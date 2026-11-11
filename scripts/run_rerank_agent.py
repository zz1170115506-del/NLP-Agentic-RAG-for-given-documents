"""Bounded live paired runs using the unchanged repository Agent.

Only unlabeled questions reach run_question. A durable budget ledger counts even
interrupted attempts; it must be shared by both experimental rounds.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from dotenv import load_dotenv

import rag_agent
from rag_agent.agent.loop import run_question
from rag_agent.config import Settings
from rag_agent.data import DocumentStore
from rag_agent.evaluation.batch import _exclusive_lock
from rag_agent.evaluation.io import file_sha256, read_questions
from rag_agent.retrieval import SearchService


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


class ObservedSearch(SearchService):
    def __init__(self, settings):
        super().__init__(settings)
        self.events = []

    def search(self, query, top_k=5, method="hybrid"):
        started = time.perf_counter()
        try:
            result = super().search(query, top_k, method)
        except Exception as error:
            self.events.append({"query": query, "top_k": top_k, "method": method,
                                "status": "error", "error_type": type(error).__name__,
                                "diagnostics": copy.deepcopy(self.last_diagnostics)})
            raise
        self.events.append({"query": query, "top_k": top_k, "method": method,
                            "status": "success", "seconds": time.perf_counter() - started,
                            "diagnostics": copy.deepcopy(self.last_diagnostics),
                            "results": [hit.model_dump() for hit in result]})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configs", nargs="+", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--env-file", default=".env.openrouter-smoke")
    parser.add_argument("--ledger", default="outputs/rerank-eval/api-budget.json")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10 or len(args.configs) < 2:
        parser.error("Use 1–10 questions and at least two paired configurations")
    load_dotenv(args.env_file, override=True)
    configs = [Settings.load(path) for path in args.configs]
    for config in configs:
        if config.mode != "live":
            raise ValueError("Live comparison rejects demo configurations")
        config.check_live()
    if len({c.config_id for c in configs}) != len(configs):
        raise ValueError("Paired configurations must be distinct")
    if len({Path(path).stem for path in args.configs}) != len(configs):
        raise ValueError("Configuration filenames must have distinct stems")
    # Model/index/Agent settings must match; only retrieval-ranking settings vary.
    ranking = {"candidate_depth", "rerank_enabled", "rerank_depth", "rerank_batch_size",
               "rerank_max_windows", "rerank_max_length", "rerank_on_error"}
    common = [{k: v for k, v in c.model_dump().items() if k not in ranking} for c in configs]
    if any(item != common[0] for item in common[1:]):
        raise ValueError("Paired configs differ outside retrieval ranking")
    questions = read_questions(args.questions)[:args.limit]
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    ledger_path = Path(args.ledger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    source_digest = hashlib.sha256()
    runtime_path = Path(rag_agent.__file__).resolve().parent
    for path in sorted(Path("src/rag_agent").rglob("*.py")):
        runtime_file = runtime_path / path.relative_to("src/rag_agent")
        if not runtime_file.exists() or runtime_file.read_bytes() != path.read_bytes():
            raise ValueError("Installed package differs from working source; reinstall or set PYTHONPATH=src")
        source_digest.update(str(path).encode())
        source_digest.update(path.read_bytes())
    source_digest.update(Path(__file__).read_bytes())
    metadata = {"git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "source_digest": source_digest.hexdigest(), "questions_sha256": file_sha256(args.questions),
                "question_ids": [q.id for q in questions], "configs": [c.model_dump() for c in configs],
                "config_ids": [c.config_id for c in configs], "platform": platform.platform(),
                "python": platform.python_version(), "runtime_path": str(runtime_path),
                "order": "alternate config order by question index"}
    with_store = DocumentStore(configs[0].store_path)
    metadata["corpus"] = with_store.metadata
    with_store.close()
    metadata["dense_manifest_sha256"] = {
        str(path): file_sha256(path) for path in sorted(Path(configs[0].index_dir).glob("*/manifest.json"))}
    manifest = out / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != metadata:
        raise ValueError("Existing live run metadata differs; choose another output directory")
    write_json(manifest, metadata)
    store = DocumentStore(configs[0].store_path)
    search = ObservedSearch(configs[0])
    rerankers = {}
    try:
        # Exclude first model/index loading from per-question wall times, without API use.
        start = time.perf_counter()
        for config in configs:
            search.settings = config
            search._reranker = None
            search.search(questions[0].question, config.top_k, config.method)
            rerankers[config.config_id] = search._reranker
        write_json(out / f"warmup-{time.time_ns()}.json", {"seconds": time.perf_counter() - start,
                                                        "searches": search.events})
        with _exclusive_lock(ledger_path.with_suffix(".lock")):
            ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"attempts": []}
            for index, question in enumerate(questions):
                order = list(range(len(configs)))
                if index % 2:
                    order.reverse()
                for group in order:
                    config = configs[group]
                    name = Path(args.configs[group]).stem
                    filename = hashlib.sha256(question.id.encode()).hexdigest()[:16] + ".json"
                    target = out / name / filename
                    if target.exists():
                        saved = json.loads(target.read_text())
                        if saved.get("id") != question.id or saved.get("config_id") != config.config_id:
                            raise ValueError("Existing result does not match its question/configuration")
                        continue
                    old = ledger["attempts"]
                    used_ids = {row["question_id"] for row in old}
                    if len(old) >= 20 or len(used_ids | {question.id}) > 10:
                        raise ValueError("Task API budget reached: maximum 20 attempts / 10 unique questions")
                    entry = {"question_id": question.id, "config_id": config.config_id,
                             "group": name, "output": str(target), "status": "started"}
                    old.append(entry)
                    write_json(ledger_path, ledger)  # reserve BEFORE any paid request
                    search.settings = config
                    # Keep embedding instances, reload only reranker when its config changes.
                    search._reranker = rerankers.get(config.config_id)
                    search.events = []
                    start = time.perf_counter()
                    try:
                        result = run_question(question, config, store=store, search=search)
                    except Exception as error:
                        entry.update(status="runner_error", error_type=type(error).__name__,
                                     usage_complete=False)
                        write_json(target, {"id": question.id, "group": name, "config_id": config.config_id,
                                            "status": "runner_error",
                                            "error_type": type(error).__name__, "searches": search.events})
                    else:
                        write_json(target, {"id": question.id, "group": name, "config_id": config.config_id,
                                            "seconds": time.perf_counter() - start,
                                            "result": result.model_dump(), "searches": search.events})
                        end = result.prediction.trajectory[-1]
                        entry.update(status=end.get("status"),
                                     total_tokens=result.prediction.total_tokens,
                                     tool_calls=result.prediction.tool_calls,
                                     usage_complete=end.get("usage_complete"))
                    rerankers[config.config_id] = search._reranker
                    write_json(ledger_path, ledger)
                    print(json.dumps({k: v for k, v in entry.items() if k != "output"}), flush=True)
    finally:
        search.close()
        store.close()
    # Never print environment values or provider payloads.
    assert os.getenv("LLM_API_KEY"), "Credential was not available to runtime"


if __name__ == "__main__":
    main()
