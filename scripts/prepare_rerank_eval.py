"""Freeze a bounded real-corpus slice and private, separately stored span labels.

This does not generate labels from model output. An annotator provides local JSONL
records with id/question/answer/split and evidence [{doc_id, quote, occurrence?}].
Questions and reference labels are then written to different files. Original
corpus text, annotations, questions and outputs must stay in Git-ignored data/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rag_agent.data import DocumentStore
from rag_agent.data.prepare import CORPUS_ID, prepare_hf
from rag_agent.data.store import chunk_document
from rag_agent.evaluation.io import file_sha256, iter_jsonl
from rag_agent.schemas import Document

REVISION = "b27b02bc3e45511b8b82a13e6f90ce761df726f6"


def bounded_copy(source_path: str, target_path: str, max_doc_chars: int = 100000) -> dict:
    """Deterministic resource bound; preserve whole documents and chunk settings."""
    if not Path(source_path).is_file():
        raise FileNotFoundError(source_path)
    if max_doc_chars < 1 or Path(source_path).resolve() == Path(target_path).resolve():
        raise ValueError("Use distinct stores and a positive whole-document length cap")
    source = DocumentStore(source_path)
    target = DocumentStore(target_path)
    try:
        meta = source.metadata
        provenance = {**meta["source"], "selection": "complete documents with len(text) <= max_doc_chars",
                      "max_doc_chars": max_doc_chars, "parent_fingerprint": source.fingerprint,
                      "parent_document_count": source.count}
        # Python len matches the chunk-coordinate contract, including embedded NUL;
        # SQLite length(TEXT) would stop counting at a NUL character.
        docs = (Document(**dict(row)) for row in source.conn.execute(
            "SELECT doc_id,text,url FROM documents ORDER BY rowid") if len(row["text"]) <= max_doc_chars)
        return target.import_documents(docs, meta["chunking"]["size"], meta["chunking"]["overlap"], provenance)
    finally:
        source.close()
        target.close()


def _jsonl(rows):
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def _save_frozen(path, content):
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError(f"Frozen artifact differs: {path}; choose a new output directory")
    path.write_text(content, encoding="utf-8")


def freeze_annotations(store_path: str, annotation_path: str, output_dir: str) -> dict:
    """Resolve unique quotes to original Python-character spans before scoring."""
    if not Path(store_path).is_file():
        raise FileNotFoundError(store_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    store = DocumentStore(store_path)
    try:
        meta = store.metadata
        if meta.get("source", {}).get("dataset") != CORPUS_ID:
            raise ValueError("Expected the actual BrowseComp-Plus corpus")
        if not store.fingerprint:
            raise ValueError("Corpus import must be complete")
        rows = list(iter_jsonl(annotation_path))
        questions, labels, seen = [], [], set()
        for row in rows:
            key = row["id"]
            if not isinstance(key, str) or not key or key in seen:
                raise ValueError("Annotation IDs must be unique nonempty strings")
            seen.add(key)
            if row["split"] not in {"dev", "heldout"}:
                raise ValueError("Every query needs a frozen dev/heldout split")
            if not isinstance(row["question"], str) or not row["question"].strip():
                raise ValueError("Questions must be nonempty strings")
            if not isinstance(row["answer"], str) or not row["answer"].strip():
                raise ValueError("Answers must be nonempty strings")
            spans = []
            for annotation in row["evidence"]:
                doc = store.get(annotation["doc_id"])
                quote = annotation["quote"]
                if doc is None or not isinstance(quote, str) or not quote:
                    raise ValueError(f"Invalid evidence for {key}")
                starts, pos = [], 0
                while (pos := doc.text.find(quote, pos)) >= 0:
                    starts.append(pos)
                    pos += 1
                occurrence = annotation.get("occurrence")
                if occurrence is None and len(starts) != 1:
                    raise ValueError(f"{key}: quote has {len(starts)} matches; disambiguate explicitly")
                occurrence = 0 if occurrence is None else occurrence
                if isinstance(occurrence, bool) or not isinstance(occurrence, int) or not 0 <= occurrence < len(starts):
                    raise ValueError(f"{key}: invalid quote occurrence")
                start = starts[occurrence]
                end = start + len(quote)
                chunks = list(chunk_document(doc, meta["chunking"]["size"], meta["chunking"]["overlap"]))
                containing = [c.chunk_id for c in chunks if c.offset <= start and c.offset + len(c.text) >= end]
                if not containing:
                    raise ValueError(f"{key}: evidence crosses all original chunks; choose an independently sufficient shorter quote")
                spans.append({"doc_id": doc.doc_id, "start": start, "end": end,
                              "text_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                              "containing_source_chunk_ids": containing})
            if not spans:
                raise ValueError(f"{key}: at least one evidence span required")
            questions.append({"id": key, "question": row["question"]})
            labels.append({"id": key, "split": row["split"], "answer": row["answer"],
                           "topic_group": row.get("topic_group", key),
                           "evidence": spans, "doc_ids": list(dict.fromkeys(x["doc_id"] for x in spans)),
                           "label_scope": "partial_manual_sufficient_spans"})
        if not labels:
            raise ValueError("At least one annotation is required")
        split_docs = {split: {doc for row in labels if row["split"] == split for doc in row["doc_ids"]}
                      for split in ("dev", "heldout")}
        split_topics = {split: {row["topic_group"] for row in labels if row["split"] == split}
                        for split in ("dev", "heldout")}
        if split_docs["dev"] & split_docs["heldout"] or split_topics["dev"] & split_topics["heldout"]:
            raise ValueError("Dev and heldout must use disjoint labelled documents and topic groups")
        for name, values in [("questions.jsonl", questions), ("labels.jsonl", labels)]:
            _save_frozen(output / name, _jsonl(values))
        for split in ("dev", "heldout"):
            ids = {row["id"] for row in labels if row["split"] == split}
            _save_frozen(output / f"questions-{split}.jsonl", _jsonl([q for q in questions if q["id"] in ids]))
            _save_frozen(output / f"labels-{split}.jsonl", _jsonl([q for q in labels if q["id"] in ids]))
        manifest = {
            "format_version": 1, "dataset": CORPUS_ID, "source": meta["source"],
            "store_path": str(Path(store_path)), "corpus_fingerprint": store.fingerprint,
            "document_count": store.count, "chunk_count": store.chunk_count, "chunking": meta["chunking"],
            "document_ids": [row[0] for row in store.conn.execute("SELECT doc_id FROM documents ORDER BY rowid")],
            "query_ids": [q["id"] for q in questions],
            "splits": {split: [q["id"] for q in labels if q["split"] == split] for split in ("dev", "heldout")},
            "topic_groups": {split: sorted({q["topic_group"] for q in labels if q["split"] == split})
                             for split in ("dev", "heldout")},
            "annotation_sha256": file_sha256(annotation_path),
            "questions_sha256": file_sha256(output / "questions.jsonl"),
            "labels_sha256": file_sha256(output / "labels.jsonl"),
            "evidence_hit_rule": "same doc_id and candidate.start <= span.start and candidate.end >= span.end; any sufficient annotated span counts",
            "doc_relevance_rule": "same doc_id as any annotated sufficient span; separate from span containment",
            "cross_chunk_rule": "annotations must fit a source chunk; returned dense subwindows still require full span containment",
            "label_scope": "partial manual labels; unlabelled passages are unknown, not proven irrelevant",
            "query_scope": "author-written factual questions on a deterministic bounded real corpus, not official course validation questions",
            "sampling_rule": "first N documents in immutable HF train order, then optional whole-document length cap in source metadata; no selection using retrieval scores",
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
        }
        try:
            manifest["git_sha_at_freeze"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            manifest["git_sha_at_freeze"] = None
        manifest_path = output / "manifest.json"
        if manifest_path.exists():
            old = json.loads(manifest_path.read_text())
            # These describe the original freeze, not the identity of its inputs.
            # A later install/commit must not prevent reuse of identical data.
            provenance_keys = {"frozen_at_utc", "git_sha_at_freeze", "environment"}
            if ({k: v for k, v in old.items() if k not in provenance_keys}
                    != {k: v for k, v in manifest.items() if k not in provenance_keys}):
                raise ValueError("Frozen manifest differs; choose a new output directory")
            return old
        manifest["frozen_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default="data/rerank-eval/documents.sqlite")
    parser.add_argument("--output", default="data/rerank-eval")
    parser.add_argument("--annotations", help="Private, manually reviewed JSONL; never passed to the search service")
    parser.add_argument("--prepare-corpus", action="store_true")
    parser.add_argument("--bounded-from", help="Copy whole documents from this imported store into --store")
    parser.add_argument("--max-doc-chars", type=int, default=100000)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args()
    if args.prepare_corpus:
        print(json.dumps(prepare_hf(args.store, revision=args.revision, limit=args.limit,
                                   cache_dir="data/cache"), indent=2))
    if args.bounded_from:
        print(json.dumps(bounded_copy(args.bounded_from, args.store, args.max_doc_chars), indent=2))
    if args.annotations:
        result = freeze_annotations(args.store, args.annotations, args.output)
        print(json.dumps({key: result[key] for key in ("document_count", "chunk_count", "query_ids", "splits")}, indent=2))
    elif not args.prepare_corpus and not args.bounded_from:
        parser.error("Select --prepare-corpus, --bounded-from and/or --annotations")


if __name__ == "__main__":
    main()
