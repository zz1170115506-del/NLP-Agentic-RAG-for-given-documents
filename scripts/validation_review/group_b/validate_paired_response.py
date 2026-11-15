#!/usr/bin/env python3
"""Validate one real paired final response offline against frozen provenance.
No model call, credential read, original-repo writes, or DocumentStore constructor.
Outputs contain answers and must remain private. Empty answers are reported separately
from provider failures; corpus grounding does not establish semantic correctness.
"""

import argparse
import copy
import hashlib
import json
import re
import sqlite3
import string
import sys
from pathlib import Path
from types import SimpleNamespace


def sha(b):
    return hashlib.sha256(b).hexdigest()


def norm(s):
    return " ".join(
        re.sub(r"\b(a|an|the)\b", " ", s.lower().translate(str.maketrans("", "", string.punctuation))).split()
    )


def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class ReadOnlyStore:
    def __init__(self, p):
        self.conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
        self.conn.execute("PRAGMA query_only=ON")

    def get(self, doc_id):
        row = self.conn.execute("SELECT doc_id,text,url FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return SimpleNamespace(doc_id=row[0], text=row[1], url=row[2]) if row else None

    def close(self):
        self.conn.close()


def validate(repo, pairs, qid, arm, response, actual_request=None, grade=True):
    manifest = json.loads((pairs / "pair-manifest.json").read_text())
    case = next(c for c in manifest["cases"] if c["case_id"] == qid)
    armdata = case[arm]
    for rel, expected in manifest["validation_source_sha256"].items():
        if sha((repo / rel).read_bytes()) != expected:
            raise ValueError("Frozen validation source hash mismatch: " + rel)
    for field in ["request", "validation_prefix"]:
        p = pairs / armdata[field + "_file"]
        expected = armdata["file_sha256" if field == "request" else "validation_prefix_sha256"]
        if sha(p.read_bytes()) != expected:
            raise ValueError("Paired artifact hash mismatch: " + p.name)
    statefile = pairs / case["pre_final_state_file"]
    if sha(statefile.read_bytes()) != case["pre_final_state_sha256"]:
        raise ValueError("State artifact hash mismatch")
    prepared = json.loads((pairs / armdata["request_file"]).read_text())
    audit = json.loads((pairs / armdata["validation_prefix_file"]).read_text())
    if response.get("event") == "api_attempt":
        event = response
        if actual_request is None:
            actual_request = event.get("request")
        response = event.get("response") or {}
        http_status = event.get("http_status")
    else:
        http_status = None
    request = actual_request or prepared
    if request.get("messages") != prepared["messages"]:
        raise ValueError("Actual API messages differ from the prepared arm")
    # Only identical provider/model translation is permitted across arms. These
    # fields affect the paired experiment and must remain exactly as prepared.
    for field in ["tools", "tool_choice", "max_tokens", "temperature", "stream"]:
        if request.get(field) != prepared.get(field):
            raise ValueError("Actual request changed controlled field: " + field)
    result = {
        "case_id": qid,
        "arm": arm,
        "condition": case["condition"],
        "reference_assisted": case["reference_assisted"],
        "frozen_source_commit": manifest["frozen_source_commit"],
        "hook_sha256": manifest["hook_sha256"],
        "input_prepared_file_sha256": armdata["file_sha256"],
        "actual_request_supplied": actual_request is not None,
        "actual_canonical_request_sha256": sha(canonical(request)),
        "response_sha256": sha(canonical(response)),
        "response_model": response.get("model"),
        "usage": response.get("usage"),
        "http_status": http_status,
        "schema_and_citation_check": "not_run",
        "semantic_entailment": "requires case-specific review; grounding is not entailment",
        "new_network_calls_by_validator": 0,
    }
    if response.get("error"):
        result.update(
            status="provider_error",
            error_code=response["error"].get("code"),
            model_abstention=False,
            raw_final_content=None,
            parsed_answer=None,
        )
        return result
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        result.update(
            status="invalid_provider_response", model_abstention=False, raw_final_content=None, parsed_answer=None
        )
        return result
    message = choices[0].get("message") or {}
    content = message.get("content")
    result.update(raw_final_content=content, finish_reason=choices[0].get("finish_reason"))
    if message.get("tool_calls"):
        result.update(
            status="unexpected_tool_calls_in_final_turn",
            schema_and_citation_check="rejected",
            model_abstention=False,
            parsed_answer=None,
        )
        return result
    sys.path.insert(0, str((repo / "agent12").resolve()))
    sys.path.insert(0, str((repo / "src").resolve()))
    from rag_agent.agent import loop
    from rag_agent.schemas import AgentState

    if Path(loop.__file__).resolve() != (repo / "src/rag_agent/agent/loop.py").resolve():
        raise ValueError("Imported validator from an unexpected runtime")
    state = AgentState.model_validate(json.loads(statefile.read_text()))
    # request event is the visibility contract used by the frozen resolver. Ensure
    # it records the exact actual messages; retain all original earlier tool events.
    audit[-1]["messages"] = copy.deepcopy(request["messages"])
    audit[-1]["tools"] = copy.deepcopy(request["tools"])
    audit[-1]["max_tokens"] = request["max_tokens"]
    audit.append(
        {
            "event": "api_attempt",
            "sequence": len(audit),
            "request": request,
            "response": response,
            "http_status": http_status,
            "diagnostic_only": True,
        }
    )
    audit.append(
        {
            "role": "assistant",
            "sequence": len(audit),
            "content": content,
            "model": response.get("model"),
            "usage": response.get("usage"),
            "finish_reason": choices[0].get("finish_reason"),
        }
    )
    store = ReadOnlyStore(repo / "data/course-full/documents.sqlite")
    try:
        try:
            final, status = loop._validate_final(content, state, store, audit)
            result.update(
                status=status,
                parsed_final=final.model_dump(),
                parsed_answer=final.answer.strip(),
                schema_and_citation_check="passed",
                model_abstention=status == "insufficient_evidence",
                resolved_evidence_ids=state.selected_evidence_ids,
            )
        except (ValueError, TypeError) as exc:
            result.update(
                status="invalid_final",
                schema_and_citation_check="rejected",
                validation_error=str(exc),
                model_abstention=False,
                parsed_answer=None,
            )
    finally:
        store.close()
    if grade:
        label = json.loads((pairs.parent / "private" / f"{qid}-label.json").read_text())["answer"]
        result.update(
            normalized_answer=norm(result.get("parsed_answer") or ""),
            normalized_reference=norm(label),
            normalized_em=int(
                result["status"] == "completed" and norm(result.get("parsed_answer") or "") == norm(label)
            ),
        )
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, default=Path("work/deepseek-official-compat"))
    p.add_argument("--pairs", type=Path, default=Path("work/validation-review-drafts/group-b/paired-final-diagnostics"))
    p.add_argument("--case", choices=["231", "390", "58"], required=True)
    p.add_argument("--arm", choices=["control", "treatment"], required=True)
    p.add_argument("--response", type=Path, required=True)
    p.add_argument("--actual-request", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    response = json.loads(a.response.read_text())
    request = json.loads(a.actual_request.read_text()) if a.actual_request else None
    result = validate(a.repo, a.pairs, a.case, a.arm, response, request)
    dest = a.out or a.pairs / "private" / f"{a.case}-{a.arm}.response-validation.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    dest.chmod(0o600)
    print(
        json.dumps(
            {
                k: result.get(k)
                for k in [
                    "case_id",
                    "arm",
                    "status",
                    "schema_and_citation_check",
                    "model_abstention",
                    "normalized_em",
                    "error_code",
                ]
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc))
        raise SystemExit(1)
