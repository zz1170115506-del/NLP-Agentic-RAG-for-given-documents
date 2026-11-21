"""Synthetic official-alias recovery cases; these tests never call the API."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.evaluation.io import read_predictions
from rag_agent.evaluation.validate import validate_record
from rag_agent.schemas import AgentState, RunResult
from test_evaluation import make_prediction


def compat_prediction(question, settings, *, abstain=False, failed=False):
    prediction = make_prediction(question, settings, live=True, failed=failed)
    trace = prediction.trajectory
    trace[0]["audit_version"] = 2
    trace[-1]["eligible"] = False
    if abstain:
        prediction.answer = ""
        trace[-2]["content"] = '{"answer":"","supporting_evidence":[]}'
        trace[-1]["status"] = "insufficient_evidence"
    for event in trace:
        if event.get("role") == "assistant":
            event["model"] = "deepseek-flash"
        if event.get("event") == "request":
            event.update(tools=[], max_tokens=64)
    for index, event in enumerate(trace):
        if event.get("event") != "api_attempt":
            continue
        context, assistant = trace[index - 1], trace[index + 1]
        event["request"].update(tools=[], max_tokens=64)
        event["response"] = {
            "model": assistant["model"], "usage": copy.deepcopy(assistant["usage"]),
            "choices": [{"message": {k: copy.deepcopy(v) for k, v in assistant.items()
                                      if k in {"role", "content", "tool_calls"}}}],
        }
        assert event["request"]["messages"] == context["messages"]
    return prediction


def fixture(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/recover_predictions.py"
    spec = importlib.util.spec_from_file_location("compat_recovery", path)
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    cfg = Settings(model_policy="official_compat", llm_model="deepseek-v4-flash", model_verified=False,
                   model_verification_note="Synthetic fixture; not a real model identity assertion.",
                   store_path=str(tmp_path / "absent.sqlite"), index_dir=str(tmp_path / "absent-index"))
    source, output = tmp_path / "input.jsonl", tmp_path / "predictions.jsonl"
    source.write_text(''.join(json.dumps({"id": str(i), "question": "Synthetic campus hall?"}) + '\n'
                              for i in range(1, 5)))

    def initial(question, settings):
        prediction = compat_prediction(question, settings, abstain=question.id == "2", failed=question.id == "3")
        return RunResult(prediction=prediction, state=AgentState(question=question), mode="live")

    batch_predict(source, output, cfg, initial, max_questions=3)
    return recovery, cfg, source, output


def test_official_recovery_preserves_answers_and_honest_abstentions(tmp_path):
    recovery, cfg, source, output = fixture(tmp_path)
    before = {row.id: row.model_dump() for row in read_predictions(output)}
    dry = recovery.recover(source, output, cfg, dry_run=True)
    assert dry["valid_existing"] == 2 and dry["pending"] == 2
    called = []

    def runner(question, settings):
        called.append(question.id)
        return RunResult(prediction=compat_prediction(question, settings), state=AgentState(question=question), mode="live")

    result = recovery.recover(source, output, cfg, runner=runner)
    assert called == ["3", "4"]
    assert result["validation"]["valid"] and result["validation"]["official_compat"]
    after = {row.id: row.model_dump() for row in read_predictions(output)}
    assert before["1"] == after["1"] and before["2"] == after["2"]
    archived = [json.loads(line) for line in Path(str(output) + ".attempts.jsonl").read_text().splitlines()]
    assert len(archived) == 1 and archived[0]["prediction"] == before["3"]
    assert recovery.recover(source, output, cfg, dry_run=True)["pending"] == 0


def test_official_batch_rerun_failed_keeps_audited_abstention(tmp_path):
    _, cfg, source, output = fixture(tmp_path)
    called = []

    def runner(question, settings):
        called.append(question.id)
        return RunResult(prediction=compat_prediction(question, settings), state=AgentState(question=question), mode="live")

    batch_predict(source, output, cfg, runner, rerun_failed=True)
    assert called == ["3", "4"]


@pytest.mark.parametrize("damage", ["missing_raw", "tampered_model", "missing_usage", "unknown_usage", "claimed_original"])
def test_compatibility_audit_does_not_accept_damaged_evidence(tmp_path, damage):
    _, _, _, output = fixture(tmp_path)
    prediction = read_predictions(output)[0]
    assert not validate_record(prediction, official_compat=True)
    assert validate_record(prediction, formal=True)
    if damage == "missing_raw":
        del prediction.trajectory[3]["response"]
    elif damage == "tampered_model":
        prediction.trajectory[3]["response"]["model"] = "not-the-recorded-response"
    elif damage == "missing_usage":
        del prediction.trajectory[4]["usage"]
    elif damage == "unknown_usage":
        prediction.trajectory[3]["usage_unknown"] = True
    else:
        prediction.trajectory[0]["model_verified"] = True
    assert validate_record(prediction, official_compat=True)
