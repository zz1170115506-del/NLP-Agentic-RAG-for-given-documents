#!/usr/bin/env python3
"""Package already-verified final requests; no context replay, network, or new evidence."""

import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

COMMIT = "dab7646158fef729c3bf3e0f37b7f302727fc568"
CASES = {
    "231": (22, 23, "target-retention-diagnostic", "observed-span-diagnostic", True),
    "390": (43, 44, "target-retention-diagnostic", "observed-span-diagnostic", True),
    "58": (43, 44, "focused-tool-retention-diagnostic", "focused-tool-first", False),
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def save(p, v, private=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
    if private:
        p.chmod(0o600)


def load_module(p):
    s = importlib.util.spec_from_file_location("group_b_replay", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--group-root", type=Path, default=Path("work/validation-review-drafts/group-b"))
    p.add_argument("--repo", type=Path, default=Path("work/deepseek-official-compat"))
    a = p.parse_args()
    root = a.group_root
    dest = root / "paired-final-diagnostics"
    private = dest / "private"
    private.mkdir(parents=True, exist_ok=True)
    private.chmod(0o700)
    m = load_module(root / "replay_group_b.py")
    helper_paths = [
        "src/rag_agent/agent/loop.py",
        "src/rag_agent/evidence.py",
        "src/rag_agent/schemas.py",
        "agent12/search_agent/final_output.py",
    ]
    provenance = {
        f: sha(subprocess.check_output(["git", "-C", str(a.repo), "show", COMMIT + ":" + f])) for f in helper_paths
    }
    hooksha = sha((root / "context_retention_hook.py").read_bytes())
    frozen = json.loads((root / "public/group-b-replay-summary.json").read_text())
    cases = []
    for qid, (reqseq, apiseq, filename, condition, assisted) in CASES.items():
        recordpath = root / "private" / f"{qid}-original-record.json"
        record = json.loads(recordpath.read_text())
        hist = record["trajectory"]
        old = hist[apiseq]["request"]
        analysis = {"source_row": next(v for v in frozen["summary"] if v["id"] == qid)["original_record"]}
        prestate = next(e for e in reversed(hist[:reqseq]) if e.get("event") == "state")
        control = json.loads((root / "private" / f"{qid}-request-{reqseq}-baseline.json").read_text())
        treatment = json.loads((root / "private" / f"{qid}-request-{reqseq}-{filename}.json").read_text())
        assert control == old
        assert {k: v for k, v in control.items() if k != "messages"} == {
            k: v for k, v in treatment.items() if k != "messages"
        }
        assert control["tool_choice"] == "none" and control["max_tokens"] == 1024
        changed = [i for i, (c, t) in enumerate(zip(control["messages"], treatment["messages"])) if c != t]
        assert len(control["messages"]) == len(treatment["messages"]) and changed == [1]
        cs = json.loads(control["messages"][1]["content"][len(m.PREFIX) :])
        ts = json.loads(treatment["messages"][1]["content"][len(m.PREFIX) :])
        assert {k: v for k, v in cs.items() if k != "evidence"} == {k: v for k, v in ts.items() if k != "evidence"}
        source_by_id = {e["evidence_id"]: e for e in prestate["state"]["evidence"]}
        entries = {}
        allids = {}
        for arm, payload in [("control", control), ("treatment", treatment)]:
            observed = m.visible(payload["messages"])
            ids = [e["evidence_id"] for e in observed]
            allids[arm] = ids
            for e in observed:
                src = source_by_id[e["evidence_id"]]
                assert all(e.get(k) == src.get(k) for k in ["doc_id", "offset", "text", "url", "chunk_id"])
            chars = len(json.dumps(payload["messages"], ensure_ascii=False, separators=(",", ":")))
            assert chars <= 24000
            f = private / f"{qid}-{arm}.request.json"
            save(f, payload, True)
            # Preserve exact original observations and earlier request views. Replace only
            # this final request; no original final response/answer/end event is retained.
            audit = copy.deepcopy(hist[: reqseq + 1])
            audit[-1]["messages"] = copy.deepcopy(payload["messages"])
            audit[-1]["tools"] = copy.deepcopy(payload["tools"])
            audit[-1]["max_tokens"] = payload["max_tokens"]
            af = private / f"{qid}-{arm}.validation-prefix.json"
            save(af, audit, True)
            entries[arm] = {
                "request_file": str(f.relative_to(dest)),
                "file_sha256": sha(f.read_bytes()),
                "canonical_request_sha256": sha(canonical(payload)),
                "messages_sha256": sha(canonical(payload["messages"])),
                "messages_characters": chars,
                "selected_evidence_ids": ids,
                "validation_prefix_file": str(af.relative_to(dest)),
                "validation_prefix_sha256": sha(af.read_bytes()),
            }
        sf = private / f"{qid}-pre-final-state.json"
        save(sf, prestate["state"], True)
        cases.append(
            {
                "case_id": qid,
                "historical_request_sequence": reqseq,
                "historical_api_sequence": apiseq,
                "historical_pre_final_state_sequence": prestate["sequence"],
                "condition": condition,
                "reference_assisted": assisted,
                "reference_assistance_scope": "retrospective choice of already-observed source coordinates; no answer string in hook or added message"
                if assisted
                else "no labels or preselected case IDs/target coordinates used; prioritize successful focused-tool spans lacking search chunk_id",
                "source_original_record_file": "../private/" + recordpath.name,
                "source_original_record_sha256": sha(recordpath.read_bytes()),
                "original_jsonl_row": analysis["source_row"],
                "config_id": "61d7cc3701b2a42a",
                "pre_final_state_file": str(sf.relative_to(dest)),
                "pre_final_state_sha256": sha(sf.read_bytes()),
                "control": entries["control"],
                "treatment": entries["treatment"],
                "newly_visible_ids": sorted(set(allids["treatment"]) - set(allids["control"])),
                "no_longer_visible_ids": sorted(set(allids["control"]) - set(allids["treatment"])),
                "only_payload_difference": "messages",
                "changed_message_indices": [1],
                "snapshot_non_evidence_fields_identical": True,
                "all_treatment_source_passages_exactly_in_historical_state": True,
                "context_total_limit": 24000,
                "selector_final_turn_limit": 23600,
                "final_instruction_reserve": 400,
                "max_output_tokens": 1024,
                "max_total_run_tokens_historical": 30000,
                "new_model_calls": 0,
            }
        )
    manifest = {
        "schema": "group-b-final-paired-diagnostic-v1",
        "design": "same historical observations and prompt procedure; one final API turn per arm, not a full fresh agent run",
        "frozen_source_commit": COMMIT,
        "runtime_source_digest_recorded": "bdf0d95892e14fb49103f76d768542379812abf620b85962d97553957a3c10d9",
        "context_source_sha256": frozen["frozen_file_sha256"]["src/rag_agent/agent/context.py"],
        "hook_file": "../context_retention_hook.py",
        "hook_sha256": hooksha,
        "validation_source_sha256": provenance,
        "validation_script": "../validate_paired_response.py",
        "validation_script_sha256": sha((root / "validate_paired_response.py").read_bytes()),
        "preparation_script_sha256": sha(Path(__file__).read_bytes()),
        "request_hash_definition": "file_sha256 hashes exact UTF-8 file bytes; canonical_request_sha256 hashes sort_keys=True, ensure_ascii=False, compact JSON; messages_sha256 uses same canonicalization of messages only",
        "provider_mapping": "Prepared payloads retain original deepseek-v4-flash, thinking.type=disabled. Root must convert BOTH arms identically to Bailian 0731, including provider-specific thinking parameter, and record converted payload hashes separately. Do not mix converted and original hashes.",
        "budget_note": "Equal configured ceilings; serialized input lengths need not be identical. No answer-length, context, or retrieval budget increase. These isolated final-turn calls do not reuse historical token counters as new-model consumption.",
        "citation_validation": "Use private per-arm validation-prefix.json plus original pre-final-state.json, append new actual api_attempt and assistant; run frozen _validate_final with read-only corpus adapter. Validate IDs via earlier successful tool observations AND per-arm request visibility. Keep raw model content, parsed answer, parser/citation status, and EM separate. Grounding validation proves provenance, not semantic entailment.",
        "cases": cases,
    }
    save(dest / "pair-manifest.json", manifest)
    print(
        json.dumps(
            {
                "cases": [
                    {
                        "id": c["case_id"],
                        "control_chars": c["control"]["messages_characters"],
                        "treatment_chars": c["treatment"]["messages_characters"],
                        "added": c["newly_visible_ids"],
                        "removed": c["no_longer_visible_ids"],
                    }
                    for c in cases
                ],
                "hook_sha256": hooksha,
                "new_api_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
