"""Explicit allowlist handoff of corpus, BM25 and committed dense shards.

Draft: review before running pack/verify. No model download or API access.
Pack is opt-in and requires stopped writers plus a fresh inventory snapshot.
All persisted paths are relative to the project/payload, never absolute roots.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import tarfile
import time

PART_BYTES = 1_900_000_000
LIMIT_BYTES = 2**31
CHUNK = 4 * 1024 * 1024
DATABASES = ("data/course-full/documents.sqlite", "indexes/course-full/sparse.sqlite")
SPARSE_MANIFEST = "indexes/course-full/sparse.manifest.json"
DENSE = {name: f"indexes/course-full-vectors/{name}/manifest.json"
         for name in ("encoder", "instruction")}
LINKS = {"indexes/course-full-vectors/sparse.sqlite": "../course-full/sparse.sqlite",
         "indexes/course-full-vectors/sparse.manifest.json": "../course-full/sparse.manifest.json"}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            result.update(block)
    return result.hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_name(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or "\x00" in value
            or path.as_posix() != value):
        raise ValueError("Unsafe relative artifact path")
    return value


def metadata(path, decode=False):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        values = dict(conn.execute("SELECT key,value FROM metadata"))
    return {key: json.loads(value) for key, value in values.items()} if decode else values


def inventory(source):
    docs = metadata(source / DATABASES[0], decode=True)
    sparse = metadata(source / DATABASES[1])
    if docs.get("importing") or not docs.get("fingerprint"):
        raise ValueError("Corpus is not a completed import")
    if sparse.get("ready") != "true" or sparse.get("fingerprint") != docs["fingerprint"]:
        raise ValueError("BM25 is not ready for the same corpus")
    manifests = {}
    for method, rel in DENSE.items():
        path = source / rel
        raw = path.read_bytes()
        data = json.loads(raw)
        if data["fingerprint"] != docs["fingerprint"]:
            raise ValueError("Dense checkpoint corpus differs")
        if sum(s["source_chunks"] for s in data["shards"]) != data["source_chunk_count"]:
            raise ValueError("Dense checkpoint source count differs")
        if sum(s["rows"] for s in data["shards"]) != data["vector_count"]:
            raise ValueError("Dense checkpoint vector count differs")
        if not 0 <= data["source_chunk_count"] <= docs["chunk_count"]:
            raise ValueError("Dense coverage out of bounds")
        if data["ready"] != (data["source_chunk_count"] == docs["chunk_count"]):
            raise ValueError("Dense ready state contradicts coverage")
        size = len(raw)
        for shard in data["shards"]:
            for key in ("vectors", "metadata"):
                name = safe_name(shard[key])
                if "/" in name or (path.parent / name).is_symlink():
                    raise ValueError("Shard must be a plain file in its checkpoint directory")
                size += (path.parent / name).stat().st_size
        manifests[method] = {"path": rel, "sha256": hashlib.sha256(raw).hexdigest(),
                             "payload_bytes": size, "manifest": data,
                             "handoff_status": "user_deferred" if method == "instruction" else
                             ("complete" if data["ready"] else "partial_checkpoint")}
    source_files = {str(p.relative_to(source)): digest(p)
                    for folder in ("src", "agent12/search_agent")
                    for p in sorted((source / folder).rglob("*.py"))}
    source_digest = hashlib.sha256(json.dumps(source_files, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
    git_sha, dirty = None, None
    if (source / ".git").exists():
        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                              text=True, stderr=subprocess.DEVNULL).strip()
            dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                                cwd=source, text=True, stderr=subprocess.DEVNULL).strip())
        except (OSError, subprocess.CalledProcessError):
            pass
    return {"format_version": 1, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "corpus": docs, "sparse": sparse, "dense": manifests,
            "database_bytes": {name: (source / name).stat().st_size for name in DATABASES},
            "sparse_manifest_sha256": digest(source / SPARSE_MANIFEST),
            "git_sha": git_sha, "git_dirty_tracked": dirty,
            "python_source_sha256": source_digest, "python_source_files": source_files}


def identity(value):
    """Timestamp is observational; payload identity must otherwise stay fixed."""
    return {key: item for key, item in value.items() if key != "captured_at_utc"}


def backup_sqlite(source, destination, *, label="database", timeout_seconds=300):
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = last_progress = last_log = time.monotonic()
    previous_remaining = None

    def progress(status, remaining, total):
        nonlocal last_progress, last_log, previous_remaining
        now = time.monotonic()
        if remaining != previous_remaining:
            last_progress, previous_remaining = now, remaining
        if now - started > timeout_seconds or now - last_progress > 45:
            raise TimeoutError("SQLite snapshot backup exceeded its bounded progress timeout")
        if now - last_log >= 5 or remaining == 0:
            print(json.dumps({"stage": "sqlite_backup", "path": label, "remaining_pages": remaining,
                              "total_pages": total, "seconds": round(now - started, 2)}), flush=True)
            last_log = now

    src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        dst = sqlite3.connect(destination, timeout=10)
        try:
            src.backup(dst, pages=4096, progress=progress, sleep=0.1)
            dst.execute("PRAGMA journal_mode=DELETE").fetchone()
        finally:
            dst.close()
    finally:
        src.close()
    # The backup includes committed WAL data; source database bytes are not copied raw.


class PartWriter:
    def __init__(self, folder, size):
        self.folder, self.size = folder, size
        self.stream = None
        self.parts = []
        self.part_hash = None
        self.part_size = 0
        self.archive_hash = hashlib.sha256()
        self.total = 0

    def _finish_part(self):
        if self.stream is None:
            return
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.stream.close()
        self.parts.append({"name": self.name, "bytes": self.part_size,
                           "sha256": self.part_hash.hexdigest()})
        self.stream = None

    def write(self, data):
        view = memoryview(data)
        count = len(view)
        self.archive_hash.update(view)
        self.total += count
        while view:
            if self.stream is None:
                self.name = f"course-data.tar.gz.part{len(self.parts) + 1:05d}"
                self.stream = (self.folder / self.name).open("xb")
                self.part_hash, self.part_size = hashlib.sha256(), 0
            length = min(len(view), self.size - self.part_size)
            self.stream.write(view[:length])
            self.part_hash.update(view[:length])
            self.part_size += length
            view = view[length:]
            if self.part_size == self.size:
                self._finish_part()
        return count

    def flush(self):
        if self.stream:
            self.stream.flush()

    def close(self):
        self._finish_part()


def pack(args):
    if not args.execute or not args.writers_stopped:
        raise ValueError("Review first; pack requires --execute --writers-stopped")
    if not 0 < args.part_bytes < LIMIT_BYTES:
        raise ValueError("Each volume must be strictly smaller than 2 GiB")
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Choose a new output directory; existing artifacts are preserved")
    expected = json.loads(args.expected_inventory.read_text())
    with ExitStack() as locks:
        for rel in DENSE.values():
            lock_path = source / Path(rel).parent / "build-lock.sqlite"
            connection = sqlite3.connect(lock_path.as_uri() + "?mode=rw", uri=True, timeout=0)
            locks.callback(connection.close)
            connection.execute("BEGIN IMMEDIATE")
        frozen = inventory(source)
        if identity(frozen) != identity(expected):
            raise ValueError("Source/checkpoint changed since inventory; recapture after stopping writers")
        required_bytes = sum(frozen["database_bytes"].values()) + sum(
            item["payload_bytes"] for item in frozen["dense"].values())
        # One stage, compressed stream with worst-case size overhead, plus margin.
        if shutil.disk_usage(output.parent).free < required_bytes * 2.1 + 1024**3:
            raise ValueError("Insufficient free space for consistent staging and archive volumes")
        output.mkdir()
        stage = output / "stage"
        stage.mkdir()
        for rel in DATABASES:
            backup_sqlite(source / rel, stage / rel, label=rel)
        for rel in [SPARSE_MANIFEST, *DENSE.values()]:
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, target)
        for entry in frozen["dense"].values():
            folder = Path(entry["path"]).parent
            for shard in entry["manifest"]["shards"]:
                for key in ("vectors", "metadata"):
                    rel = folder / shard[key]
                    shutil.copyfile(source / rel, stage / rel)
                    if digest(stage / rel) != shard[key + "_sha256"]:
                        raise ValueError("Committed shard checksum mismatch")
        for rel, target in LINKS.items():
            (stage / rel).symlink_to(target)
        for name in ("corpus", "validation", "test", "encoder", "instruction", "reranker"):
            original = args.license_evidence / name / "README.md"
            target = stage / "THIRD_PARTY" / name / "README.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        shutil.copyfile(args.license_evidence / "fetch-results.json", stage / "THIRD_PARTY" / "fetch-results.json")
        (stage / "THIRD_PARTY" / "standard").mkdir()
        for filename in ("MIT.txt", "Apache-2.0.txt", "manifest.json"):
            shutil.copyfile(args.license_evidence / "standard" / filename,
                            stage / "THIRD_PARTY" / "standard" / filename)
        shutil.copyfile(args.license_evidence.parent / "MODEL_DOWNLOADS.json", stage / "MODEL_DOWNLOADS.json")
        if metadata(stage / DATABASES[0], True) != frozen["corpus"]:
            raise ValueError("Corpus changed during backup")
        if metadata(stage / DATABASES[1]) != frozen["sparse"]:
            raise ValueError("BM25 changed during backup")
        if identity(inventory(source)) != identity(frozen):
            raise ValueError("Source changed during staging; do not publish this directory")
    files = {}
    for path in sorted(stage.rglob("*")):
        rel = path.relative_to(stage).as_posix()
        if path.is_symlink():
            files[rel] = {"type": "symlink", "target": path.readlink().as_posix()}
        elif path.is_file():
            files[rel] = {"type": "file", "bytes": path.stat().st_size, "sha256": digest(path)}
    handoff = {"format_version": 1, "scope": "corpus_bm25_dense_checkpoints_without_models_or_questions",
               "source_snapshot": frozen, "files": files,
               "sqlite_transfer": "SQLite online backup into self-contained DELETE-journal databases",
               "code_delivery": "Separate code archive or Git checkout; compare python_source_sha256"}
    json_write(stage / "HANDOFF.json", handoff)
    # Stage is now independent; source builders may resume after this point.
    writer = PartWriter(output, args.part_bytes)
    try:
        with gzip.GzipFile(filename="", fileobj=writer, mode="wb", compresslevel=1, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for rel in ["HANDOFF.json", *files]:
                    info = archive.gettarinfo(str(stage / rel), arcname=rel)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    info.mode = 0o777 if info.issym() else 0o644
                    if info.isfile():
                        with (stage / rel).open("rb") as stream:
                            archive.addfile(info, stream)
                    else:
                        archive.addfile(info)
    finally:
        writer.close()
    manifest = {"format_version": 1, "compression": "tar+gzip", "part_limit_bytes": args.part_bytes,
                "archive_bytes": writer.total, "archive_sha256": writer.archive_hash.hexdigest(),
                "handoff_sha256": digest(stage / "HANDOFF.json"), "parts": writer.parts}
    json_write(output / "VOLUMES.json", manifest)
    (output / "SHA256SUMS").write_text("".join(
        f"{part['sha256']}  {part['name']}\n" for part in writer.parts), encoding="utf-8")
    print(json.dumps({"status": "packed_not_yet_independently_verified", "parts": len(writer.parts),
                      "archive_bytes": writer.total, "archive_sha256": manifest["archive_sha256"]}))


class PartReader:
    def __init__(self, folder, parts):
        self.paths = iter(folder / row["name"] for row in parts)
        self.stream = None

    def read(self, size):
        if size < 0:
            raise ValueError("Unbounded archive read is not supported")
        blocks = []
        remaining = size
        while remaining:
            if self.stream is None:
                path = next(self.paths, None)
                if path is None:
                    break
                self.stream = path.open("rb")
            block = self.stream.read(remaining)
            if block:
                blocks.append(block)
                remaining -= len(block)
            else:
                self.stream.close()
                self.stream = None
        return b"".join(blocks)

    def close(self):
        if self.stream:
            self.stream.close()


def checked_dense_paths(root, handoff):
    """Validate every semantic-check path before opening any checkpoint file."""
    dense = handoff["source_snapshot"]["dense"]
    if set(dense) != set(DENSE):
        raise ValueError("Unexpected dense methods in handoff snapshot")
    for method, expected in DENSE.items():
        entry = dense[method]
        if entry["path"] != expected:
            raise ValueError("Dense manifest must use its fixed expected path")
        manifest_file = handoff["files"].get(expected, {})
        if manifest_file.get("type") != "file" or manifest_file.get("sha256") != entry["sha256"]:
            raise ValueError("Dense manifest is not bound to the verified payload")
        paths = [expected]
        for shard in entry["manifest"]["shards"]:
            for key in ("vectors", "metadata"):
                name = safe_name(shard[key])
                if "/" in name:
                    raise ValueError("Dense shard must be a plain basename")
                rel = (Path(expected).parent / name).as_posix()
                file = handoff["files"].get(rel, {})
                if file.get("type") != "file" or file.get("sha256") != shard[key + "_sha256"]:
                    raise ValueError("Dense shard is not bound to the verified payload")
                paths.append(rel)
        for rel in paths:
            path = root / rel
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Semantic verification path escapes restored payload")


def verify_sqlite_and_vectors(root, handoff):
    """Read-only semantic smoke checks; requires numpy, no model weights/API."""
    import numpy as np

    snapshot = handoff["source_snapshot"]
    checked_dense_paths(root, handoff)
    results = {}
    for rel in DATABASES:
        with sqlite3.connect((root / rel).resolve().as_uri() + "?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise ValueError("SQLite quick_check failed")
            if rel == DATABASES[0]:
                for table, key in (("documents", "document_count"), ("chunks", "chunk_count")):
                    count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    if count != snapshot["corpus"][key]:
                        raise ValueError("Restored corpus count differs")
                rows = connection.execute("SELECT doc_id,offset,text FROM chunks ORDER BY seq LIMIT 3").fetchall()
                for doc_id, offset, text in rows:
                    full = connection.execute("SELECT text FROM documents WHERE doc_id=?", (doc_id,)).fetchone()[0]
                    if full[offset:offset + len(text)] != text:
                        raise ValueError("Corpus chunk offsets do not match original text")
            else:
                count = connection.execute("SELECT count(*) FROM records").fetchone()[0]
                if count != snapshot["corpus"]["chunk_count"]:
                    raise ValueError("Restored BM25 count differs")
                # Exercise the FTS table without printing source text.
                connection.execute("SELECT rowid FROM fts WHERE fts MATCH ? LIMIT 3", ('"university"',)).fetchall()
            results[rel] = "quick_check_and_counts_passed"
    if metadata(root / DATABASES[0], True) != snapshot["corpus"] or metadata(root / DATABASES[1]) != snapshot["sparse"]:
        raise ValueError("Restored database metadata differs")
    for method, entry in snapshot["dense"].items():
        folder = root / Path(entry["path"]).parent
        manifest = json.loads((root / entry["path"]).read_text())
        if manifest != entry["manifest"]:
            raise ValueError("Restored dense manifest differs")
        for shard in manifest["shards"]:
            vectors = np.load(folder / shard["vectors"], mmap_mode="r", allow_pickle=False)
            if vectors.shape != (shard["rows"], manifest["dimension"]) or vectors.dtype != np.dtype("float32"):
                raise ValueError("Restored shard shape or dtype differs")
            for start in range(0, len(vectors), 1024):
                if not np.isfinite(vectors[start:start + 1024]).all():
                    raise ValueError("Non-finite vector values")
            with (folder / shard["metadata"]).open(encoding="utf-8") as stream:
                rows = sum(1 for line in stream if json.loads(line))
            if rows != shard["rows"]:
                raise ValueError("Restored shard metadata count differs")
        results[method] = {"ready": manifest["ready"], "source_chunks": manifest["source_chunk_count"],
                           "total_source_chunks": snapshot["corpus"]["chunk_count"],
                           "vectors": manifest["vector_count"], "shards": len(manifest["shards"])}
    for rel, target in LINKS.items():
        if not (root / rel).is_symlink() or (root / rel).readlink().as_posix() != target:
            raise ValueError("Relative BM25 link was not restored")
        if not (root / rel).exists():
            raise ValueError("Restored BM25 link is broken")
    return results


def verify(args):
    folder = args.volumes.parent
    volumes = json.loads(args.volumes.read_text())
    if not 0 < volumes["part_limit_bytes"] < LIMIT_BYTES or not volumes["parts"]:
        raise ValueError("Invalid volume limits")
    archive_hash, total = hashlib.sha256(), 0
    for number, row in enumerate(volumes["parts"], 1):
        if row["name"] != f"course-data.tar.gz.part{number:05d}":
            raise ValueError("Volume order/name differs")
        path = folder / row["name"]
        if path.is_symlink() or path.stat().st_size != row["bytes"] or not 0 < row["bytes"] <= volumes["part_limit_bytes"]:
            raise ValueError("Volume size or type differs")
        result = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(CHUNK), b""):
                result.update(block)
                archive_hash.update(block)
                total += len(block)
        if result.hexdigest() != row["sha256"]:
            raise ValueError("Volume checksum differs")
    if total != volumes["archive_bytes"] or archive_hash.hexdigest() != volumes["archive_sha256"]:
        raise ValueError("Combined archive checksum differs")
    restore = None
    if args.extract:
        destination = args.extract.resolve()
        restore = destination.with_name(destination.name + ".partial")
        if destination.exists() or restore.exists():
            raise ValueError("Restore destination must be new")
        restore.mkdir(parents=True)
    elif args.semantic:
        raise ValueError("--semantic requires --extract into a fresh directory")
    reader, seen = PartReader(folder, volumes["parts"]), set()
    try:
        with tarfile.open(fileobj=reader, mode="r|gz") as archive:
            first = archive.next()
            if first is None or first.name != "HANDOFF.json" or not first.isfile() or first.size > 32 * 1024**2:
                raise ValueError("Archive must begin with a bounded HANDOFF.json")
            raw = archive.extractfile(first).read()
            if hashlib.sha256(raw).hexdigest() != volumes["handoff_sha256"]:
                raise ValueError("Handoff manifest checksum differs")
            handoff = json.loads(raw)
            if restore:
                (restore / "HANDOFF.json").write_bytes(raw)
            while (member := archive.next()) is not None:
                rel = safe_name(member.name)
                if rel in seen or rel not in handoff["files"]:
                    raise ValueError("Duplicate or unexpected archive member")
                seen.add(rel)
                entry = handoff["files"][rel]
                if entry["type"] == "symlink":
                    if not member.issym() or LINKS.get(rel) != member.linkname or entry["target"] != member.linkname:
                        raise ValueError("Unexpected archive link")
                    if restore:
                        (restore / rel).parent.mkdir(parents=True, exist_ok=True)
                        (restore / rel).symlink_to(member.linkname)
                elif entry["type"] == "file":
                    if not member.isfile() or member.size != entry["bytes"]:
                        raise ValueError("Archive file type/size differs")
                    stream, result = archive.extractfile(member), hashlib.sha256()
                    with ExitStack() as handles:
                        output = None
                        if restore:
                            (restore / rel).parent.mkdir(parents=True, exist_ok=True)
                            output = handles.enter_context((restore / rel).open("xb"))
                        for block in iter(lambda: stream.read(CHUNK), b""):
                            result.update(block)
                            if output:
                                output.write(block)
                    if result.hexdigest() != entry["sha256"]:
                        raise ValueError("Payload file checksum differs")
                else:
                    raise ValueError("Unsupported payload type")
    finally:
        reader.close()
    if seen != set(handoff["files"]):
        raise ValueError("Archive payload missing files")
    results = verify_sqlite_and_vectors(restore, handoff) if args.semantic else None
    if restore:
        restore.rename(destination)
    print(json.dumps({"status": "verified", "archive_sha256": volumes["archive_sha256"],
                      "files": len(seen), "restored": bool(restore), "semantic_checks": results}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inventory", help="Read metadata/manifests; does not hash large databases")
    inspect.add_argument("--source", required=True, type=Path)
    inspect.add_argument("--output", required=True, type=Path)
    package = sub.add_parser("pack")
    package.add_argument("--source", required=True, type=Path)
    package.add_argument("--output", required=True, type=Path)
    package.add_argument("--expected-inventory", required=True, type=Path)
    package.add_argument("--license-evidence", required=True, type=Path)
    package.add_argument("--part-bytes", type=int, default=PART_BYTES)
    package.add_argument("--writers-stopped", action="store_true")
    package.add_argument("--execute", action="store_true")
    check = sub.add_parser("verify")
    check.add_argument("--volumes", required=True, type=Path)
    check.add_argument("--extract", type=Path)
    check.add_argument("--semantic", action="store_true")
    args = parser.parse_args()
    if args.command == "inventory":
        if args.output.exists():
            raise ValueError("Inventory output exists; choose a new name to preserve it")
        json_write(args.output, inventory(args.source))
        print("Inventory captured; active writers must still stop before packaging")
    elif args.command == "pack":
        pack(args)
    else:
        verify(args)


if __name__ == "__main__":
    main()
