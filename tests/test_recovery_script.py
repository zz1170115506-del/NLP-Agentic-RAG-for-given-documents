"""Synthetic recovery fixtures; no inference API is called by these tests."""
import hashlib
import importlib.util
import json
from pathlib import Path

from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.evaluation.io import read_predictions
from rag_agent.schemas import AgentState, RunResult
from test_evaluation import make_prediction


def fixture(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/recover_predictions.py"
    spec = importlib.util.spec_from_file_location("recovery_script", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    settings = Settings(store_path=str(tmp_path / "absent-store"), index_dir=str(tmp_path / "absent-index"),
                        llm_base_url="https://example.invalid/v1", llm_model="synthetic-provider-model",
                        model_verified=True, model_verification_note="Synthetic fixture; not a real API verification")
    source, output = tmp_path / "input.jsonl", tmp_path / "predictions.jsonl"
    source.write_text(''.join(json.dumps({"id": str(i), "question": "Synthetic campus hall?"}) + '\n'
                              for i in range(1, 5)))

    def initial(question, config):
        p = make_prediction(question, config, live=True, failed=question.id == "3")
        if question.id == "2":
            p.answer = ""
            p.trajectory[-2]["content"] = '{"answer":"","supporting_evidence":[]}'
            p.trajectory[-1].update(status="insufficient_evidence", eligible=False)
        return RunResult(prediction=p, state=AgentState(question=question), mode="live")

    batch_predict(source, output, settings, initial, max_questions=3)
    return module, settings, source, output


def test_recover_skips_valid_answers_and_valid_abstentions(tmp_path):
    module, settings, source, output = fixture(tmp_path)
    before = {p.id: p.model_dump() for p in read_predictions(output)}
    dry = module.recover(source, output, settings, dry_run=True)
    assert dry == {"valid_existing": 2, "pending": 2, "missing": 1, "ineligible": 1,
                   "dry_run": True, "new_api_calls": 0}
    called = []

    def runner(question, config):
        called.append(question.id)
        return RunResult(prediction=make_prediction(question, config, live=True),
                         state=AgentState(question=question), mode="live")

    result = module.recover(source, output, settings, runner=runner)
    assert called == ["3", "4"] and result["attempted_this_run"] == 2
    after = {p.id: p.model_dump() for p in read_predictions(output)}
    assert after["1"] == before["1"] and after["2"] == before["2"]
    archive = Path(str(output) + ".attempts.jsonl")
    rows = [json.loads(line) for line in archive.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["prediction"] == before["3"]
    assert module.recover(source, output, settings, dry_run=True)["pending"] == 0


def test_recovery_reuses_a_durable_returned_result_without_a_new_api_call(tmp_path):
    module, settings, source, output = fixture(tmp_path)
    from rag_agent.evaluation.io import read_questions
    question = read_questions(source)[2]
    actual_fixture_result = make_prediction(question, settings, live=True)
    journal = Path(str(output) + ".recovery-journal")
    journal.mkdir()
    identity = json.loads(Path(str(output) + ".meta.json").read_text())
    pending = journal / (hashlib.sha256(question.id.encode()).hexdigest() + ".json")
    pending.write_text(json.dumps({"identity": identity, "prediction": actual_fixture_result.model_dump()}))

    def must_not_run(question, config):
        raise AssertionError("A completed journal result must not issue a new request")

    result = module.recover(source, output, settings, runner=must_not_run, limit=1)
    assert result["attempted_this_run"] == 0 and result["journal_results_reused"] == 1
    assert not pending.exists()
    assert {p.id: p.model_dump() for p in read_predictions(output)}["3"] == actual_fixture_result.model_dump()
    assert module.recover(source, output, settings, dry_run=True)["pending"] == 1
