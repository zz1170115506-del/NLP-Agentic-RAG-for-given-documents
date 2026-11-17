"""Verify the supplement map and expand its files using the team's original logical names."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


def restore(source: Path, output: Path) -> int:
    if output.exists():
        raise ValueError("Choose a new output directory")
    source = source.resolve(strict=True)
    data = json.loads((source / "file-map.json").read_text(encoding="utf-8"))
    if data["version"] != 1 or data["logical_entries"] != len(data["records"]):
        raise ValueError("Unsupported or incomplete map")
    rows = [r for r in data["records"] if r["location"] == "supplement"]
    seen_paths = set()
    seen_hashes = set()
    for r in rows:
        rel = PurePosixPath(r["path"])
        digest = PurePosixPath(r["file"]).name
        if (str(rel) != r["path"] or not rel.parts or rel.is_absolute() or ".." in rel.parts
                or r["path"] in seen_paths or "\\" in r["path"]):
            raise ValueError("Unsafe or repeated logical path")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) or r["file"] != f"payload/{digest}":
            raise ValueError("Invalid content-addressed payload")
        payload = source / r["file"]
        if payload.resolve(strict=True) != payload or not payload.is_file() or payload.stat().st_size != r["bytes"]:
            raise ValueError("Payload size or path mismatch")
        if digest not in seen_hashes:
            with payload.open("rb") as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != digest:
                    raise ValueError("Wrong payload SHA-256")
            seen_hashes.add(digest)
        seen_paths.add(r["path"])
    if (len(rows) != data["supplemental_logical_paths"] or len(seen_hashes) != data["supplemental_unique_payloads"]
            or seen_hashes != {p.name for p in (source / "payload").iterdir()}):
        raise ValueError("Payload coverage differs from the inventory")
    output.mkdir(parents=True, mode=0o700)
    for r in rows:
        target = output / r["path"]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source / r["file"], target)
        target.chmod(0o600)
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path, help="Extracted supplement directory containing file-map.json")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps({"restored_logical_files": restore(args.source, args.output)}))
