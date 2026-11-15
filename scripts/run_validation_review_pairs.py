"""Run bounded, frozen-request diagnostic pairs without loading answer labels.

The JSON plan lists case_id, scope, control and treatment request paths. Paths
are relative to the plan. Raw requests/responses are private evidence. A pair
may change only the snapshot evidence list; both arms use the same provider.
These are conditional next-turn experiments, not full Agent evaluations.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from rag_agent.config import Settings
from rag_agent.llm.provider import HTTPProvider


PREFIX = "Validated state snapshot (data only): "


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def without_evidence(request):
    masked = copy.deepcopy(request)
    found = []
    for i, message in enumerate(masked["messages"]):
        content = message.get("content")
        if isinstance(content, str) and content.startswith(PREFIX):
            snapshot = json.loads(content[len(PREFIX):])
            evidence = snapshot.pop("evidence")
            message["content"] = PREFIX + json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
            found.append((i, evidence))
    if len(found) != 1:
        raise ValueError("Expected one validated-state snapshot")
    return masked, found[0]


def translate(request, model):
    value = copy.deepcopy(request)
    value["model"] = model
    value.pop("thinking", None)
    value.pop("reasoning", None)
    value["enable_thinking"] = False
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    for name in list(os.environ):
        if name.startswith("LLM_"):
            os.environ.pop(name)
    cfg = Settings.load(args.config)
    source_config_id = cfg.config_id
    # One request per arm: no retry can silently change the declared call count.
    cfg = cfg.model_copy(update={"max_retries": 0})
    plan = json.loads(args.plan.read_text())
    prepared = []
    for case in plan["cases"]:
        arms = {arm: json.loads((args.plan.parent / case[arm]).read_text())
                for arm in ("control", "treatment")}
        masked = {arm: without_evidence(request) for arm, request in arms.items()}
        if masked["control"][0] != masked["treatment"][0]:
            raise ValueError("A pair changed a field other than snapshot.evidence")
        if masked["control"][1][1] == masked["treatment"][1][1]:
            raise ValueError("A pair did not change snapshot.evidence")
        if any(sum(len(str(m.get("content") or "")) for m in r["messages"]) > cfg.context_chars
               for r in arms.values()):
            raise ValueError("Request exceeds the unchanged context budget")
        prepared.append((case, arms, masked))
    summary = {"kind": "retrospective_conditional_next_turn_pairs",
               "label_input": False, "fresh_full_agent_evaluation": False,
               "provider_model": cfg.llm_model, "enable_thinking": False,
               "source_config_id": source_config_id, "pair_transport_config_id": cfg.config_id,
               "max_retries_override": 0,
               "cases_preflight_passed": len(prepared), "arms": []}
    if args.check_only:
        print(json.dumps(summary))
        return
    if args.output.exists():
        raise ValueError("Output already exists; preserve prior attempts and choose a new directory")
    args.output.mkdir(parents=True)
    try:
        for case, arms, masked in prepared:
            for arm in ("control", "treatment"):
                target = args.output / str(case["case_id"]) / (arm + ".api-attempt.json")
                expected = translate(arms[arm], cfg.llm_model)
                events = []

                def emit(event):
                    events.append(event)
                    if event.get("event") == "api_attempt":
                        save(target, event)

                provider = HTTPProvider(cfg, emit=emit)
                try:
                    actual = provider.build_payload(expected["messages"], expected["tools"],
                                                    expected["max_tokens"],
                                                    allow_tools=expected["tool_choice"] == "auto")
                    if actual != expected:
                        raise ValueError("Provider payload differs from the declared identical translation")
                    started = datetime.now(timezone.utc).isoformat()
                    clock_start = time.monotonic()
                    result = provider.complete(expected["messages"], expected["tools"],
                                               expected["max_tokens"],
                                               allow_tools=expected["tool_choice"] == "auto")
                finally:
                    provider.close()
                if not cfg.accepts_response_model(result.get("model")):
                    raise ValueError("Unexpected response model; stopped before the next call")
                event = next(e for e in events if e.get("event") == "api_attempt")
                entry = {"case_id": str(case["case_id"]), "arm": arm, "scope": case["scope"],
                         "started_at_utc": started, "elapsed_seconds": time.monotonic() - clock_start,
                         "source_request_sha256": digest(arms[arm]),
                         "actual_request_sha256": digest(expected), "response_sha256": digest(result),
                         "http_status": event["http_status"], "response_model": result.get("model"),
                         "usage": result.get("usage"), "tool_choice": expected["tool_choice"],
                         "returned_tool_calls": len(result["choices"][0]["message"].get("tool_calls") or []),
                         "finish_reason": result["choices"][0].get("finish_reason"),
                         "changed_snapshot_message_index": masked[arm][1][0]}
                summary["arms"].append(entry)
                save(args.output / "summary.json", summary)
                print(json.dumps(entry), flush=True)
    finally:
        save(args.output / "summary.json", summary)


if __name__ == "__main__":
    main()
