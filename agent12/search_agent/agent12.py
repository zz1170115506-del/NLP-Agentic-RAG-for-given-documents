"""Independent section 1.2 runner and teammate integration entry point.

python -m search_agent.agent12 --offline --scenario multi-hop
python -m search_agent.agent12 --fixture-backend --development-model
python -m search_agent.agent12 --backend teammate_module:create_backend --question "..."
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .agent import AgentConfig, SearchAgent
from .config import PROJECT_ROOT, load_config
from .fixtures_agent12 import FixtureBackend, QUESTION, ScenarioClient
from .ports import FunctionBackend


def create_agent(search_fn, *, config: AgentConfig | None = None,
                 open_document_fn=None, find_in_document_fn=None, client=None, on_event=None):
    """Public handoff API: inject functions; no index/model-weight dependency."""
    backend = FunctionBackend(search_fn, open_document_fn=open_document_fn,
                              find_in_document_fn=find_in_document_fn)
    config = config or load_config(enable_skills=False, require_evidence=True)
    return SearchAgent(backend, config, on_event=on_event, client=client)


def _backend(path):
    module_name, separator, factory_name = path.partition(":")
    if not separator or not module_name or not factory_name:
        raise ValueError("--backend must be module_name:factory_name")
    factory = getattr(importlib.import_module(module_name), factory_name)
    instance = factory()
    if isinstance(instance, FunctionBackend):
        return instance
    return FunctionBackend.from_backend(instance)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--offline", action="store_true", help="No API; explicit mock model and synthetic backend")
    source.add_argument("--fixture-backend", action="store_true", help="Real API + synthetic source documents; development only")
    source.add_argument("--backend", help="Teammate backend factory module:function")
    source.add_argument("--peer-project", type=Path, help="Section 1.1 project root containing src/rag_agent")
    parser.add_argument("--peer-config", type=Path, help="Peer YAML/JSON config; relative paths resolve against the peer project")
    parser.add_argument("--retrieval-method", choices=["sparse", "encoder", "instruction", "hybrid"])
    parser.add_argument("--find-max-matches", type=int, default=8)
    parser.add_argument("--scenario", choices=["multi-hop", "recovery", "context"], default="multi-hop")
    parser.add_argument("--development-model", action="store_true", help="Allow configured model for development, without claiming the coursework backbone")
    parser.add_argument("--question")
    parser.add_argument("--id", default="agent12-check")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--context-chars", type=int, default=12000)
    parser.add_argument("--max-tokens", type=int, default=24000)
    args = parser.parse_args(argv)
    backend = None
    try:
        if bool(args.peer_project) != bool(args.peer_config):
            raise ValueError("--peer-project and --peer-config must be supplied together")
        if args.retrieval_method and not args.peer_project:
            raise ValueError("--retrieval-method requires --peer-project")
        if (args.backend or args.peer_project) and not args.question:
            raise ValueError("A teammate backend requires --question")
        target = args.output or PROJECT_ROOT / "outputs" / "agent12" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        if target.exists():
            raise ValueError("Output already exists; select a new file to preserve the earlier run")
        config = load_config(enable_skills=False, require_evidence=True, max_steps=args.max_steps,
                             context_chars=args.context_chars, max_tokens=args.max_tokens,
                             max_output_tokens=1536, strict_model_identity=True)
        client = None
        if args.offline:
            config = replace(config, api_key="", demo=True, provider="demo", development_only=True)
            client = ScenarioClient(args.scenario)
        elif args.development_model:
            # Explicit opt-in never changes the default course-model requirement.
            config = replace(config, expected_model_family=config.model, development_only=True)
        if not args.offline and not config.api_key:
            raise ValueError("Configure LLM_API_KEY locally before real API execution")
        if args.peer_project:
            from .peer import load_peer_backend
            backend = FunctionBackend.from_backend(load_peer_backend(
                args.peer_project, args.peer_config, method=args.retrieval_method,
                max_matches=args.find_max_matches))
        else:
            backend = _backend(args.backend) if args.backend else FunctionBackend.from_backend(FixtureBackend())
        fixture = not bool(args.backend or args.peer_project) or backend.is_fixture
        if fixture:
            config = replace(config, development_only=True)
        question = args.question or ("Who founded Cedarwatch Observatory?" if args.scenario == "context" else QUESTION)
        def event(event):
            if event["type"] == "tool_call":
                print(f"  {event['name']}: {json.dumps(event.get('arguments'), ensure_ascii=False)}", file=sys.stderr)
        result = SearchAgent(backend, config, on_event=event, client=client).run(question, args.id)
        result["backend_fixture"] = fixture
        result["backend"] = backend.describe()
        result["test_description"] = ("Offline mock model; no API or accuracy claim" if args.offline else
                                      "Real model API with synthetic source documents; integration test only" if fixture else
                                      "Teammate retrieval integration")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": result["status"], "answer": result["answer"], "tool_calls": result["tool_calls"],
                          "api_tokens": result["total_tokens"], "observed_models": result["observed_models"],
                          "development_only": result["development_only"], "test_description": result["test_description"],
                          "context_stats": result["context_stats"], "output": str(target.resolve())}, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 1
    except (ValueError, OSError, RuntimeError, ImportError, AttributeError) as exc:
        message = str(exc)
        secret = locals().get("config")
        if secret and secret.api_key:
            message = message.replace(secret.api_key, "[REDACTED]")
        print("Error: " + message, file=sys.stderr)
        return 2
    finally:
        if backend is not None:
            backend.close()


if __name__ == "__main__":
    raise SystemExit(main())
