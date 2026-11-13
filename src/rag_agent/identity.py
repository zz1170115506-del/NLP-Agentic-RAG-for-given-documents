"""Bind resumable runs to executable code and the actual corpus/index artifacts."""
import hashlib
import json
from pathlib import Path
import sqlite3
import importlib.util


def runtime_identity(settings):
    digest = hashlib.sha256()
    peer = importlib.util.find_spec("search_agent")
    packages = [Path(__file__).resolve().parent]
    if peer and peer.origin:
        packages.append(Path(peer.origin).parent)
    for package in packages:
        for path in sorted(package.rglob("*.py")):
            digest.update((package.name + "/" + str(path.relative_to(package))).encode())
            digest.update(path.read_bytes())
    corpus = {"missing": True}
    store = Path(settings.store_path).resolve()
    if store.is_file():
        with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as conn:
            corpus = {key: json.loads(value) for key, value in conn.execute("SELECT key,value FROM metadata")}
        if corpus.get("importing"):
            raise ValueError("Cannot bind a batch to an incomplete corpus import")
    indexes = {}
    target = Path(settings.index_dir)
    for path in sorted(target.glob("*/manifest.json")):
        indexes[str(path.relative_to(target))] = hashlib.sha256(path.read_bytes()).hexdigest()
    sparse = target / "sparse.sqlite"
    if sparse.is_file():
        # Include header identity without scanning a multi-GB FTS index every batch.
        with sqlite3.connect(sparse.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            indexes["sparse"] = [list(row) for row in conn.execute("SELECT * FROM metadata ORDER BY key")]
    return {"code_sha256": digest.hexdigest(), "corpus": corpus, "indexes": indexes}
