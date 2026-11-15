"""Read-only SQLite quick_check with periodic progress and bounded duration."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    stat_before = args.database.stat()
    wal = Path(str(args.database) + "-wal")
    report = {"database": str(args.database), "read_only": True, "sqlite_version": sqlite3.sqlite_version,
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "file_bytes": stat_before.st_size,
              "wal_bytes_before": wal.stat().st_size if wal.exists() else 0, "progress_calls": 0,
              "state": "running", "timeout_seconds": args.timeout_seconds}
    last_log = started

    def save():
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temp = args.report.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(args.report)

    def progress():
        nonlocal last_log
        now = time.monotonic()
        report["progress_calls"] += 1
        if now - last_log >= 10:
            print(json.dumps({"database": str(args.database), "state": "running",
                              "elapsed_seconds": now - started, "progress_calls": report["progress_calls"]}), flush=True)
            last_log = now
        if now - started > args.timeout_seconds or (args.stop_file and args.stop_file.exists()):
            report["interruption"] = "timeout" if now - started > args.timeout_seconds else "stop_file"
            return 1
        return 0

    print(json.dumps(report), flush=True)
    save()
    db = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA cache_size=-8192")
        db.set_progress_handler(progress, 100000)
        report["results"] = db.execute("PRAGMA quick_check").fetchall()
        report["state"] = "passed" if report["results"] == [("ok",)] else "failed"
    except (sqlite3.Error, KeyboardInterrupt) as exc:
        report.update(state="interrupted" if report.get("interruption") or isinstance(exc, KeyboardInterrupt) else "error",
                      error_type=type(exc).__name__, error=str(exc))
    finally:
        db.close()
        now_usage = resource.getrusage(resource.RUSAGE_SELF)
        stat_after = args.database.stat()
        report.update(finished_at_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic() - started,
                      user_cpu_seconds=now_usage.ru_utime - usage_before.ru_utime,
                      system_cpu_seconds=now_usage.ru_stime - usage_before.ru_stime,
                      peak_rss_bytes=now_usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024),
                      wal_bytes_after=wal.stat().st_size if wal.exists() else 0,
                      file_size_and_mtime_unchanged=(stat_before.st_size, stat_before.st_mtime_ns) == (stat_after.st_size, stat_after.st_mtime_ns))
        save()
        print(json.dumps(report), flush=True)
    if report["state"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
