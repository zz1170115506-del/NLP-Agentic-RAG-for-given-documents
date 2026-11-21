"""Changed procedural prompts must not silently mix into a resumed batch."""
import json

import pytest

from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.schemas import AgentState, RunResult
from test_evaluation import make_prediction


def test_resume_rejects_skill_body_change_before_any_new_run(tmp_path):
    skill = tmp_path / "skills" / "recovery" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: recovery\ndescription: Synthetic fixture\n---\nFirst procedure.\n")
    source, output = tmp_path / "questions.jsonl", tmp_path / "predictions.jsonl"
    source.write_text("".join(json.dumps({"id": str(i), "question": "Synthetic campus?"}) + "\n" for i in range(2)))
    cfg = Settings(mode="demo", skills_dir=str(skill.parent.parent),
                   store_path=str(tmp_path / "missing.sqlite"), index_dir=str(tmp_path / "missing-index"))
    called = []

    def runner(question, settings):
        called.append(question.id)
        return RunResult(prediction=make_prediction(question, settings),
                         state=AgentState(question=question), mode="demo")

    batch_predict(source, output, cfg, runner, max_questions=1)
    skill.write_text(skill.read_text().replace("First procedure", "Different procedure"))
    with pytest.raises(ValueError, match="Resume source/configuration mismatch"):
        batch_predict(source, output, cfg, runner)
    assert called == ["0"]
