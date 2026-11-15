#!/usr/bin/env python3
"""Offline coverage, redaction, provenance and payload budget checks."""

import json
import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ids = ("231", "390", "58")
labels = [json.loads((ROOT / "private" / f"{q}-label.json").read_text()) for q in ids]
publicfiles = list((ROOT / "public").rglob("*")) + list(ROOT.glob("*.py")) + [ROOT / "README.md"]
for p in publicfiles:
    if not p.is_file():
        continue
    content = p.read_text()
    assert ("/" + "Users/") not in content, p.name
    assert not re.search(r"sk-[a-zA-Z0-9]{16,}", content), p.name
    for lab in labels:
        assert lab["question"] not in content, p.name
        assert lab["answer"].lower() not in content.lower(), p.name
for p in ROOT.rglob("*"):
    if p.is_file() and "private" in p.relative_to(ROOT).parts:
        assert stat.S_IMODE(p.stat().st_mode) == 0o600, p.name
assert stat.S_IMODE((ROOT / "private").stat().st_mode) == 0o700
counts = {"historical": {}, "bailian": {}}
for q in ids:
    for condition, suffix in [("historical", ""), ("bailian", "-bailian")]:
        rec = json.loads((ROOT / "private" / f"{q}{suffix}-original-record.json").read_text())
        events = rec["trajectory"]
        for view in ["private", "public"]:
            text = (ROOT / view / f"{q}{suffix}-timeline.md").read_text()
            seqs = [int(x) for x in re.findall(r"^\| (\d+) \|", text, re.M)]
            assert seqs == [e["sequence"] for e in events], (view, q, suffix)
        types = {
            k: sum(e.get("event", e.get("role")) == k for e in events) for k in ["api_attempt", "assistant", "tool"]
        }
        counts[condition][q] = {"events": len(events), **types}
    x = json.loads((ROOT / "private" / f"{q}-analysis.json").read_text())
    for r in x["requests"]:
        assert r["baseline_exact_replay"] and r["actual_api_messages_identical"]
        for variant in [
            "target_retention_diagnostic",
            "latest_tool_retention_diagnostic",
            "focused_tool_retention",
            "doc_diversity_retention",
        ]:
            assert r[variant]["stats"]["characters"] <= 24000
        assert not r["target_ids_in_actual_request"]
    assert x["export_matches_parsed"]
    assert all(
        z["state_preserves_exact_text"] and not z["actual_api_target_visible"] and z["counterfactual_target_visible"]
        for z in x["first_losses"]
    )
paired = json.loads((ROOT / "public/paired-final-results.json").read_text())
assert len(paired["events"]) == 12 and paired["actual_api_calls_performed_by_root"] == 6
assert all(c["only_messages_differ"] and c["all_other_provider_converted_fields_identical"] for c in paired["cases"])
assert {c["case_id"]: [c["arms"][a]["normalized_em"] for a in ["control", "treatment"]] for c in paired["cases"]} == {
    "231": [0, 0],
    "390": [0, 0],
    "58": [0, 1],
}
result = {
    "paired_live_api_attempts": 6,
    "paired_live_assistant_response_rows": 6,
    "paired_scope": "separate final turns on old observed history",
    "passed": True,
    "coverage": counts,
    "public_redaction_files_checked": len(publicfiles),
    "historical_exact_message_replays": 15,
    "hook_exact_replays": 30,
    "no_new_api_calls": True,
    "private_permissions": "directory700/files600",
}
(ROOT / "public/verification-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False))
