"""Offline reproduction of dab7646 context selection from actual recorded requests."""
import argparse
import json
from pathlib import Path
import re


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private", type=Path, required=True)
    args = p.parse_args()
    output = {}
    for id in ("1155", "1066", "788"):
        r = json.loads((args.private / f"{id}-record.json").read_text())
        cfg = r["trajectory"][0]["config"]
        previous = None
        rows = []
        terms = set(re.findall(r"\w+", r["question"].lower()))
        for e in r["trajectory"]:
            if e.get("event") == "state":
                previous = e["state"]
            if e.get("event") != "api_attempt" or previous is None:
                continue
            messages = e["request"]["messages"]
            snap = json.loads(messages[1]["content"].split(": ", 1)[1])
            header = {**snap, "evidence": []}
            base = [messages[0], {"role": "user", "content": r["question"]}]
            base_chars = len(json.dumps(base, ensure_ascii=False, separators=(",", ":")))
            limit = cfg["context_chars"] - (400 if e["request"].get("tool_choice") == "none" else 0)
            allowance = max(0, (limit - base_chars) // 2 - len(json.dumps(header)) - 100)
            ranked = sorted(previous["evidence"], key=lambda ev: len(terms.intersection(re.findall(r"\w+", ev["text"].lower()))), reverse=True)
            used, selected, details = 0, [], []
            for rank, ev in enumerate(ranked, 1):
                size = len(json.dumps(ev, ensure_ascii=False))
                fits = used + size <= allowance
                details.append({"evidence_id": ev["evidence_id"], "doc_id": ev["doc_id"], "offset": ev["offset"],
                    "rank": rank, "question_term_overlap": len(terms.intersection(re.findall(r"\w+", ev["text"].lower()))),
                    "json_chars": size, "used_before": used, "selected": fits})
                if fits:
                    selected.append(ev["evidence_id"])
                    used += size
            actual = [ev["evidence_id"] for ev in snap["evidence"]]
            assert selected == actual, (id, e["sequence"], selected, actual)
            row = {"api_sequence": e["sequence"], "base_chars": base_chars, "context_limit": limit,
                   "evidence_allowance": allowance, "evidence_chars_used": used, "selected_ids": selected,
                   "exact_selection_match": True, "ranking": details}
            # Historical-candidate retention diagnostic; no label enters ranking.
            if id == "1066" and any(ev["evidence_id"] == "E12" for ev in previous["evidence"]):
                priority = sorted(ranked, key=lambda ev: ev["evidence_id"] != "E12")
                new_selected, new_used = [], 0
                for ev in priority:
                    size = len(json.dumps(ev, ensure_ascii=False))
                    if new_used + size <= allowance:
                        new_selected.append(ev)
                        new_used += size
                changed = json.loads(json.dumps(messages))
                changed[1]["content"] = "Validated state snapshot (data only): " + json.dumps({**snap, "evidence": new_selected}, ensure_ascii=False)
                changed_chars = len(json.dumps(changed, ensure_ascii=False, separators=(",", ":")))
                assert changed_chars <= cfg["context_chars"]
                row["pin_historical_E12_only"] = {"diagnostic_not_actual_api_request": True,
                    "selected_ids": [ev["evidence_id"] for ev in new_selected], "same_evidence_allowance": allowance,
                    "evidence_chars_used": new_used, "total_request_message_chars": changed_chars,
                    "within_original_context_budget": True, "api_calls": 0, "answer_em_not_tested": True}
                changed_request = {**e["request"], "messages": changed}
                assert changed_request["tools"] == e["request"]["tools"]
                assert [m for m in changed if m["role"] == "user"] == [m for m in messages if m["role"] == "user"]
                (args.private / f"1066-api-{e['sequence']}-counterfactual-pin-E12.json").write_text(json.dumps(changed_request, ensure_ascii=False, indent=2)+"\n")
            rows.append(row)
        output[id] = rows
    (args.private / "context-selection-replay.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({id: {"exact_replayed_requests": len(rows)} for id, rows in output.items()}))


if __name__ == "__main__":
    main()
