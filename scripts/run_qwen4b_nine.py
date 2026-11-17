"""Run the fixed nine questions with the production Qwen candidate search and Beijing API."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from urllib.parse import urlparse

from rag_agent.config import Settings
from rag_agent.evaluation.batch import batch_predict
from rag_agent.evaluation.io import file_sha256, read_predictions, read_questions
from rag_agent.evaluation.validate import validate_record
from rag_agent.identity import runtime_identity
from rag_agent.runtime import make_runtime, run_question
from recover_predictions import recover


IDS = ["960", "1035", "64", "231", "390", "58", "1155", "1066", "788"]
INPUT_SHA = "dd829d11a47ce9c4d7c150c0e75fbdbcf57341b5197f3221c162dfe00fb60ce9"


def append(path, row):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class LoggedSearch:
    """Capture the real search engine's diagnostics outside the LLM context."""

    def __init__(self, service, path, qid, attempt_id):
        self.service = service
        self.path = path
        self.qid = qid
        self.attempt_id = attempt_id
        self.calls = 0
        self.failures = 0

    def search(self, query, top_k, method):
        self.calls += 1
        record = {"id": self.qid, "attempt_id": self.attempt_id, "search_index": self.calls,
                  "method": method, "top_k": top_k,
                  "query_sha256": hashlib.sha256(query.encode()).hexdigest()}
        try:
            hits = self.service.search(query, top_k, method)
        except Exception as exc:
            self.failures += 1
            record["error_type"] = type(exc).__name__
            raise
        else:
            record["returned_chunk_ids"] = [h.chunk_id for h in hits]
            return hits
        finally:
            record["diagnostics"] = self.service.last_diagnostics
            append(self.path, record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/qwen4b-compressed-nine.yaml")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--baseline-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Keep successful prior attempts; only retry invalid records.")
    args = parser.parse_args()
    os.umask(0o077)
    for key in list(os.environ):
        if key.startswith("LLM_"):
            os.environ.pop(key)
    settings = Settings.load(args.config)
    settings.check_live()
    if (urlparse(settings.llm_base_url).hostname != "dashscope.aliyuncs.com"
            or settings.llm_model != "deepseek-v4-flash-0731"
            or settings.method != "qwen4b_candidates" or settings.agent_engine != "baseline"):
        raise ValueError("Expected the fixed Beijing QA model and production Qwen candidate route")
    if [q.id for q in read_questions(args.questions)] != IDS or file_sha256(args.questions) != INPUT_SHA:
        raise ValueError("Questions differ from the original ordered benchmark")
    base = json.loads(args.baseline_metadata.read_text())
    identity = runtime_identity(settings)
    if any(identity[key] != base["runtime_identity"][key] for key in ("corpus", "indexes", "skills")):
        raise ValueError("Corpus, index, or skills differ from the verified baseline")
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    predictions = args.output_dir / "prediction.jsonl"
    store, service = make_runtime(settings)
    try:
        started = time.monotonic()
        service.warm_qwen4b()
        print(json.dumps({"model_warmed_seconds": round(time.monotonic() - started, 3),
                          "config_id": settings.config_id, "runtime_hash": identity["code_sha256"]}), flush=True)
        any_run = False
        def run_one(question, cfg):
            nonlocal any_run
            any_run = True
            attempt = uuid.uuid4().hex
            search = LoggedSearch(service, args.output_dir / "retrieval.jsonl", question.id, attempt)
            def capture(event):
                append(args.output_dir / "events.jsonl", {"id": question.id, "attempt_id": attempt, "record": event})
            result = run_question(question, cfg, store=store, search=search, on_event=capture)
            append(args.output_dir / "question-executions.jsonl",
                   {"id": question.id, "attempt_id": attempt, "searches": search.calls,
                    "search_errors": search.failures, "elapsed": result.prediction.trajectory[-1]["elapsed_seconds"]})
            return result
        for _ in IDS:
            if args.resume and predictions.is_file():
                completed = recover(args.questions, predictions, settings, runner=run_one, limit=1)
            else:
                completed = batch_predict(args.questions, predictions, settings, run_one, resume=True, max_questions=1)
            if not completed["attempted_this_run"] and not completed.get("journal_results_reused"):
                break
            execution = json.loads((args.output_dir / "question-executions.jsonl").read_text().splitlines()[-1])
            row = next(p for p in read_predictions(predictions) if p.id == execution["id"])
            errors = validate_record(row, formal=True, check_grounding=True)
            print(json.dumps({**execution, "status": row.trajectory[-1]["status"], "answered": bool(row.answer),
                              "tokens": row.total_tokens, "tools": row.tool_calls, "errors": errors}), flush=True)
            if errors or execution["search_errors"] or not execution["searches"]:
                raise RuntimeError("Review the recorded failed attempt before continuing the benchmark")
        rows = read_predictions(predictions)
        if [p.id for p in rows] != IDS or any(validate_record(p, formal=True, check_grounding=True) for p in rows):
            raise RuntimeError("Nine valid predictions are required before scoring")
        if any_run:
            # On recovery the process only holds vectors accessed in that process.
            target = args.output_dir / ("vectors-" + uuid.uuid4().hex + ".npz" if args.resume else "vectors.npz")
            print(json.dumps({"compact_cache_written": target.name, "rows": service.save_qwen4b_vectors(target)}), flush=True)
    finally:
        store.close()
        service.close()


if __name__ == "__main__":
    main()
