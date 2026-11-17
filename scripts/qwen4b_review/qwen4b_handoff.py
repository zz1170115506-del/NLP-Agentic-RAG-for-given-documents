#!/usr/bin/env python3
"""Build or independently restore the Qwen nine-question evidence package."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile


RECEIPT = "QWEN4B_EVIDENCE_RECEIPT.json"
KEY_NAME = "qwen4b-evidence.key"
PRIVATE_NAMES = {".git", ".ssh", ".aws", ".secrets", "credentials.json"}
SKIP = {"__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store"}
SECRET = re.compile(rb"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_.-]{18,}|gh[pousr]_[A-Za-z0-9]{24,}|"
                    rb"github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----)")
EVIDENCE_TYPES = {".json", ".jsonl", ".md", ".txt", ".csv", ".tsv", ".log", ".yaml", ".yml", ".py", ".zip", ".npz"}


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def logical_path(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or value != str(path) or
            any(part in {".", ".."} for part in path.parts) or any(c in value for c in ("\\", ":", "\0"))):
        raise ValueError("Invalid relative evidence path")
    if any(part.lower().startswith(".env") or part.lower() in PRIVATE_NAMES for part in path.parts):
        raise ValueError("Credential file cannot enter evidence")
    if SECRET.search(value.encode()) or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx"}:
        raise ValueError("Secret material cannot enter evidence")
    return path


def inspect_bytes(data, logical):
    if SECRET.search(data):
        raise ValueError(f"Credential-shaped data detected in {logical}; keep credentials out of raw traces")


def inspect_vectors(archive):
    """Validate the compact document cache without loading numpy or unpickling data."""
    names = ("doc_ids.npy", "chunk_ids.npy", "codes.npy", "scales.npy")
    if sorted(archive.namelist()) != sorted(names):
        raise ValueError("Unexpected fields in compact Qwen vector cache")
    headers = {}
    payload_bytes = {}
    for name in names:
        with archive.open(name) as stream:
            if stream.read(6) != b"\x93NUMPY":
                raise ValueError("Invalid NPY vector member")
            version = stream.read(2)
            if version not in {b"\x01\x00", b"\x02\x00", b"\x03\x00"}:
                raise ValueError("Unsupported NPY header version")
            n = int.from_bytes(stream.read(2 if version[0] == 1 else 4), "little")
            if n > 65536:
                raise ValueError("Unexpected vector header length")
            headers[name] = ast.literal_eval(stream.read(n).decode("utf-8"))
            payload_bytes[name] = archive.getinfo(name).file_size - stream.tell()
    nrows, ndim = headers["codes.npy"]["shape"]
    if not 32 <= ndim <= 2560 or nrows < 1 or headers["codes.npy"]["descr"] != "|i1":
        raise ValueError("Expected compact int8 vector rows")
    if headers["scales.npy"]["descr"] not in {"<f4", ">f4"} or headers["scales.npy"]["shape"] != (nrows,):
        raise ValueError("Expected one float32 scale per compact vector")
    if payload_bytes["codes.npy"] != nrows * ndim or payload_bytes["scales.npy"] != nrows * 4:
        raise ValueError("Vector cache payload length differs from declared shape or dtype")
    for name in names[:2]:
        if not re.fullmatch(r"[<>=|](?:[USiu])\d+", headers[name]["descr"]) or headers[name]["shape"] != (nrows,):
            raise ValueError("Expected plain document/chunk identifiers in compact vector cache")
    return nrows, ndim


def verify_live_run(run, dimension, question_ids, question_hash):
    """Bind each labeled run to its actual vector width, questions and post-run assessment."""
    for name in ("events.jsonl", "retrieval.jsonl", "question-executions.jsonl"):
        if (run/name).stat().st_size == 0:
            raise ValueError(f"Missing live run records: {name}")
    with zipfile.ZipFile(run/"vectors.npz") as archive:
        _, observed_dimension = inspect_vectors(archive)
    if observed_dimension != dimension:
        raise ValueError(f"Requested dimension {dimension} differs from saved vector width {observed_dimension}")
    pred = run/"prediction.jsonl"
    ids = [str(json.loads(line)["id"]) for line in pred.read_text().splitlines()]
    meta = json.loads((run/"prediction.jsonl.meta.json").read_bytes())
    if (ids != question_ids or meta["mode"] != "live" or meta["source_sha256"] != question_hash
            or meta["input_count"] != len(ids)):
        raise ValueError("Live prediction identities differ from the ordered question input")
    scores = json.loads((run/"evaluation/metrics.json").read_bytes())
    evaluated = json.loads((run/"evaluation/evaluation-identity.json").read_bytes())
    if (not scores["valid"] or scores["records"] != len(ids) or scores["expected"] != len(ids)
            or evaluated["prediction_sha256"] != sha(pred) or not evaluated["evaluated_after_run_completed"]):
        raise ValueError("Post-run evaluation does not match all live predictions")
    selected_ref = run/"evaluation/selected-validation-reference-private.jsonl"
    if sha(selected_ref) != evaluated["selected_reference_sha256"]:
        raise ValueError("Post-run reference identity differs from the selected answers")
    return evaluated["reference_source_sha256"], evaluated["selected_reference_sha256"]


def selected(roots):
    files = {}
    for prefix, source in roots:
        prefix = logical_path(prefix)
        source = source.resolve(strict=True)
        candidates = sorted(source.rglob("*")) if source.is_dir() else [source]
        count = 0
        for path in candidates:
            name = prefix / path.relative_to(source) if path != source else prefix
            if set(name.parts) & SKIP or path.suffix in {".lock", ".pyc"}:
                continue
            if path.is_symlink():
                raise ValueError(f"Unexpected symlink in evidence: {name}")
            if path.is_dir():
                continue
            logical_path(name.as_posix())
            if path.suffix.lower() not in EVIDENCE_TYPES or not path.is_file():
                raise ValueError(f"Select evidence files only; exclude databases, models and binary caches: {name}")
            if name.as_posix() in files:
                raise ValueError(f"Duplicate evidence destination: {name}")
            files[name.as_posix()] = path
            count += 1
        if count == 0:
            raise ValueError(f"Selected evidence group has no files: {prefix}")
    return files


def invoke(python, script, *args):
    subprocess.run([str(python), str(script), *map(str, args)], check=True)


def restore(repo, crypto, assets, key, work, expected):
    expected_raw = expected.read_bytes()
    if (assets / RECEIPT).read_bytes() != expected_raw:
        raise ValueError("Download receipt differs from the chosen receipt")
    receipt = json.loads(expected_raw)
    manifest = assets / "ENCRYPTED_VOLUMES.json"
    if sha(manifest) != receipt["encrypted_manifest_sha256"]:
        raise ValueError("Encrypted volume manifest differs from receipt")
    outer = json.loads(manifest.read_bytes())
    if outer["key_id"] != receipt["key_id"] or outer["parts"] != receipt["encrypted_parts"]:
        raise ValueError("Encrypted volume list does not match receipt")
    for part in receipt["encrypted_parts"]:
        name = logical_path(part["name"])
        if len(name.parts) != 1:
            raise ValueError("Invalid encrypted volume name")
        p = assets / name
        if p.stat().st_size != part["bytes"] or sha(p) != part["sha256"]:
            raise ValueError(f"Downloaded ciphertext failed byte/size verification: {name}")
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    scripts = repo / "scripts"
    invoke(crypto, scripts/"handoff/handoff_crypto.py", "decrypt", "--manifest", manifest,
           "--key-file", key, "--output", work/"decrypted")
    invoke(sys.executable, scripts/"handoff/handoff_archive.py", "verify", "--volumes",
           work/"decrypted/VOLUMES.json", "--extract", work/"extracted")
    invoke(sys.executable, scripts/"restore_validation_review_evidence.py", "--extracted",
           work/"extracted", "--output", work/"restored")
    path_map = work/"extracted/PATH_MAP.json"
    if sha(path_map) != receipt["path_map_sha256"]:
        raise ValueError("Restored evidence inventory is different")
    rows = json.loads(path_map.read_bytes())["files"]
    if len(rows) != receipt["evidence_files"] or sum(row["bytes"] for row in rows) != receipt["plaintext_bytes"]:
        raise ValueError("Restored file count or total bytes differs")
    restored = work/"restored"
    names = {str(path.relative_to(restored)) for path in restored.rglob("*") if path.is_file()}
    if names != {row["logical_path"] for row in rows}:
        raise ValueError("Unexpected or missing restored evidence")
    for row in rows:
        p = restored / logical_path(row["logical_path"])
        if p.stat().st_size != row["bytes"] or sha(p) != row["sha256"]:
            raise ValueError("Restored evidence failed original SHA-256 check")
    report = {"status": "verified", "authenticated_decryption": True, "ciphertext_parts": len(outer["parts"]),
              "logical_evidence_files_restored": len(rows), "all_original_sha256_matched": True,
              "plaintext_bytes": receipt["plaintext_bytes"], "path_map_sha256": sha(path_map)}
    write_json(work/"RESTORE_CHECK.json", report)
    print(json.dumps(report))


def pack(args):
    output, work = args.output.resolve(), args.work.resolve()
    run, baseline = args.run.resolve(), args.baseline.resolve()
    baseline_label, package_label = "baseline-v2", "qwen4b-nine-evidence"
    if args.paired_int8_dimensions:
        old_dim, new_dim = args.paired_int8_dimensions
        if old_dim == new_dim or not args.questions:
            raise ValueError("Paired-dimension handoff requires two different widths and the questions file")
        ids = [str(json.loads(line)["id"]) for line in args.questions.read_text().splitlines()]
        if len(ids) != 9 or len(set(ids)) != 9:
            raise ValueError("Expected exactly nine unique question IDs")
        question_hash = sha(args.questions)
        old_ref = verify_live_run(baseline, old_dim, ids, question_hash)
        new_ref = verify_live_run(run, new_dim, ids, question_hash)
        if old_ref != new_ref:
            raise ValueError("Paired evaluations used different answer references")
        baseline_label = f"baseline-int8-{old_dim}"
        package_label = f"qwen4b-int8-{old_dim}-vs-{new_dim}"
    elif not args.audit:
        raise ValueError("The original baseline-v2 handoff requires its audit directory")
    roots = [("run", run), (baseline_label, baseline)]
    if args.audit:
        roots.append(("audit", args.audit))
    if args.questions:
        roots.append(("inputs/nine-questions.jsonl", args.questions))
    for value in args.add:
        label, sep, path = value.partition("=")
        if not sep or not path:
            raise ValueError("--add expects LOGICAL_PATH=LOCAL_PATH")
        roots.append((label, Path(path)))
    for _, selected_root in roots:
        selected_root = selected_root.resolve(strict=True)
        if any(p == selected_root or p.is_relative_to(selected_root) for p in (output, work)):
            raise ValueError("Keep workspace and delivery output outside the selected inputs")
    if work == output or work.is_relative_to(output):
        raise ValueError("Keep plaintext scratch outside the delivery output")
    files = selected(roots)
    assets, private = output/"release-assets", output/"private"
    key = private/KEY_NAME
    if assets.exists() or key.exists() or assets.is_symlink() or private.is_symlink() or key.is_symlink():
        raise ValueError("New evidence requires a fresh release asset directory and a new local key")
    work.mkdir(parents=True, exist_ok=False, mode=0o700)
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    private.chmod(0o700)
    stage = work/"staged"
    stage.mkdir(mode=0o700)
    rows = []
    for i, (name, source) in enumerate(sorted(files.items()), 1):
        payload = source.read_bytes()
        inspect_bytes(payload, name)
        if source.suffix.lower() in {".zip", ".npz"}:
            with zipfile.ZipFile(source) as archive:
                if source.suffix.lower() == ".npz":
                    inspect_vectors(archive)
                for entry in archive.infolist():
                    if not entry.is_dir():
                        logical_path(entry.filename)
                        inspect_bytes(archive.read(entry), name)
        digest = hashlib.sha256(payload).hexdigest()
        archive_name = f"detailed/file-{i:05d}"
        dest = stage/archive_name
        dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        dest.write_bytes(payload)
        if sha(dest) != digest or sha(source) != digest:
            raise ValueError(f"Source changed during capture: {name}")
        rows.append({"logical_path": name, "archive_path": archive_name, "bytes": len(payload), "sha256": digest})
    for row in rows:
        if sha(files[row["logical_path"]]) != row["sha256"]:
            raise ValueError("An input changed during capture; stop writers before packaging")
    # Detect an appended attempt creating a new file during staging.
    if selected(roots) != files:
        raise ValueError("Evidence inventory changed during capture")
    path_map = stage/"PATH_MAP.json"
    write_json(path_map, {"format_version": 1, "scope": "qwen4b_nine_evidence", "files": rows})
    include = work/"include.json"
    write_json(include, ["PATH_MAP.json", *[row["archive_path"] for row in rows]])
    scripts = args.repo / "scripts/handoff"
    invoke(sys.executable, scripts/"pack_selected_files.py", "--source", stage, "--include-list", include,
           "--output", work/"volumes")
    invoke(args.crypto_python, scripts/"handoff_crypto.py", "encrypt", "--volumes", work/"volumes/VOLUMES.json",
           "--output", assets, "--key-file", key, "--label", package_label)
    if (key.stat().st_mode & 0o777) != 0o600 or (private.stat().st_mode & 0o777) != 0o700:
        raise ValueError("Unexpected key or directory mode")
    outer_path = assets/"ENCRYPTED_VOLUMES.json"
    outer = json.loads(outer_path.read_bytes())
    if {p.name for p in assets.iterdir()} != {outer_path.name, "SHA256SUMS", *[part["name"] for part in outer["parts"]]}:
        raise ValueError("Public asset directory contains an unexpected item")
    # Only generated field names, checksums, counts and ciphertext names enter this public receipt.
    receipt = {"format_version": 1, "algorithm": outer["algorithm"], "key_id": outer["key_id"],
               "evidence_files": len(rows), "plaintext_bytes": sum(row["bytes"] for row in rows),
               "path_map_sha256": sha(path_map), "encrypted_manifest_sha256": sha(outer_path),
               "encrypted_parts": outer["parts"]}
    write_json(assets/RECEIPT, receipt)
    (assets/"SHA256SUMS").write_text("".join(
        f"{sha(p)}  {p.name}\n" for p in sorted(assets.iterdir()) if p.name != "SHA256SUMS"), encoding="utf-8")
    restore(args.repo, args.crypto_python, assets, key, work/"local-check", assets/RECEIPT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_subparsers(dest="command", required=True)
    packer = mode.add_parser("pack", help="Encrypt selected evidence and verify complete local restoration")
    verifier = mode.add_parser("verify", help="Authenticate downloaded assets and recheck each original file")
    for sub in (packer, verifier):
        sub.add_argument("--repo", type=Path, required=True, help="Source checkout containing scripts/handoff")
        sub.add_argument("--crypto-python", type=Path, required=True, help="Python with cryptography installed")
        sub.add_argument("--work", type=Path, required=True, help="New local private work directory")
    for field in ("run", "baseline", "output"):
        packer.add_argument("--"+field, type=Path, required=True)
    packer.add_argument("--audit", type=Path, help="Audit evidence directory (required for the original v2 baseline)")
    packer.add_argument("--questions", type=Path)
    packer.add_argument("--paired-int8-dimensions", type=int, nargs=2, metavar=("BASELINE", "CANDIDATE"),
                        help="Validate and package two independently evaluated live int8 runs")
    packer.add_argument("--add", action="append", default=[], metavar="LOGICAL_PATH=LOCAL_PATH")
    verifier.add_argument("--assets", type=Path, required=True)
    verifier.add_argument("--key", type=Path, required=True)
    verifier.add_argument("--expected-receipt", type=Path, help="Local trusted receipt, recommended for remote recheck")
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "pack":
        pack(args)
    else:
        restore(args.repo, args.crypto_python, args.assets, args.key, args.work,
                args.expected_receipt or args.assets/RECEIPT)


if __name__ == "__main__":
    main()
