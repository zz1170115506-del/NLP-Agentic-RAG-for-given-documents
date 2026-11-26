"""Make consistent, writable acceptance copies without changing the source checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("work/acceptance/indexes/copy_report.json"))
    parser.add_argument("--defer-quick-check", action="store_true", help="Copy now; run the full database scan separately")
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"source": str(args.source), "copies": []}

    def record(event):
        report["copies"].append(event)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(event, ensure_ascii=False), flush=True)

    for relative in ("data/course-full/documents.sqlite", "indexes/course-full/sparse.sqlite"):
        source, target = args.source / relative, Path(relative)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".clone.sqlite")
        if temporary.exists():
            raise FileExistsError(temporary)
        started = time.monotonic()
        source_stat = source.stat()
        wal = Path(str(source) + "-wal")
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as src:
            src.execute("BEGIN")
            source_metadata = src.execute("SELECT key,value FROM metadata ORDER BY key").fetchall()
            if wal.exists() and wal.stat().st_size:
                raise ValueError(f"Source WAL is nonempty; clone is not sufficient: {wal}")
            subprocess.run(["cp", "-c", str(source), str(temporary)], check=True)
            after_stat = source.stat()
            if (source_stat.st_size, source_stat.st_mtime_ns) != (after_stat.st_size, after_stat.st_mtime_ns):
                raise ValueError(f"Source changed while cloning: {source}")
            if wal.exists() and wal.stat().st_size:
                raise ValueError(f"Source WAL became nonempty during clone: {wal}")
            src.rollback()
        src.close()
        print(json.dumps({"path": relative, "stage": "APFS clone completed; verifying SQLite"}), flush=True)
        with sqlite3.connect(temporary) as dst:
            copied_metadata = dst.execute("SELECT key,value FROM metadata ORDER BY key").fetchall()
            if copied_metadata != source_metadata:
                raise ValueError(f"Metadata mismatch after cloning {source}")
            if not args.defer_quick_check:
                check = dst.execute("PRAGMA quick_check").fetchall()
                if check != [("ok",)]:
                    raise ValueError(f"SQLite quick_check failed: {check}")
        dst.close()
        temporary.replace(target)
        record({"path": relative, "method": "APFS cp -c under a read transaction; WAL zero and source stat stable before/after",
                "source_wal_bytes_after": wal.stat().st_size if wal.exists() else 0,
                "bytes": target.stat().st_size, "seconds": time.monotonic() - started,
                "quick_check": "pending separate scan" if args.defer_quick_check else "ok", "metadata_equal": True})

    shutil.copy2(args.source / "indexes/course-full/sparse.manifest.json", "indexes/course-full/sparse.manifest.json")
    for relative in ("indexes/course-full-vectors", "indexes/model_cache"):
        target = Path(relative)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite {target}")
        started = time.monotonic()
        subprocess.run(["cp", "-cR", str(args.source / relative), str(target)], check=True)
        record({"path": relative, "method": "APFS cp -cR clone, preserving relative symlinks",
                "seconds": time.monotonic() - started})
    for method in ("encoder", "instruction"):
        directory = Path("indexes/course-full-vectors") / method
        manifest = json.loads((directory / "manifest.json").read_text())
        for shard in manifest["shards"]:
            for key in ("vectors", "metadata"):
                actual = hashlib.sha256((directory / shard[key]).read_bytes()).hexdigest()
                if actual != shard[key + "_sha256"]:
                    raise ValueError(f"Copied checkpoint hash mismatch: {shard[key]}")
        record({"method": method, "copied_shards_verified": len(manifest["shards"]),
                "source_chunks": manifest["source_chunk_count"], "ready": manifest["ready"]})
    for name in ("sparse.sqlite", "sparse.manifest.json"):
        link = Path("indexes/course-full-vectors") / name
        if not link.exists() or not link.is_symlink():
            raise ValueError(f"Copied sparse link is invalid: {link}")
    print("Acceptance data and index copies are ready.", flush=True)


if __name__ == "__main__":
    main()
