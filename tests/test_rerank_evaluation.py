"""Evaluation accounting and frozen-pool replay, using explicitly fake scores."""
import argparse
import importlib.util
import json
from pathlib import Path

import pytest

from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.retrieval import build_indexes
from rag_agent.schemas import Document, SearchHit

SPEC = importlib.util.spec_from_file_location("evaluate_rerank", Path(__file__).parents[1] / "scripts/evaluate_rerank.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


@pytest.fixture
def store(tmp_path):
    value = DocumentStore(tmp_path / "docs.sqlite")
    value.import_documents([Document(doc_id="d", text="🌙 Alpha result is Copper. " * 6)], 64, 10)
    yield value
    value.close()


def label_for(text, start, end, **updates):
    return {"id": "q", "split": "dev", "answer": "Copper", "doc_ids": ["d"], "label_scope": "partial",
            "evidence": [{"doc_id": "d", "start": start, "end": end,
                          "text_sha256": evaluation.digest_bytes(text[start:end].encode())}], **updates}


def hit(text, start, end, name="c"):
    return SearchHit(doc_id="d", chunk_id=name, offset=start, text=text[start:end], score=1.0, method="hybrid")


def test_full_span_containment_not_doc_or_overlap_union(store):
    text = store.get("d").text
    label = label_for(text, 2, 25)
    wrong_passage = hit(text, 30, 50, "wrong")
    good = hit(text, 0, 30, "good")
    metrics = evaluation.evaluate_ranking([wrong_passage, good], [good, wrong_passage], label, store, 1)
    assert metrics["document_hit_at_k"] is True
    assert metrics["evidence_hit_at_k"] is False
    assert metrics["evidence_mrr"] == .5
    assert metrics["evidence_candidate_hit"] is True
    assert metrics["category"] == "ranking_miss"
    split = [hit(text, 0, 15, "part1"), hit(text, 10, 30, "part2")]
    metrics = evaluation.evaluate_ranking(split, split, label, store, 5)
    assert metrics["category"] == "candidate_miss"
    assert metrics["document_hit_at_k"] is True


def test_missing_and_invalid_labels_are_distinct(store):
    text = store.get("d").text
    label = label_for(text, 2, 25)
    label["evidence"][0]["doc_id"] = "absent"
    metrics = evaluation.evaluate_ranking([], [], label, store, 5)
    assert metrics["category"] == "corpus_coverage_missing"
    assert metrics["missing_span_labels"] == 1
    label["evidence"][0]["doc_id"] = "d"
    label["evidence"][0]["text_sha256"] = "corrupt"
    assert evaluation.evaluate_ranking([], [], label, store, 5)["category"] == "invalid_label"
    assert evaluation.evaluate_ranking([], [], None, store, 5)["category"] == "unlabeled"


def test_summary_does_not_call_fallback_success():
    success = {"status": "success", "metrics": {"annotation_available": True, "category": "evidence_in_top_k",
        "evidence_hit_at_k": True, "evidence_mrr": 1.0, "evidence_first_rank": 1}, "timing": {"total_seconds": .1}}
    fallback = {**success, "status": "fallback_rrf", "diagnostics": {"status": "fallback_rrf"}}
    summary = evaluation.summarize([{"id": "q", "groups": {"A": success, "B": success, "C": fallback}}], ["q"])
    assert summary["paired"]["C_vs_B"]["valid_pairs"] == 0
    assert summary["groups"]["C"]["fallbacks"] == 1
    assert summary["groups"]["C"]["success"] == 0
    assert summary["failures"][0]["status"] == "fallback_rrf"


class FakeReranker:
    calls = 0

    def __init__(self, settings):
        self.settings = settings
        self.last_diagnostics = {}

    def rerank(self, query, hits, top_k):
        assert "Copper" not in query  # The answer belongs only to labels/corpus.
        type(self).calls += 1
        self.last_diagnostics = {"status": "success", "model": {"backend": "injected_test_stub"},
                                 "scored_candidates": len(hits)}
        return list(reversed(hits)), self.last_diagnostics


def test_capture_resume_and_replay_preserve_pool_identity(tmp_path, monkeypatch):
    config = Settings(method="sparse", store_path=str(tmp_path / "docs.sqlite"),
                      index_dir=str(tmp_path / "indexes"), chunk_size=64, chunk_overlap=10)
    source = DocumentStore(config.store_path)
    text = "Alpha result is Copper. " * 6
    source.import_documents([Document(doc_id="d", text=text)], 64, 10)
    source.close()
    build_indexes(config, ["sparse"])
    cfg = tmp_path / "config.json"
    cfg.write_text(config.model_dump_json())
    questions, labels = tmp_path / "questions.jsonl", tmp_path / "labels.jsonl"
    questions.write_text(json.dumps({"id": "q", "question": "What is Alpha result?"}) + "\n")
    labels.write_text(json.dumps(label_for(text, 0, 23)) + "\n")
    monkeypatch.setattr(evaluation, "LocalCrossEncoder", FakeReranker)
    args = argparse.Namespace(config=cfg, questions=questions, labels=labels, output=tmp_path / "first",
                              split="dev", candidate_depth=50, rerank_depth=30, replay=None, rerun_failed=False)
    result = evaluation.run(args)
    assert result["samples"] == 1 and not result["failures"]
    row = json.loads((args.output / "queries" / evaluation.sample_file("q")).read_text())
    assert row["groups"]["B"]["pool_sha256"] == row["groups"]["C"]["pool_sha256"]
    calls = FakeReranker.calls
    assert evaluation.run(args) == result
    assert FakeReranker.calls == calls
    args = argparse.Namespace(**{**vars(args), "output": tmp_path / "second", "replay": args.output, "rerank_depth": 10})
    replay = evaluation.run(args)
    assert not replay["failures"]
    row2 = json.loads((args.output / "queries" / evaluation.sample_file("q")).read_text())
    assert row2["groups"]["B"]["pool_sha256"] == row["groups"]["B"]["pool_sha256"]
    assert row2["groups"]["B"]["timing"]["retrieval_timing_reused"] is True
    questions.write_text(json.dumps({"id": "q", "question": "Changed question"}) + "\n")
    with pytest.raises(ValueError, match="Resume identity mismatch"):
        evaluation.run(args)
