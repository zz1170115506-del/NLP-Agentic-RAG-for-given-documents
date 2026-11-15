"""Offline post-hoc diagnostic: pin one already-observed evidence item.

Reproduce the actual control payload with the frozen context function. Treatment
replaces exactly one selected observation with another previously observed item,
and verifies the unchanged frozen evidence allowance and total character budget.
This file never imports a provider, reads dotenv, or invokes an API.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

PREFIX = "Validated state snapshot (data only): "
FROZEN_CONTEXT_SHA = "049570c0ac9977b4f63421ef907bdefcc7690f6ed46fa869d1e8fca169129867"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def snapshot(messages):
    matches = [(i, json.loads(m["content"][len(PREFIX):])) for i, m in enumerate(messages)
               if isinstance(m.get("content"), str) and m["content"].startswith(PREFIX)]
    if len(matches) != 1:
        raise ValueError("Expected one validated state snapshot")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("work/deepseek-official-compat"))
    parser.add_argument("--record", type=Path,
                        default=Path("work/validation-review-drafts/group-a/64-bailian-original-private.json"))
    parser.add_argument("--output", type=Path, default=Path("work/validation-review-drafts/group-a/e4-counterfactual"))
    parser.add_argument("--api-sequence", type=int, default=51)
    parser.add_argument("--evidence-id", default="E4")
    parser.add_argument("--replace-evidence-id", default="E7")
    args = parser.parse_args()
    source_path = args.repo / "src/rag_agent/agent/context.py"
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != FROZEN_CONTEXT_SHA:
        raise ValueError("Context source differs from historical frozen implementation")
    sys.path[:0] = [str(args.repo / "src"), str(args.repo / "agent12")]
    from rag_agent.agent.context import build_context, message_size
    from rag_agent.schemas import AgentState
    from rag_agent.skills.runtime import SkillCatalog

    record = json.loads(args.record.read_text())
    events = record["trajectory"]
    target_event = next(e for e in events if e.get("event") == "api_attempt" and e["sequence"] == args.api_sequence)
    before = [e for e in events if e["sequence"] < args.api_sequence]
    state_event = [e for e in before if e.get("event") == "state"][-1]
    state = AgentState.model_validate(state_event["state"])
    config = copy.deepcopy(events[0]["config"])
    control = copy.deepcopy(target_event["request"])
    is_final = control.get("tool_choice") == "none"
    config["context_chars"] -= 400 if is_final else 0
    settings = SimpleNamespace(**config)
    catalog = SkillCatalog(str(args.repo / "skills"))
    for event in before:
        if event.get("event") == "skill_loaded":
            body = catalog.load(event["name"])
            if event.get("instructions") is not None and body != event["instructions"]:
                raise ValueError("Current skill body differs from captured instructions")
    # Match the production loop's atomic assistant+tool groups exactly.
    groups = []
    pending = None
    for event in before:
        if event.get("role") == "assistant" and event.get("tool_calls"):
            if pending:
                groups.append(pending)
            pending = [{k: copy.deepcopy(event[k]) for k in ("role", "content", "tool_calls")}]
        elif event.get("role") == "tool" and pending is not None:
            pending.append({k: copy.deepcopy(event[k]) for k in ("role", "tool_call_id", "name", "content")})
    if pending:
        groups.append(pending)
    final_message = None
    if is_final:
        final_message = copy.deepcopy(control["messages"][-1])
        if final_message.get("role") != "user" or not final_message.get("content", "").startswith("Finish now"):
            raise ValueError("Unexpected finalization message")
    reproduced, control_info = build_context(state, catalog, groups, settings)
    if final_message:
        reproduced.append(final_message)
    if reproduced != control["messages"]:
        raise ValueError("Frozen context replay did not exactly reproduce the actual control messages")
    chosen = next(e for e in state.evidence if e.evidence_id == args.evidence_id)
    observations = []
    for event in before:
        if event.get("role") == "tool":
            envelope = json.loads(event["content"])
            for rank, hit in enumerate(envelope.get("data", {}).get("results", []), 1):
                if hit.get("evidence_id") == args.evidence_id:
                    if (hit["doc_id"], hit["offset"], hit["text"]) != (chosen.doc_id, chosen.offset, chosen.text):
                        raise ValueError("Pinned evidence does not equal its real tool observation")
                    observations.append({"sequence": event["sequence"], "rank": rank,
                                         "call_id": event["tool_call_id"]})
    if not observations:
        raise ValueError("Pinned evidence has no real earlier tool observation")
    control_index, control_snapshot = snapshot(control["messages"])
    if any(e["evidence_id"] == args.evidence_id for e in control_snapshot["evidence"]):
        raise ValueError("Control already includes the pinned evidence")
    # Exactly one in-memory selected-evidence substitution. Other selected
    # items, including the artist birth evidence, remain byte-for-byte identical.
    treatment_snapshot = copy.deepcopy(control_snapshot)
    replacement_indices = [i for i, e in enumerate(treatment_snapshot["evidence"])
                           if e["evidence_id"] == args.replace_evidence_id]
    if len(replacement_indices) != 1:
        raise ValueError("Expected exactly one selected item to replace")
    replacement_index = replacement_indices[0]
    treatment_snapshot["evidence"][replacement_index] = chosen.model_dump()
    treatment_messages = copy.deepcopy(control["messages"])
    treatment_messages[control_index]["content"] = PREFIX + json.dumps(treatment_snapshot, ensure_ascii=False)
    # Recompute the frozen allocator's original evidence allowance, not a new
    # expanded allowance. build_context inserts its snapshot at index 1.
    empty_snapshot = copy.deepcopy(control_snapshot)
    empty_snapshot["evidence"] = []
    base_size = message_size([control["messages"][0], control["messages"][2]])
    allowance = max(0, (settings.context_chars - base_size) // 2 - len(json.dumps(empty_snapshot)) - 100)
    control_used = sum(len(json.dumps(e, ensure_ascii=False)) for e in control_snapshot["evidence"])
    treatment_used = sum(len(json.dumps(e, ensure_ascii=False)) for e in treatment_snapshot["evidence"])
    if max(control_used, treatment_used) > allowance:
        raise ValueError("Evidence substitution exceeds the unchanged frozen allowance")
    treatment_info = {**control_info, "characters": message_size(treatment_messages) -
                      (message_size(control["messages"]) - control_info["characters"])}
    treatment = copy.deepcopy(control)
    treatment["messages"] = treatment_messages
    treatment_index, treatment_snapshot = snapshot(treatment_messages)
    assert control_index == treatment_index
    assert {k:v for k,v in control_snapshot.items() if k != "evidence"} == {
        k:v for k,v in treatment_snapshot.items() if k != "evidence"}
    assert control["messages"][:control_index] + control["messages"][control_index + 1:] == (
        treatment_messages[:treatment_index] + treatment_messages[treatment_index + 1:])
    assert {k:v for k,v in control.items() if k != "messages"} == {k:v for k,v in treatment.items() if k != "messages"}
    assert any(e["evidence_id"] == args.evidence_id for e in treatment_snapshot["evidence"])
    observed = {(e.doc_id, e.offset, e.text) for e in state.evidence}
    assert all((e["doc_id"], e["offset"], e["text"]) in observed for e in treatment_snapshot["evidence"])
    assert message_size(treatment_messages) <= events[0]["config"]["context_chars"]
    args.output.mkdir(parents=True, exist_ok=True)
    for name, payload in (("control-request-private.json", control), ("treatment-request-private.json", treatment)):
        (args.output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (args.output / "context-replay-state-private.json").write_text(json.dumps({"state": state.model_dump(),
        "groups": groups, "loaded_skills": catalog.loaded, "context_config": config}, ensure_ascii=False, indent=2) + "\n")
    provenance = {"type": "post_hoc_reference_assisted_diagnostic_not_blind_or_online_agent_success",
        "api_calls_performed": 0, "question_id": record["id"], "control_api_sequence": args.api_sequence,
        "state_sequence": state_event["sequence"], "pinned_evidence_id": args.evidence_id,
        "replaced_evidence_id": args.replace_evidence_id,
        "pinned_span": {"doc_id": chosen.doc_id, "chunk_id": chosen.chunk_id, "offset": chosen.offset,
                        "end": chosen.offset + len(chosen.text), "text_sha256": hashlib.sha256(chosen.text.encode()).hexdigest()},
        "earlier_tool_observations": observations, "control_reproduces_actual_messages_exactly": True,
        "only_snapshot_evidence_changed": True, "all_treatment_spans_previously_observed": True,
        "no_reference_answer_or_evaluator_label_added_to_payload": True,
        "change": "Exactly one selected evidence substitution; unchanged order and seven other observations; frozen allocator allowance verified",
        "evidence_allowance_chars": allowance, "control_evidence_used_chars": control_used,
        "treatment_evidence_used_chars": treatment_used,
        "configured_context_chars": events[0]["config"]["context_chars"],
        "context_builder_budget_chars": settings.context_chars,
        "control_request_chars": message_size(control["messages"]),
        "treatment_request_chars": message_size(treatment_messages),
        "control_context_info": control_info, "treatment_context_info": treatment_info,
        "control_selected_ids": [e["evidence_id"] for e in control_snapshot["evidence"]],
        "treatment_selected_ids": [e["evidence_id"] for e in treatment_snapshot["evidence"]],
        "tool_choice": control.get("tool_choice"), "max_tokens": control.get("max_tokens"),
        "model": control.get("model"), "enable_thinking": control.get("enable_thinking"),
        "frozen_context_file_sha256": FROZEN_CONTEXT_SHA,
        "record_file_sha256": hashlib.sha256(args.record.read_bytes()).hexdigest(),
        "control_payload_sha256": digest(control), "treatment_payload_sha256": digest(treatment),
        "canonical_hash_note": "SHA256 of UTF-8 json.dumps ensure_ascii=False separators=(',', ':')",
        "preparation_status": "This offline script creates payloads only; it never sends API requests.",
        "actual_execution_result_file": "paired-results-public.json"}
    (args.output / "provenance-public.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(provenance, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
