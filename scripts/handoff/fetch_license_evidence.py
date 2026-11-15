"""Fetch only small license/model-card files at immutable upstream revisions.

No credentials, model weights, corpus text, or course questions are requested.
Run from the code root: python scripts/handoff/fetch_license_evidence.py
"""
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from handoff_paths import documentation_dir

SOURCES = [
    ("corpus", "dataset", "Tevatron/browsecomp-plus-corpus", "b27b02bc3e45511b8b82a13e6f90ce761df726f6"),
    ("validation", "dataset", "HongruCai/COMP5423-BrowseComp-Plus-Val", "277d3b49913c176976e8b40b7df55b00212cf158"),
    ("test", "dataset", "HongruCai/COMP5423-BrowseComp-Plus-Test", "9cb2f4b9758f97c8bb4275c6d81f8d134bb3eadb"),
    ("encoder", "model", "intfloat/e5-small-v2", "ffb93f3bd4047442299a41ebb6fa998a38507c52"),
    ("instruction", "model", "Qwen/Qwen3-Embedding-0.6B", "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"),
    ("reranker", "model", "cross-encoder/ms-marco-MiniLM-L6-v2", "233902d25c440f23af6f7d6e94d2946bac0bee0a"),
]
NAMES = ("README.md", "LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE", "NOTICE.txt")


def main():
    destination = documentation_dir() / "licenses"
    destination.mkdir(exist_ok=True)
    records = []
    for key, kind, repo, revision in SOURCES:
        folder = destination / key
        folder.mkdir(exist_ok=True)
        prefix = "datasets/" if kind == "dataset" else ""
        for name in NAMES:
            url = f"https://huggingface.co/{prefix}{repo}/resolve/{revision}/{name}"
            record = {"source": key, "repo_id": repo, "repo_type": kind,
                      "revision": revision, "filename": name, "url": url}
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "course-rag-license-audit/1.0"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    content = response.read(1_048_577)
                    if len(content) > 1_048_576:
                        raise ValueError("Unexpectedly large license/card response")
                    record["http_status"] = response.status
                (folder / name).write_bytes(content)
                record.update(bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
                              saved=f"licenses/{key}/{name}")
            except urllib.error.HTTPError as error:
                record["http_status"] = error.code
            except (OSError, ValueError) as error:
                record["error_type"] = type(error).__name__
            records.append(record)
            print(json.dumps({k: record[k] for k in ("source", "filename", "http_status", "error_type", "sha256") if k in record}), flush=True)
            (destination / "fetch-results.json").write_text(json.dumps({
                "captured_at_utc": datetime.now(timezone.utc).isoformat(), "records": records
            }, indent=2) + "\n")


if __name__ == "__main__":
    main()
