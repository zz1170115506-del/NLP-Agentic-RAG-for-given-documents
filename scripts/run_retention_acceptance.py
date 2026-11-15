"""Run every selected question from empty state with a locked baseline config.

Only question IDs/text and baseline metadata are read. This driver never reads
answer labels, old model answers, or diagnostic target coordinates. One question
is durably saved at a time; provider/identity failures stop subsequent calls.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.evaluation.io import read_predictions, read_questions, file_sha256
from rag_agent.evaluation.validate import validate_record
from rag_agent.identity import runtime_identity
from rag_agent.runtime import make_runtime, run_question


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--baseline-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(args.output.suffix + ".meta.json").exists():
        raise ValueError("Full acceptance requires a fresh output path")
    for name in list(os.environ):
        if name.startswith("LLM_"):
            os.environ.pop(name)
    cfg = Settings.load(args.config)
    cfg.check_live()
    if urlparse(cfg.llm_base_url).hostname != "dashscope.aliyuncs.com" or cfg.llm_model != "deepseek-v4-flash-0731":
        raise ValueError("This acceptance is pinned to the existing verified Beijing provider/model")
    questions = read_questions(args.questions)
    baseline = json.loads(args.baseline_metadata.read_text())
    current = runtime_identity(cfg)
    for field, value in [("config_id", cfg.config_id), ("source_sha256", file_sha256(args.questions)),
                         ("input_count", len(questions))]:
        if baseline[field] != value:
            raise ValueError("Acceptance differs from the baseline: " + field)
    for field in ["corpus", "indexes", "skills"]:
        if current[field] != baseline["runtime_identity"][field]:
            raise ValueError("Acceptance runtime differs outside the code change: " + field)
    store, search = make_runtime(cfg)
    try:
        for _ in questions:
            batch_predict(args.questions, args.output, cfg,
                          lambda q, settings: run_question(q, settings, store=store, search=search),
                          resume=True, max_questions=1)
            row = read_predictions(args.output)[-1]
            end = next(e for e in reversed(row.trajectory) if e.get("event") == "run_end")
            errors = validate_record(row, formal=True, check_grounding=True)
            print(json.dumps({"id": row.id, "status": end["status"], "has_answer": bool(row.answer),
                              "tool_calls": row.tool_calls, "reported_total_tokens": row.total_tokens,
                              "record_errors": errors}), flush=True)
            if errors:
                print(json.dumps({"stopped_before_next_question": True, "reason": "ineligible_record"}), flush=True)
                return 1
    finally:
        store.close()
        search.close()
    print(json.dumps({"all_questions_rerun_from_empty_state": len(questions), "config_id": cfg.config_id,
                      "runtime_code_sha256": current["code_sha256"], "reference_labels_read": False}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
