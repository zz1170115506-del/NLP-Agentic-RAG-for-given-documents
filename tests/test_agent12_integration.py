"""Exercise the integrated agent through batch prediction and the shared HTTP boundary."""
import json
from pathlib import Path

import httpx
import yaml

from rag_agent.cli import main
from rag_agent.config import Settings
from rag_agent.evaluation.io import read_predictions
from rag_agent.evaluation.validate import validate_record


def test_agent12_cli_batch_preserves_events_and_grounded_evidence(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    config = Settings(mode="demo", agent_engine="agent12", method="sparse",
                      store_path="corpus.sqlite", index_dir="indexes", use_skills=False)
    path = tmp_path / "agent12.yaml"
    path.write_text(yaml.safe_dump(config.model_dump()))
    options = ["--config", str(path)]
    questions = str(root / "tests/fixtures/questions.jsonl")
    assert main(["prepare", *options, "--source", str(root / "tests/fixtures/corpus.jsonl")]) == 0
    assert main(["index", *options, "--methods", "sparse"]) == 0
    assert main(["predict", *options, "--input", questions, "--output", "predictions.jsonl"]) == 0
    assert main(["validate", *options, "--input", questions, "--predictions", "predictions.jsonl"]) == 0
    rows = read_predictions("predictions.jsonl")
    assert len(rows) == 3
    assert rows[0].answer.startswith("[DEMO: retrieved passage]")
    end = rows[0].trajectory[-1]
    assert end["state"]["selected_evidence_ids"] == ["E1"]
    assert end["state"]["evidence"][0]["chunk_id"]
    assert rows[0].trajectory[0]["engine"] == "agent12"
    assert any(row.get("source_event", {}).get("type") == "tool_result" for row in rows[0].trajectory)
    assert not end["eligible"]
    assert main(["predict", *options, "--input", questions, "--output", "predictions.jsonl"]) == 0


def test_agent12_live_boundary_records_model_calls_and_usage(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_MODEL_VERIFIED", "LLM_MODEL_VERIFICATION_NOTE"):
        monkeypatch.delenv(name, raising=False)
    config = Settings(
        agent_engine="agent12", method="sparse", store_path="corpus.sqlite", index_dir="indexes",
        use_skills=False, llm_base_url="https://provider.example/v1", llm_model="verified-flash-deployment",
        model_verified=True, model_verification_note="Synthetic endpoint fixture", max_retries=0,
    )
    path = tmp_path / "live.yaml"
    path.write_text(yaml.safe_dump(config.model_dump()))
    options = ["--config", str(path)]
    assert main(["prepare", *options, "--source", str(root / "tests/fixtures/corpus.jsonl")]) == 0
    assert main(["index", *options, "--methods", "sparse"]) == 0
    requests = []

    def post(self, url, *, json: dict, **kwargs):
        assert url == "https://provider.example/v1/chat/completions"
        requests.append(json)
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "search-1", "type": "function", "function": {
                    "name": "search", "arguments": '{"query":"Copper Museum","top_k":1}',
                },
            }]}
        else:
            message = {"role": "assistant", "content": '{"answer":"1984","supporting_evidence":["E1"]}'}
        return httpx.Response(200, json={"model": config.llm_model, "usage": {"total_tokens": 7},
                                         "choices": [{"message": message}]})

    monkeypatch.setattr(httpx.Client, "post", post)
    assert main(["ask", *options, "When did the Copper Museum open?", "--output", "single.jsonl"]) == 0
    prediction, = read_predictions("single.jsonl")
    assert prediction.answer == "1984"
    assert (prediction.tool_calls, prediction.total_tokens) == (1, 14)
    tool = next(row for row in requests[1]["messages"] if row["role"] == "tool")
    assert "1984" in json.loads(tool["content"])["results"][0]["text"]
    assert validate_record(prediction) == []
    assert prediction.trajectory[-1]["eligible"]
    # Synthetic HTTP response fixture verifies the protocol, not a real API run.
    assert validate_record(prediction, formal=True, check_grounding=True) == []
    assert "synthetic-test-key" not in Path("single.jsonl").read_text()
