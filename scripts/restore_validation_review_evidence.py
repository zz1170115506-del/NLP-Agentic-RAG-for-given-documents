"""Restore mapped detailed-evidence paths after authenticated archive extraction.

This command copies local files only. It makes no API calls and reads no keys.
The decrypted package contains PATH_MAP.json and detailed/ files. Both the
archive and logical destination paths are validated and SHA-256 checked.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


def safe(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("Unsafe evidence path")
    return path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracted", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.extracted.resolve()
    rows = json.loads((root / "PATH_MAP.json").read_text())["files"]
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Output must be a new directory")
    names = set()
    for row in rows:
        src, dest = root / safe(row["archive_path"]), safe(row["logical_path"])
        if dest in names or not src.is_file() or src.resolve() != src or src.is_symlink():
            raise ValueError("Duplicate destination or non-regular evidence file")
        names.add(dest)
        if src.stat().st_size != row["bytes"] or digest(src) != row["sha256"]:
            raise ValueError("Evidence checksum mismatch")
    output.mkdir(parents=True, mode=0o700)
    for row in rows:
        dest = output / safe(row["logical_path"])
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(root / safe(row["archive_path"]), dest)
        dest.chmod(0o600)
        if digest(dest) != row["sha256"]:
            raise ValueError("Copied evidence checksum mismatch")
    print(json.dumps({"status": "restored_and_hash_verified", "files": len(rows)}))


if __name__ == "__main__":
    main()
