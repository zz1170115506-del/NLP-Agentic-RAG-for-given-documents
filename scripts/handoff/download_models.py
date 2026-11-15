"""Download only selected immutable model snapshots; never performs encoding."""
import argparse
import json
from pathlib import Path
from handoff_paths import documentation_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=documentation_dir() / "MODEL_DOWNLOADS.json")
    parser.add_argument("--cache-dir", type=Path, default=Path("indexes/model_cache"))
    parser.add_argument("--roles", nargs="+", choices=["encoder", "instruction", "reranker"], default=["encoder"])
    parser.add_argument("--offline", action="store_true", help="Verify an existing cache without downloading")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    manifest = json.loads(args.manifest.read_text())
    for entry in manifest["models"]:
        if entry["role"] not in args.roles:
            continue
        snapshot = Path(snapshot_download(repo_id=entry["repo_id"], repo_type="model",
            revision=entry["revision"], cache_dir=args.cache_dir, token=False,
            allow_patterns=[row["filename"] for row in entry["files"]], local_files_only=args.offline))
        if snapshot.name != entry["revision"]:
            raise ValueError("Resolved snapshot differs from the fixed revision")
        for row in entry["files"]:
            if (snapshot / row["filename"]).stat().st_size != row["bytes"]:
                raise ValueError("Downloaded model file size differs from recorded snapshot")
        print(json.dumps({"role": entry["role"], "repo_id": entry["repo_id"], "revision": snapshot.name,
                          "files": len(entry["files"]), "bytes": entry["expected_download_bytes"],
                          "offline": args.offline}))


if __name__ == "__main__":
    main()
