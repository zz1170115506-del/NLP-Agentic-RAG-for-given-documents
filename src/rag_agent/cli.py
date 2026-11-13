"""All entry points share the same schemas and runtime as the web interface."""
import argparse
import json
import sys
from pathlib import Path

from rag_agent.config import Settings
from rag_agent.runtime import local_caches, make_runtime, run_question
from rag_agent.schemas import Question


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    p = argparse.ArgumentParser(description="COMP5423 fixed-corpus search agent")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ["check-config", "prepare", "index", "search", "ask", "predict", "validate", "evaluate", "tools"]:
        s = sub.add_parser(name)
        s.add_argument("--config", default="configs/default.yaml")
        if name == "check-config":
            s.add_argument("--live", action="store_true")
        elif name == "prepare":
            g = s.add_mutually_exclusive_group(required=True)
            g.add_argument("--source", help="Local JSONL containing docid/text/url")
            g.add_argument("--hf", action="store_true", help="Stream only Tevatron/browsecomp-plus-corpus")
            s.add_argument("--limit", type=int)
            s.add_argument("--revision", default="main")
        elif name == "index":
            s.add_argument("--methods", nargs="+", choices=["sparse", "encoder", "instruction"], default=["sparse", "encoder", "instruction"])
            s.add_argument("--max-new-shards", type=int, help="Checkpoint each dense route after this many NEW shards; incomplete indexes remain unsearchable")
        elif name == "search":
            s.add_argument("query")
            s.add_argument("--method", choices=["sparse", "encoder", "instruction", "hybrid"])
        elif name == "ask":
            s.add_argument("question")
            s.add_argument("--id", default="single")
            s.add_argument("--output")
        elif name == "predict":
            s.add_argument("--input", required=True)
            s.add_argument("--output", default="outputs/test_prediction.jsonl")
            s.add_argument("--rerun-failed", action="store_true")
            s.add_argument("--limit", type=int, help="Run at most this many pending questions; resume uses the full original input")
        elif name in ("validate", "evaluate"):
            s.add_argument("--input", required=True)
            s.add_argument("--predictions", required=True)
            if name == "validate":
                s.add_argument("--formal", action="store_true")
                s.add_argument("--strict-grounding", action="store_true", help="Also require exact inspected citations; separate from course record validity")
    args = p.parse_args(argv)
    try:
        local_caches()
        cfg = Settings.load(args.config)
        if args.command == "check-config":
            if args.live:
                if cfg.mode != "live":
                    raise ValueError("--live requires a live configuration; demo cannot verify an API setup")
                cfg.check_live()
            emit({"config_id": cfg.config_id, "settings": cfg.model_dump(), "live_checked": args.live})
        elif args.command == "prepare":
            from itertools import islice
            from rag_agent.data import DocumentStore, iter_jsonl, prepare_hf
            if args.limit is not None and args.limit < 1:
                raise ValueError("--limit must be positive")
            store = DocumentStore(cfg.store_path)
            if args.hf:
                result = prepare_hf(store, revision=args.revision, limit=args.limit, chunk_size=cfg.chunk_size,
                                    chunk_overlap=cfg.chunk_overlap,
                                    progress=lambda event: print(str(event), file=sys.stderr))
            else:
                documents = iter_jsonl(args.source)
                if args.limit:
                    documents = islice(documents, args.limit)
                result = store.import_documents(documents, chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap, source={"kind": "local", "path": str(Path(args.source).resolve())})
            emit(result)
        elif args.command == "index":
            from rag_agent.retrieval import build_indexes
            emit(build_indexes(cfg, args.methods, progress=lambda event: print(str(event), file=sys.stderr), max_new_shards=args.max_new_shards))
        elif args.command == "search":
            from rag_agent.retrieval import SearchService
            emit([x.model_dump() for x in SearchService(cfg).search(args.query, cfg.top_k, args.method or cfg.method)])
        elif args.command == "ask":
            store, search = make_runtime(cfg)
            result = run_question(Question(id=args.id, question=args.question), cfg, store=store, search=search)
            emit(result.model_dump())
            if args.output:
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(result.prediction.model_dump_json() + "\n", encoding="utf-8")
        elif args.command == "predict":
            from rag_agent.evaluation import batch_predict
            store, search = make_runtime(cfg)
            emit(batch_predict(args.input, args.output, cfg, lambda q, settings: run_question(q, settings, store=store, search=search), resume=True, rerun_failed=args.rerun_failed, max_questions=args.limit))
        elif args.command in ("validate", "evaluate"):
            from rag_agent.evaluation import evaluate, validate_predictions
            result = (validate_predictions(args.input, args.predictions, formal=args.formal, check_grounding=args.strict_grounding)
                      if args.command == "validate" else evaluate(args.input, args.predictions))
            emit(result)
            if args.command == "validate" and not result["valid"]:
                return 1
        elif args.command == "tools":
            if cfg.agent_engine == "agent12":
                from rag_agent.agent.agent12 import tool_schemas
                emit(tool_schemas(cfg.use_skills))
            else:
                from rag_agent.tools.registry import ToolRegistry
                emit(ToolRegistry.documentation())
        return 0
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
