"""Synthetic records only: these fixtures are not API or benchmark results."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

from rag_agent.config import Settings
from rag_agent.evaluation import batch_predict, evaluate, normalize_answer, read_questions, validate_predictions
from rag_agent.evaluation.io import dump_line
from rag_agent.evaluation.validate import validate_record
from rag_agent.schemas import AgentState, Prediction, Question, RunResult


def make_prediction(question, settings, *, failed=False, live=False):
    # Deliberately constructed fixtures test the validator; never written as results.
    start = {"event": "run_start", "mode": "live" if live else settings.mode, "provider": "http" if live else "scripted", "injected_provider": False, "config_id": settings.config_id, "config": settings.model_dump(), "model": settings.llm_model, "model_verified": settings.model_verified, "model_verification_note": settings.model_verification_note}
    user = {"role": "user", "content": question.question}
    assistant = {"role": "assistant", "content": None, "model": settings.llm_model, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "search", "arguments": '{"query":"synthetic campus"}'}}], "usage": {"total_tokens": 5 if live else 0}}
    citation = {"doc_id": "synthetic-1", "offset": 0, "text": "The fictional campus hall is Aurora Hall."}
    tool = {"role": "tool", "tool_call_id": "c1", "content": json.dumps({"ok": True, "data": {"results": [citation]}})}
    final = {"role": "assistant", "content": json.dumps({"answer": "The Aurora Hall", "evidence": [citation]}), "model": settings.llm_model, "usage": {"total_tokens": 7 if live else 0}}
    first_request = {"event": "request", "messages": [user]}
    second_request = {"event": "request", "messages": [user, {key: val for key, val in assistant.items() if key not in {"usage", "model"}}, tool]}
    def attempt(context):
        return {"event": "api_attempt", "outcome": "received", "http_status": 200, "request": {"messages": context["messages"], "model": settings.llm_model}}
    trajectory = [start, user, first_request, attempt(first_request), assistant, tool, second_request, attempt(second_request), final, {"event": "run_end", "status": "error" if failed else "completed", "eligible": live and not failed, "usage_complete": True}]
    return Prediction(id=question.id, question=question.question, answer="" if failed else "The Aurora Hall", trajectory=trajectory, tool_calls=1, total_tokens=12 if live else 0)


def write_questions(path, rows=None):
    rows = rows or [{"id": "001", "question": "What is the fictional campus hall?", "answer": "Aurora Hall"}]
    path.write_text("".join(dump_line(row) for row in rows))
    return path


def test_labels_removed_and_id_preserved(tmp_path):
    path = write_questions(tmp_path / "input.jsonl")
    question = read_questions(path)[0]
    assert question.id == "001"
    assert question.model_dump() == {"id": "001", "question": "What is the fictional campus hall?"}
    write_questions(path, [{"id": 1, "question": "x"}])
    with pytest.raises(ValueError):
        read_questions(path)
    write_questions(path, [{"id": "1", "question": "x"}, {"id": "1", "question": "y"}])
    with pytest.raises(ValueError, match="duplicate"):
        read_questions(path)


def test_normalized_em_and_failures(tmp_path):
    assert normalize_answer("  The AURORA, Hall! ") == "aurora hall"
    assert normalize_answer("an apple and a pear") == "apple and pear"
    source = write_questions(tmp_path / "input.jsonl")
    settings = Settings(mode="demo")
    prediction = make_prediction(read_questions(source)[0], settings)
    output = tmp_path / "pred.jsonl"
    output.write_text(dump_line(prediction))
    assert evaluate(source, output)["em"] == 1.0
    prediction.trajectory[-1]["status"] = "error"
    output.write_text(dump_line(prediction))
    assert evaluate(source, output)["em"] == 0.0


def test_pairing_usage_and_formal_gate(tmp_path):
    source = write_questions(tmp_path / "input.jsonl")
    prediction = make_prediction(read_questions(source)[0], Settings(mode="demo"))
    output = tmp_path / "pred.jsonl"
    output.write_text(dump_line(prediction))
    assert validate_predictions(source, output)["valid"]
    report = validate_predictions(source, output, formal=True)
    assert not report["valid"]
    assert any("exactly 100" in error for error in report["errors"])
    assert any("live HTTP" in error for error in report["errors"])
    broken = prediction.model_copy(deep=True)
    broken.trajectory[5]["tool_call_id"] = "other"
    assert any("orphan" in error for error in validate_record(broken))
    broken = prediction.model_copy(deep=True)
    broken.tool_calls = 0
    assert any("actual 1" in error for error in validate_record(broken))
    broken = prediction.model_copy(deep=True)
    broken.total_tokens = 9
    assert any("recorded usage" in error for error in validate_record(broken))
    broken = prediction.model_copy(deep=True)
    broken.trajectory[6]["messages"] = [broken.trajectory[1], broken.trajectory[5]]
    assert any("request" in error and "orphan" in error for error in validate_record(broken))


def test_coverage_types_and_usage_missing(tmp_path):
    source = write_questions(tmp_path / "input.jsonl")
    settings = Settings(mode="live", llm_base_url="https://example.invalid/v1", llm_model="synthetic-provider-model", model_verified=True, model_verification_note="Synthetic validator fixture, not a real model verification")
    prediction = make_prediction(read_questions(source)[0], settings, live=True)
    assert not validate_record(prediction, formal=True)
    prediction.trajectory[4]["usage"] = None
    prediction.total_tokens = 7
    assert any("reliable API usage" in error for error in validate_record(prediction, formal=True))
    output = tmp_path / "pred.jsonl"
    prediction.id = "unexpected"
    output.write_text(dump_line(prediction))
    report = validate_predictions(source, output)
    assert any("unexpected" in error for error in report["errors"])
    assert any("missing prediction" in error for error in report["errors"])
    raw = prediction.model_dump()
    raw["tool_calls"] = True
    output.write_text(dump_line(raw))
    assert not validate_predictions(source, output)["valid"]


def test_resume_and_failed_retry_are_durable_and_label_free(tmp_path):
    source = write_questions(tmp_path / "input.jsonl", [{"id": "001", "question": "first", "answer": "private reference"}, {"id": "002", "question": "second", "answer": "another private label"}])
    settings = Settings(mode="demo")
    called = []

    def runner(question, config):
        assert not hasattr(question, "answer")
        called.append(question.id)
        prediction = make_prediction(question, config, failed=question.id == "002")
        return RunResult(prediction=prediction, state=AgentState(question=question), mode=config.mode)

    output = tmp_path / "test_prediction.jsonl"
    first = batch_predict(source, output, settings, runner)
    assert first["records"] == 2 and first["completed"] == 1 and first["failed"] == 1
    assert called == ["001", "002"]
    called.clear()
    second = batch_predict(source, output, settings, runner)
    assert second["skipped"] == 2 and not called

    def recovery(question, config):
        called.append(question.id)
        return RunResult(prediction=make_prediction(question, config), state=AgentState(question=question), mode=config.mode)

    third = batch_predict(source, output, settings, recovery, rerun_failed=True)
    assert called == ["002"]
    assert third["completed"] == 2 and third["replaced_failed"] == 1
    assert len(output.read_text().splitlines()) == 2
    assert "superseded_failed_attempt" in Path(third["attempt_archive"]).read_text()
    with pytest.raises(ValueError, match="mismatch"):
        batch_predict(source, output, settings.model_copy(update={"top_k": 7}), recovery)
    source.write_text(source.read_text().replace('"first"', '"changed"'))
    with pytest.raises(ValueError, match="mismatch"):
        batch_predict(source, output, settings, recovery)


def test_uncaught_failure_is_recorded_and_never_formal(tmp_path):
    source = write_questions(tmp_path / "input.jsonl")
    output = tmp_path / "prediction.jsonl"

    def broken(question, settings):
        raise RuntimeError("secret-key-DO-NOT-LOG")

    report = batch_predict(source, output, Settings(mode="demo"), broken)
    assert report["valid"] and report["failed"] == 1
    assert "secret-key-DO-NOT-LOG" not in output.read_text()
    assert not validate_predictions(source, output, formal=True)["valid"]
    output.write_text(output.read_text()[:-5])
    with pytest.raises(ValueError, match="invalid JSON"):
        batch_predict(source, output, Settings(mode="demo"), broken)


def test_package_rejects_incomplete_and_ignores_secrets(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "package_course.py"
    spec = importlib.util.spec_from_file_location("package_course", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "source"
    (root / "src/rag_agent").mkdir(parents=True)
    (root / "skills/test-skill").mkdir(parents=True)
    for relative in ["README.md", "pyproject.toml", "requirements.txt", "src/rag_agent/__init__.py", "skills/test-skill/SKILL.md"]:
        (root / relative).write_text("synthetic fixture")
    (root / ".env").write_text("SECRET")
    (root / "data").mkdir()
    (root / "data/corpus.jsonl").write_text("private corpus")
    (root / "requirements-lock-py312-macos.txt").write_text("synthetic-package==1.0")
    (root / "unknown-private-notes.md").write_text("must not be packaged")
    (root / "docs").mkdir()
    private = tmp_path / "private.txt"
    private.write_text("private symlink target")
    (root / "LICENSE").symlink_to(private)
    (root / "docs/linked-notes.md").symlink_to(private)
    (root / "src/generated.egg-info").mkdir()
    (root / "src/generated.egg-info/SOURCES.txt").write_text("generated metadata must be rebuilt")
    output = tmp_path / "draft.zip"
    result = module.package(root, output, "Group-X", draft=True)
    assert result["draft"]
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "Group-X/DRAFT-NOT-FOR-SUBMISSION.txt" in names
        assert not any(".env" in name or "corpus" in name for name in names)
        assert "Group-X/code/requirements-lock-py312-macos.txt" in names
        assert not any("unknown-private" in name or "linked-notes" in name or name.endswith("/LICENSE") for name in names)
        assert not any(".egg-info" in name or ".dist-info" in name for name in names)
    with pytest.raises(ValueError, match="Formal package requires"):
        module.package(root, tmp_path / "formal.zip", "Group-X")


def test_formal_rejects_tampered_identity_and_unsupported_evidence():
    settings = Settings(mode="live", llm_base_url="https://example.invalid/v1", llm_model="synthetic-provider-model", model_verified=True, model_verification_note="Synthetic validator fixture, not a real model verification")
    question = Question(id="1", question="What is the fictional campus hall?")
    baseline = make_prediction(question, settings, live=True)
    assert not validate_record(baseline, formal=True)
    for model in ("gpt-4o", "deepseek-chat", "deepseek-v4.1"):
        changed = settings.model_copy(update={"llm_model": model})
        assert validate_record(make_prediction(question, changed, live=True), formal=True)
    changed = settings.model_copy(update={"llm_base_url": "https://api.deepseek.com"})
    assert validate_record(make_prediction(question, changed, live=True), formal=True)
    changed = settings.model_copy(update={"llm_base_url": "https://[invalid-host"})
    assert validate_record(make_prediction(question, changed, live=True), formal=True)
    broken = baseline.model_copy(deep=True)
    broken.trajectory[0]["model"] = "pretend-verified-model"
    assert any("contradicts" in error for error in validate_record(broken, formal=True))
    broken = baseline.model_copy(deep=True)
    broken.trajectory[5]["content"] = json.dumps({"ok": True, "data": {"results": []}})
    assert any("previously returned" in error for error in validate_record(broken, formal=True))
    broken = baseline.model_copy(deep=True)
    broken.answer = "A manually overwritten answer"
    assert any("differs from" in error for error in validate_record(broken, formal=True))
    broken = baseline.model_copy(deep=True)
    broken.trajectory = [event for event in broken.trajectory if event.get("event") != "api_attempt"]
    assert any("actual successful HTTP" in error for error in validate_record(broken, formal=True))
    broken = baseline.model_copy(deep=True)
    broken.trajectory[0]["injected_provider"] = True
    assert any("injected provider" in error for error in validate_record(broken, formal=True))


def test_retry_usage_is_counted_once():
    settings = Settings(mode="live", llm_base_url="https://example.invalid/v1", llm_model="synthetic-provider-model", model_verified=True, model_verification_note="Synthetic validator fixture, not a real model verification")
    prediction = make_prediction(Question(id="1", question="Synthetic?"), settings, live=True)
    prediction.trajectory.insert(3, {"event": "api_usage", "usage": {"total_tokens": 4}, "model": settings.llm_model, "http_status": 500})
    prediction.total_tokens += 4
    assert not validate_record(prediction, formal=True)
    prediction.total_tokens += 4
    assert any("recorded usage 16" in error for error in validate_record(prediction, formal=True))


def test_invalid_runner_trace_is_preserved_and_explicitly_retryable(tmp_path):
    source = write_questions(tmp_path / "input.jsonl")
    output = tmp_path / "predictions.jsonl"
    settings = Settings(mode="demo")

    def invalid(question, config):
        prediction = make_prediction(question, config)
        prediction.trajectory[5]["tool_call_id"] = "actual-invalid-provider-id"
        return RunResult(prediction=prediction, state=AgentState(question=question), mode=config.mode)

    summary = batch_predict(source, output, settings, invalid)
    assert not summary["valid"] and summary["failed"] == 1
    assert "actual-invalid-provider-id" in output.read_text()

    def repaired(question, config):
        return RunResult(prediction=make_prediction(question, config), state=AgentState(question=question), mode=config.mode)

    summary = batch_predict(source, output, settings, repaired, rerun_failed=True)
    assert summary["valid"] and summary["completed"] == 1
    assert "actual-invalid-provider-id" in Path(summary["attempt_archive"]).read_text()


@pytest.mark.parametrize("position,key,value", [
    (-1, "status", {}),
    (0, "config_id", {}),
    (4, "tool_calls", 3),
    (4, "role", []),
    (5, "tool_call_id", {}),
    (6, "messages", [{"role": "assistant", "tool_calls": [{"id": [], "function": {}}]}]),
])
def test_malformed_nested_json_returns_errors_not_tracebacks(tmp_path, position, key, value):
    source = write_questions(tmp_path / "input.jsonl")
    prediction = make_prediction(read_questions(source)[0], Settings(mode="demo"))
    prediction.trajectory[position][key] = value
    output = tmp_path / "prediction.jsonl"
    output.write_text(dump_line(prediction))
    for formal in (False, True):
        result = validate_predictions(source, output, formal=formal)
        assert result["valid"] is False
        assert result["errors"] and result["records"] == 1
        assert isinstance(result["completed"], int) and isinstance(result["failed"], int)
