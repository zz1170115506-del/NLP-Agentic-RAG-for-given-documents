"""Build the supplied 1.1 BM25 implementation on declared synthetic documents.

No API, embedding downloads, or changes to the teammate's source are needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from search_agent.peer import import_peer


def prepare(project_dir, output_dir):
    project, settings_class, _ = import_peer(project_dir)
    from rag_agent.data.store import DocumentStore
    from rag_agent.schemas import Document
    from rag_agent.retrieval import build_indexes

    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    documents = [
        Document(doc_id="d1", text="The Lumen Observatory was designed by Mira Sol. Mira Sol studied at Cedar University."),
        Document(doc_id="d2", text="Cedar University is located in Northport. The university opened in 1968."),
        Document(doc_id="d3", text="The Copper Museum opened in 1984. Its architect was Tomas Reed."),
        Document(doc_id="two-facts", text=("Helion Museum was founded by Nara Vale. " + "Historical archive. " * 22
                                         + "Helion Museum opened to the public in 1977.")),
        Document(doc_id="long-register", text=("Cedarwatch Observatory was founded by Elara Venn. "
                                              + "Routine archive entry. " * 700)),
        Document(doc_id="repeated-phrase", text="Inspection marker. " * 600),
    ]
    settings = settings_class(store_path=str(output / "documents.sqlite"), index_dir=str(output / "indexes"),
                              skills_dir=str(project / "skills"), method="sparse", chunk_size=256, chunk_overlap=40)
    store = DocumentStore(settings.store_path)
    try:
        metadata = store.import_documents(documents, settings.chunk_size, settings.chunk_overlap,
            source={"type": "synthetic_agent12_integration", "synthetic": True,
                    "note": "First three documents follow the supplied 1.1 tests; all facts are fictional."})
    finally:
        store.close()
    built = build_indexes(settings, ["sparse"])
    config = output / "peer-config.json"
    config.write_text(json.dumps({key: getattr(settings, key) for key in
                     ("store_path", "index_dir", "skills_dir", "method", "chunk_size", "chunk_overlap")}, indent=2), encoding="utf-8")
    summary = {"synthetic": True, "peer_project": str(project), "config": str(config),
               "corpus": metadata, "built_methods": list(built), "api_calls": 0}
    (output / "preparation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer-project", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "peer12_sample")
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.peer_project, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
