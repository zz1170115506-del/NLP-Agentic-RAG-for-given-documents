"""Synthetic protocol/provenance regressions; never benchmark or live API evidence."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.evaluation.batch import batch_predict
from rag_agent.evaluation.validate import validate_record
from rag_agent.evidence import resolve_evidence_ids
from rag_agent.retrieval import build_indexes
from rag_agent.runtime import make_runtime, run_question
from rag_agent.schemas import Question
from search_agent.final_output import parse_final_object


def protocol_run(tmp_path, monkeypatch, engine, *, settings_updates=None, usage=None):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("LLM_API_KEY", "synthetic-key-not-a-real-credential")
    config = Settings(agent_engine=engine, method="sparse", store_path=str(tmp_path / "corpus.sqlite"),
                      index_dir=str(tmp_path / "index"), skills_dir=str(root / "skills"),
                      llm_base_url="https://protocol.example/v1", llm_model="synthetic-flash-deployment",
                      model_verified=True, model_verification_note="Synthetic protocol fixture; no API contacted",
                      use_skills=False, max_retries=0)
    if settings_updates:
        config = config.model_copy(update=settings_updates)
    store = DocumentStore(config.store_path)
    store.import_documents(iter_jsonl(root / "tests/fixtures/corpus.jsonl"))
    store.close()
    build_indexes(config, ["sparse"])
    requests = []

    def post(self, url, *, json, **kwargs):
        requests.append(copy.deepcopy(json))
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "actual-provider-call-id",
                       "type": "function", "function": {"name": "search", "arguments": '{"query":"Copper Museum","top_k":2}'}}]}
        else:
            # Both engines use IDs from the real local tool result, not retyped offsets.
            message = {"role": "assistant", "content": '{"answer":"1984","supporting_evidence":["E1"]}'}
        return httpx.Response(200, json={"model": config.llm_model, "usage": usage or {"total_tokens": 11},
                                         "choices": [{"message": message, "finish_reason": "stop"}]})

    monkeypatch.setattr(httpx.Client, "post", post)
    store, search = make_runtime(config)
    try:
        result = run_question(Question(id="synthetic-1", question="When did the Copper Museum open?"),
                              config, store=store, search=search)
    finally:
        store.close()
        search.close()
    return result, config, requests


@pytest.mark.parametrize("engine", ["baseline", "agent12"])
def test_id_contract_and_actual_provider_call_ids(tmp_path, monkeypatch, engine):
    result, _, requests = protocol_run(tmp_path, monkeypatch, engine)
    prediction = result.prediction
    assert result.eligible and prediction.answer == "1984"
    assert prediction.total_tokens == 22 and prediction.tool_calls == 1
    assert not validate_record(prediction, formal=True, check_grounding=True)
    call = next(row for row in prediction.trajectory if row.get("role") == "assistant")
    assert call["tool_calls"][0]["id"] == "actual-provider-call-id"
    assert "E1" in json.dumps(requests[1]["messages"])
    assert "synthetic-key-not-a-real-credential" not in prediction.model_dump_json()


@pytest.mark.parametrize("engine", ["baseline", "agent12"])
def test_budget_reserve_requests_a_real_final_answer_with_tools_disabled(tmp_path, monkeypatch, engine):
    result, _, requests = protocol_run(tmp_path, monkeypatch, engine,
        settings_updates={"graceful_finalization": True, "max_total_tokens": 1500, "max_output_tokens": 64},
        usage={"total_tokens": 700, "prompt_tokens": 600, "completion_tokens": 100})
    assert len(requests) == 2
    assert requests[0]["tool_choice"] == "auto" and requests[1]["tool_choice"] == "none"
    assert result.prediction.answer == "1984" and result.prediction.total_tokens == 1400
    assert result.state.stop_reason == "completed"
    assert validate_record(result.prediction, formal=True, check_grounding=True) == []


@pytest.mark.parametrize("mutation,expected", [
    ("unknown_id", "Unknown"), ("duplicate_id", "Duplicate"),
    ("offset", "never shown"), ("missing_tool", "missing tool results"),
    ("missing_usage", "reliable API usage"), ("fake_http", "raw response"),
    ("changed_raw_response", "differs from its raw HTTP response"),
    ("malformed_request", "request"),
])
def test_bad_provenance_and_accounting_are_rejected(tmp_path, monkeypatch, mutation, expected):
    result, _, _ = protocol_run(tmp_path, monkeypatch, "agent12")
    prediction = result.prediction.model_copy(deep=True)
    final = [row for row in prediction.trajectory if row.get("role") == "assistant"][-1]
    if mutation in {"unknown_id", "duplicate_id"}:
        data = json.loads(final["content"])
        data["supporting_evidence"] = ["E999"] if mutation == "unknown_id" else ["E1", "E1"]
        final["content"] = json.dumps(data)
    elif mutation == "offset":
        tool = next(row for row in prediction.trajectory if row.get("role") == "tool")
        data = json.loads(tool["content"])
        data["results"][0]["start"] += 1
        data["results"][0]["end"] += 1
        tool["content"] = json.dumps(data)
    elif mutation == "missing_tool":
        prediction.trajectory = [row for row in prediction.trajectory if row.get("role") != "tool"]
    elif mutation == "missing_usage":
        final["usage"] = None
        prediction.total_tokens -= 11
    elif mutation == "fake_http":
        next(row for row in prediction.trajectory if row.get("event") == "api_attempt").pop("response")
    elif mutation == "changed_raw_response":
        next(row for row in prediction.trajectory if row.get("event") == "api_attempt")["response"]["usage"]["total_tokens"] += 1
    elif mutation == "malformed_request":
        next(row for row in prediction.trajectory if row.get("event") == "request")["messages"] = [None]
    errors = validate_record(prediction, formal=True, check_grounding=True)
    assert any(expected in error for error in errors), errors


def test_course_validity_and_citation_quality_are_separate(tmp_path, monkeypatch):
    result, _, _ = protocol_run(tmp_path, monkeypatch, "baseline")
    prediction = result.prediction
    final = [row for row in prediction.trajectory if row.get("role") == "assistant"][-1]
    raw = [row for row in prediction.trajectory if row.get("event") == "api_attempt"][-1]["response"]
    content = '{"answer":"a wrong synthetic answer","supporting_evidence":[]}'
    final["content"] = raw["choices"][0]["message"]["content"] = content
    prediction.answer = "a wrong synthetic answer"
    prediction.trajectory[-1]["eligible"] = False  # A project quality flag is not a course rule.
    assert validate_record(prediction, formal=True) == []
    assert any("inspected evidence" in e for e in validate_record(prediction, formal=True, check_grounding=True))


def test_context_compaction_resolves_only_visible_range():
    full = {"doc_id": "same-doc", "chunk_id": "c1", "evidence_id": "E1", "start": 4,
            "end": 1204, "text": "原" * 1200, "source_url": "https://synthetic.example/doc"}
    other = {**full, "chunk_id": "c2", "evidence_id": "E2", "start": 1404, "end": 2604}
    shown = {**full, "text": full["text"][:900], "visible_text_end": 904}
    calls = [{"id": "s1", "function": {"name": "search", "arguments": "{}"}}]
    trajectory = [{"role": "assistant", "tool_calls": calls},
                  {"role": "tool", "tool_call_id": "s1", "content": json.dumps({"results": [full, other]})},
                  {"event": "request", "messages": [{"role": "user", "content": json.dumps({"evidence": [shown, other]})}]}]
    resolved = resolve_evidence_ids(["E1", "E2"], trajectory)
    assert [(x["offset"], x["end"]) for x in resolved] == [(4, 904), (1404, 2604)]
    assert len(resolved[0]["text"]) == 900
    opened = {k: v for k, v in full.items() if k != "chunk_id"}
    reopened = [{"role": "assistant", "tool_calls": [{"id": "o1", "function": {"name": "open_document", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "o1", "content": json.dumps(opened)}]
    assert resolve_evidence_ids(["E1"], trajectory + reopened)[0]["end"] == 904
    with pytest.raises(ValueError, match="never shown"):
        resolve_evidence_ids(["E1"], trajectory[:2])


def test_final_json_extraction_preserves_model_values_and_rejects_ambiguity():
    content = 'The inspected document states the date.\n\n{"answer":"1984","supporting_evidence":["E1"]}'
    assert parse_final_object(content) == {"answer": "1984", "supporting_evidence": ["E1"]}
    for malformed in ['{"answer":"x", "nested":{"answer":"y"}',
                      'Example {"answer":"x"} Final {"answer":"y"}',
                      'No JSON here', '[{"answer":"x"}]']:
        with pytest.raises(ValueError):
            parse_final_object(malformed)


def test_bounded_batch_resume_and_changed_index_identity(tmp_path, monkeypatch):
    result, settings, _ = protocol_run(tmp_path, monkeypatch, "baseline")
    source, output = tmp_path / "questions.jsonl", tmp_path / "predictions.jsonl"
    source.write_text(''.join(json.dumps({"id": str(i), "question": "synthetic question"}) + '\n' for i in range(3)))
    seen = []

    def runner(question, config):
        seen.append(question.id)
        run = result.model_copy(deep=True)
        run.prediction.id, run.prediction.question = question.id, question.question
        return run

    first = batch_predict(source, output, settings, runner, max_questions=1)
    assert first["records"] == 1
    second = batch_predict(source, output, settings, runner, max_questions=1)
    assert second["records"] == 2 and seen == ["0", "1"]
    third = batch_predict(source, output, settings, runner)
    assert third["records"] == 3 and seen == ["0", "1", "2"]
    import sqlite3
    with sqlite3.connect(Path(settings.index_dir) / "sparse.sqlite") as conn:
        conn.execute("UPDATE metadata SET value='different-index' WHERE key='fingerprint'")
    with pytest.raises(ValueError, match="mismatch"):
        batch_predict(source, output, settings, runner)


def test_actual_process_interruption_preserves_completed_question(tmp_path):
    import os
    import subprocess
    import sys
    import time
    root = Path(__file__).resolve().parents[1]
    settings = Settings(mode="demo", method="sparse", store_path=str(tmp_path / "store.sqlite"),
                        index_dir=str(tmp_path / "index"), skills_dir=str(root / "skills"))
    store = DocumentStore(settings.store_path)
    store.import_documents(iter_jsonl(root / "tests/fixtures/corpus.jsonl"))
    store.close()
    build_indexes(settings, ["sparse"])
    source, output, config, marker = [tmp_path / name for name in ("input.jsonl", "output.jsonl", "config.json", "entered-second")]
    config.write_text(settings.model_dump_json())
    source.write_text(''.join(json.dumps({"id": str(i), "question": "When did the Copper Museum open?"}) + '\n' for i in range(2)))
    code = '''
import signal,sys
from pathlib import Path
from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.runtime import make_runtime,run_question
source,output,config,marker=sys.argv[1:]
cfg=Settings.model_validate_json(Path(config).read_text())
store,search=make_runtime(cfg)
def runner(question,settings):
    if question.id=='1':
        Path(marker).touch()
        signal.pause()
    return run_question(question,settings,store=store,search=search)
batch_predict(source,output,cfg,runner)
'''
    child = subprocess.Popen([sys.executable, "-c", code, str(source), str(output), str(config), str(marker)],
                             env={**os.environ, "PYTHONPATH": str(root / "src") + os.pathsep + str(root / "agent12")})
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.exists()
    finally:
        child.terminate()
        child.wait(timeout=5)
    assert len(output.read_text().splitlines()) == 1
    store, search = make_runtime(settings)
    try:
        summary = batch_predict(source, output, settings, lambda q, c: run_question(q, c, store=store, search=search))
    finally:
        store.close()
        search.close()
    assert summary["skipped"] == 1 and summary["attempted_this_run"] == 1
    assert summary["records"] == 2 and summary["completed"] == 2


def test_neural_checkpoint_remains_incomplete_and_resumes(tmp_path, monkeypatch):
    import numpy as np
    from rag_agent.retrieval import dense
    from rag_agent.schemas import Document
    monkeypatch.setattr(dense, "SHARD_CHUNKS", 2)
    config = Settings(chunk_size=64, chunk_overlap=0, store_path=str(tmp_path / "store.sqlite"))
    store = DocumentStore(config.store_path)
    store.import_documents([Document(doc_id="synthetic", text="some test words " * 40)], 64, 0)

    class SyntheticEmbedder:
        resolved_revision = "synthetic-vector-fixture"
        dimension = 2

        def segments(self, chunk):
            yield chunk

        def encode(self, texts, query=False):
            return np.ones((len(texts), 2), dtype="float32")

    model, target = SyntheticEmbedder(), tmp_path / "vectors"
    first = dense.build_dense(config, store, target, "encoder", embedder=model, max_new_shards=1)
    assert not first["ready"] and first["source_chunk_count"] == 2
    with pytest.raises(ValueError, match="incomplete"):
        dense.DenseRetriever(config, store, target, "encoder", embedder=model)
    before = (target / first["shards"][0]["vectors"]).stat().st_mtime_ns
    second = dense.build_dense(config, store, target, "encoder", embedder=model, max_new_shards=1)
    assert not second["ready"] and second["source_chunk_count"] == 4
    assert (target / first["shards"][0]["vectors"]).stat().st_mtime_ns == before
    final = dense.build_dense(config, store, target, "encoder", embedder=model)
    assert final["ready"] and final["source_chunk_count"] == store.chunk_count
    store.close()
