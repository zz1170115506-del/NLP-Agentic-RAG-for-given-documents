"""Partition aggregation must preserve live-audited records and resume identity."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.evaluation.io import read_predictions
from rag_agent.identity import runtime_identity
from rag_agent.schemas import AgentState, RunResult
from test_compat_recovery import compat_prediction


spec = importlib.util.spec_from_file_location("acceptance_batch", Path(__file__).resolve().parents[1] / "scripts/acceptance_batch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def prepared(tmp_path):
    source = tmp_path / "questions.jsonl"
    source.write_text("".join(json.dumps({"id": str(i), "question": "Synthetic campus hall?"}) + "\n" for i in range(4)))
    cfg = Settings(model_policy="official_compat", llm_model="deepseek-v4-flash", model_verified=False,
                   model_verification_note="Synthetic aggregation fixture; no API call.",
                   store_path=str(tmp_path / "missing.sqlite"), index_dir=str(tmp_path / "missing-index"))
    parts = module.partitions(source, tmp_path, 2)
    for input_path, output in parts:
        def runner(question, settings):
            return RunResult(prediction=compat_prediction(question, settings, abstain=question.id == "2"),
                             state=AgentState(question=question), mode="live")
        batch_predict(input_path, output, cfg, runner)
    return source, cfg, parts


def test_merge_keeps_original_records_order_and_resumes_without_calls(tmp_path):
    source, cfg, parts = prepared(tmp_path)
    originals = {row.id: row.model_dump() for _, path in parts for row in read_predictions(path)}
    output = tmp_path / "combined.jsonl"
    audit = module.merge(source, output, parts, cfg, runtime_identity(cfg))
    assert audit["valid"] and audit["records"] == 4
    rows = read_predictions(output)
    assert [row.id for row in rows] == ["0", "1", "2", "3"]
    assert all(row.model_dump() == originals[row.id] for row in rows)
    assert rows[2].answer == ""

    def forbidden(*args):
        raise AssertionError("Already audited aggregates must not make new API calls")

    resumed = batch_predict(source, output, cfg, forbidden, rerun_failed=True)
    assert resumed["attempted_this_run"] == 0 and resumed["skipped"] == 4


def test_merge_rejects_changed_partition_code_identity(tmp_path):
    source, cfg, parts = prepared(tmp_path)
    metadata = Path(str(parts[0][1]) + ".meta.json")
    value = json.loads(metadata.read_text())
    value["runtime_identity"]["code_sha256"] = "different-version"
    metadata.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="execution metadata mismatch"):
        module.merge(source, tmp_path / "combined.jsonl", parts, cfg, runtime_identity(cfg))
    assert not (tmp_path / "combined.jsonl").exists()


def test_prediction_partition_rejects_reference_answers(tmp_path):
    source = tmp_path / "labeled.jsonl"
    source.write_text(json.dumps({"id": "0", "question": "Synthetic?", "answer": "never sent"}) + "\n")
    with pytest.raises(ValueError, match="labels are evaluator-only"):
        module.partitions(source, tmp_path, 2)


def test_last_allowed_round_still_aggregates_completed_records(tmp_path, monkeypatch):
    source, cfg, _ = prepared(tmp_path)
    destination = tmp_path / "coordinator"
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-never-transmitted")
    monkeypatch.setattr(module.Settings, "load", lambda path: cfg)
    monkeypatch.setattr(module, "balance", lambda: {"available": True, "balances": [
        {"currency": "CNY", "total_balance": "5.0"}]})
    monkeypatch.setattr(module, "optional_git_sha", lambda path: None)

    def subprocess_fixture(command, **kwargs):
        input_path = command[command.index("--input") + 1]
        output = command[command.index("--output") + 1]

        def runner(question, settings):
            return RunResult(prediction=compat_prediction(question, settings),
                             state=AgentState(question=question), mode="live")

        batch_predict(input_path, output, cfg, runner, max_questions=2)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", subprocess_fixture)
    monkeypatch.setattr(module.sys, "argv", ["acceptance_batch.py", "--input", str(source),
        "--config", "synthetic", "--output-dir", str(destination), "--workers", "2",
        "--per-round", "2", "--max-rounds", "1"])
    assert module.main() == 0
    assert len(read_predictions(destination / "prediction.jsonl")) == 4
