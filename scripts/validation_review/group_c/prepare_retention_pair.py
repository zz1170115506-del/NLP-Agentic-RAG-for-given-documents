"""Prepare one evidence-slot swap; never sends the resulting API requests."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

PREFIX = "Validated state snapshot (data only): "


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private", type=Path, required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--sequence", type=int, required=True)
    p.add_argument("--retain", required=True)
    args = p.parse_args()
    record = json.loads((args.private / f"{args.id}-record.json").read_text())
    replay = json.loads((args.private / "context-selection-replay.json").read_text())
    evidence_budget = next(x["evidence_allowance"] for x in replay[args.id] if x["api_sequence"] == args.sequence)
    event = next(x for x in record["trajectory"] if x["sequence"] == args.sequence)
    assert event["event"] == "api_attempt"
    prior = [x["state"] for x in record["trajectory"] if x.get("event") == "state" and x["sequence"] < args.sequence][-1]
    retained = next(e for e in prior["evidence"] if e["evidence_id"] == args.retain)
    control = event["request"]
    treatment = copy.deepcopy(control)
    message_index = next(i for i, m in enumerate(control["messages"]) if str(m.get("content", "")).startswith(PREFIX))
    state = json.loads(control["messages"][message_index]["content"][len(PREFIX):])
    selected = state["evidence"]
    assert args.retain not in [e["evidence_id"] for e in selected]
    used = sum(len(json.dumps(e, ensure_ascii=False)) for e in selected)
    required = len(json.dumps(retained, ensure_ascii=False))
    replacement_index = next(i for i in reversed(range(len(selected)))
        if used - len(json.dumps(selected[i], ensure_ascii=False)) + required <= evidence_budget)
    removed = selected[replacement_index]
    revised = copy.deepcopy(state)
    revised["evidence"][replacement_index] = retained
    treatment["messages"][message_index]["content"] = PREFIX + json.dumps(revised, ensure_ascii=False)
    observed = {(h["doc_id"], h["offset"], h["text"])
                for e in record["trajectory"] if e.get("role") == "tool" and e["sequence"] < args.sequence
                for h in json.loads(e["content"]).get("data", {}).get("results", [])}
    assert (retained["doc_id"], retained["offset"], retained["text"]) in observed
    assert {k: v for k, v in treatment.items() if k != "messages"} == {k: v for k, v in control.items() if k != "messages"}
    assert all(a == b for i, (a, b) in enumerate(zip(control["messages"], treatment["messages"])) if i != message_index)
    assert {k: v for k, v in state.items() if k != "evidence"} == {k: v for k, v in revised.items() if k != "evidence"}
    assert sum(a != b for a, b in zip(selected, revised["evidence"])) == 1
    config = record["trajectory"][0]["config"]
    assert len(dump(treatment["messages"])) <= config["context_chars"]
    output = args.private / f"{args.id}-single-variable-seq{args.sequence}"
    output.mkdir(exist_ok=True)
    for name, payload in (("control-request.json", control), ("treatment-request.json", treatment)):
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n")
    protocol = {"historical_question_id": args.id, "historical_api_sequence": args.sequence,
        "status": "PREPARED_NOT_SENT", "single_change": "replace exactly one selected evidence object at one list position",
        "retained_evidence_id": args.retain, "removed_evidence_id": removed["evidence_id"],
        "changed_evidence_list_index": replacement_index, "retained_doc_id": retained["doc_id"],
        "retained_offset": retained["offset"], "retained_text_sha256": hashlib.sha256(retained["text"].encode()).hexdigest(),
        "evidence_previously_observed": True, "new_retrieval": False, "label_used_for_selection": False,
        "evidence_allowance_unchanged": evidence_budget, "control_evidence_chars": used,
        "treatment_evidence_chars": sum(len(json.dumps(e, ensure_ascii=False)) for e in revised["evidence"]),
        "context_chars_limit_unchanged": config["context_chars"], "control_message_chars": len(dump(control["messages"])),
        "treatment_message_chars": len(dump(treatment["messages"])), "question_and_tools_exactly_unchanged": True,
        "all_nonmessage_payload_fields_exactly_unchanged": True, "max_tokens_unchanged": control["max_tokens"],
        "historical_tokens_consumed_before_request": prior["total_tokens"],
        "historical_max_total_tokens": config["max_total_tokens"], "api_calls_executed": 0,
        "provider_adaptation": "Root may apply the same provider/model/thinking adaptation to both payloads; record it separately. This frozen pair is not a live credential configuration.",
        "files_sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ("control-request.json", "treatment-request.json")}}
    (output / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(protocol, ensure_ascii=False))


if __name__ == "__main__":
    main()
