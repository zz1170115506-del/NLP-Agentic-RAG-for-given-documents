"""Package an explicit file list (e.g. completed private run traces) for encryption.

Paths are relative to --source. Directories, links, .env, key files and private
folders are refused. This command does not upload or encrypt on its own.
"""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import tarfile

from handoff_archive import PART_BYTES, LIMIT_BYTES, PartWriter, digest, json_write, safe_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--include-list", type=Path, required=True, help="JSON array of exact relative file paths")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--part-bytes", type=int, default=PART_BYTES)
    args = parser.parse_args()
    names = json.loads(args.include_list.read_text())
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        parser.error("Include list must be a nonempty array of unique paths")
    if args.output.exists() or not 0 < args.part_bytes < LIMIT_BYTES:
        parser.error("Output must be new and volume limit strictly less than 2 GiB")
    source = args.source.resolve()
    for rel in names:
        safe_name(rel)
        parts = [part.lower() for part in Path(rel).parts]
        if rel == "HANDOFF.json" or any(p.startswith(".env") or p in {"private", ".git", ".ssh", ".aws"} for p in parts) or Path(rel).suffix.lower() in {".key", ".pem"}:
            parser.error("Secret/configuration credential files are not package inputs")
        path = source / rel
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            parser.error("Each input must be a regular file with no symlink parents")
    args.output.mkdir(parents=True)
    stage = args.output / "stage"
    stage.mkdir()
    files = {}
    for rel in sorted(names):
        original, target = source / rel, stage / rel
        before = digest(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if digest(target) != before or digest(original) != before:
            raise ValueError("A selected file changed during capture")
        files[rel] = {"type": "file", "bytes": target.stat().st_size, "sha256": before}
    json_write(stage / "HANDOFF.json", {"format_version": 1, "scope": "explicit_selected_files",
        "source_snapshot": {"kind": "completed_selected_run_evidence"}, "files": files})
    writer = PartWriter(args.output, args.part_bytes)
    try:
        with gzip.GzipFile(filename="", fileobj=writer, mode="wb", compresslevel=1, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|") as archive:
                for rel in ["HANDOFF.json", *files]:
                    info = archive.gettarinfo(str(stage / rel), arcname=rel)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime, info.mode = 0, 0o644
                    with (stage / rel).open("rb") as stream:
                        archive.addfile(info, stream)
    finally:
        writer.close()
    json_write(args.output / "VOLUMES.json", {"format_version": 1, "compression": "tar+gzip",
        "part_limit_bytes": args.part_bytes, "archive_bytes": writer.total,
        "archive_sha256": writer.archive_hash.hexdigest(), "handoff_sha256": digest(stage / "HANDOFF.json"),
        "parts": writer.parts})
    print(json.dumps({"status": "packed_selected_files_for_encryption", "files": len(files), "parts": len(writer.parts)}))


if __name__ == "__main__":
    main()
