"""Exercise a real project search/follow-up against a disclosed synthetic fixture."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.evaluation.validate import validate_record
from rag_agent.retrieval import build_indexes
from rag_agent.runtime import make_runtime, run_question
from rag_agent.schemas import Question


def main():
    for name in list(os.environ):
        if name.startswith("LLM_"):
            os.environ.pop(name)
    cfg = Settings.load("configs/validation-review-bailian.yaml").model_copy(update={
        "store_path": "data/validation-review-probe.sqlite", "index_dir": "indexes/validation-review-probe"})
    store = DocumentStore(cfg.store_path)
    store.import_documents(iter_jsonl("tests/fixtures/corpus.jsonl"), chunk_size=cfg.chunk_size,
                           chunk_overlap=cfg.chunk_overlap, source={"kind": "synthetic_project_protocol_fixture"})
    store.close()
    build_indexes(cfg, ["sparse"])
    store, search = make_runtime(cfg)
    result = run_question(Question(id="synthetic-protocol", question="In what year did the Copper Museum open?"),
                          cfg, store=store, search=search)
    store.close()
    out = Path("outputs/validation-review")
    out.mkdir(parents=True, exist_ok=True)
    (out / "project-tool-probe.jsonl").write_text(result.prediction.model_dump_json() + "\n")
    attempts = [x for x in result.prediction.trajectory if x.get("event") == "api_attempt"]
    errors = validate_record(result.prediction, formal=True, check_grounding=True)
    tool_followups = sum(any(m.get("role") == "tool" for m in x["request"]["messages"]) for x in attempts)
    summary = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "kind": "synthetic_protocol_only",
               "formal_grounding_errors": errors, "api_requests": len(attempts),
               "http_statuses": [x.get("http_status") for x in attempts],
               "response_models": sorted({x.get("response", {}).get("model") for x in attempts}),
               "enable_thinking_values": [x["request"].get("enable_thinking") for x in attempts],
               "tool_result_followup_requests": tool_followups,
               "tool_calls": result.prediction.tool_calls, "total_tokens": result.prediction.total_tokens,
               "per_request_total_tokens": [x.get("response", {}).get("usage", {}).get("total_tokens") for x in attempts],
               "answer_matches_synthetic_fixture": result.prediction.answer == "1984"}
    (out / "project-tool-probe-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    assert not errors and tool_followups >= 1 and result.prediction.tool_calls >= 1
    assert all(x["request"].get("enable_thinking") is False for x in attempts)


if __name__ == "__main__":
    main()
