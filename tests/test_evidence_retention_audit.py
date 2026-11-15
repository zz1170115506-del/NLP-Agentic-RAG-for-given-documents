"""Audit checks must use actual API payloads, prior observations and exact spans."""
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_evidence_retention.py"
SPEC = importlib.util.spec_from_file_location("retention_audit", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def fixture_record(visible, *, actual_before_tool=False):
    span = {"evidence_id": "E1", "doc_id": "fixture-doc", "offset": 0,
            "text": "PRIVATE_PASSAGE", "chunk_id": "fixture-doc:0"}
    full_message = {"role": "system", "content": audit.PREFIX + json.dumps({"evidence": [span]})}
    actual_message = {"role": "system", "content": audit.PREFIX + json.dumps({"evidence": visible})}
    first = {"event": "api_attempt", "http_status": 200,
             "request": {"model": "fixture", "messages": [actual_message]},
             "response": {"model": "fixture", "usage": {"total_tokens": 7},
                          "choices": [{"message": {"content": "PRIVATE_RESPONSE"}}]}}
    events = [{"event": "run_start", "config_id": "fixture-config", "model": "fixture",
               "config": {"llm_base_url": "https://fixture.invalid/v1", "context_chars": 2000, "max_total_tokens": 100}},
              {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "search",
               "arguments": json.dumps({"query": "PRIVATE_QUERY"})}}]},
              {"role": "tool", "tool_call_id": "c1", "name": "search", "content": json.dumps(
                  {"ok": True, "data": {"results": [span]}})},
              {"event": "state", "state": {"evidence": [span]}},
              # The prepared request deliberately differs from the actual API view.
              {"event": "request", "messages": [full_message]}, first,
              {"role": "assistant", "content": "PRIVATE_FINAL"},
              {"event": "run_end", "status": "insufficient_evidence", "stop_reason": "insufficient_evidence",
               "usage_complete": True}]
    if actual_before_tool:
        events.insert(1, events.pop(5))
    for index, event in enumerate(events):
        event["sequence"] = index
    return {"id": "fixture-case", "question": "PRIVATE_QUESTION", "answer": "", "trajectory": events,
            "tool_calls": 1, "total_tokens": 7}


def test_visibility_uses_actual_payload_not_prepared_request():
    public, private = audit.audit_record(fixture_record([]), [])
    assert public["never_visible_observed_spans"] == 1
    assert public["requests"][0]["state_absent"] == 1
    assert private["question"] == "PRIVATE_QUESTION"
    exported = json.dumps(public)
    for secret in ["PRIVATE_QUESTION", "PRIVATE_QUERY", "PRIVATE_PASSAGE", "PRIVATE_RESPONSE", "PRIVATE_FINAL"]:
        assert secret not in exported


def test_exact_partial_window_is_not_counted_as_full_retention():
    view = {"evidence_id": "E1", "doc_id": "fixture-doc", "offset": 8, "text": "PASSAGE"}
    public, _ = audit.audit_record(fixture_record([view]), [])
    row = public["requests"][0]
    assert row["state_partial_visible"] == 1
    assert row["state_full_visible"] == 0
    assert row["state_visibility"][0]["visible_chars"] == 7
    assert row["unobserved_view_spans"] == 0


def test_future_observation_does_not_validate_an_earlier_view():
    view = {"evidence_id": "E1", "doc_id": "fixture-doc", "offset": 0, "text": "PRIVATE_PASSAGE"}
    public, _ = audit.audit_record(fixture_record([view], actual_before_tool=True), [])
    assert public["requests"][0]["unobserved_view_spans"] == 1
    assert public["requests"][0]["visible_spans"] == []
    assert public["evidence_lifetimes"][0]["final_request_visibility"] == "no_later_request"


def test_same_coordinates_with_changed_text_are_not_valid_provenance():
    view = {"evidence_id": "E1", "doc_id": "fixture-doc", "offset": 8, "text": "CHANGED"}
    public, _ = audit.audit_record(fixture_record([view]), [])
    assert public["requests"][0]["state_absent"] == 1
    assert public["requests"][0]["unobserved_view_spans"] == 1


def test_incomplete_records_are_refused_before_audit(tmp_path):
    record = fixture_record([])
    record["trajectory"].pop()
    path = tmp_path / "incomplete.jsonl"
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(ValueError, match="Only ended"):
        audit.load_records(path)


def test_orphan_tool_result_is_reported():
    assert audit.pairing_errors([{"role": "tool", "tool_call_id": "missing"}]) == [
        "tool_without_matching_visible_assistant_call"]


def test_tool_pair_with_intervening_user_message_is_not_atomic():
    messages = [{"role": "assistant", "tool_calls": [{"id": "c1"}]},
                {"role": "user", "content": "interruption"},
                {"role": "tool", "tool_call_id": "c1"}]
    assert audit.pairing_errors(messages) == ["tool_group_interrupted_by_non_tool_message"]


def test_target_disclosure_and_id_are_required(tmp_path):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps([{"case_id": "fixture-case", "doc_id": "fixture-doc", "offset": 0, "end": 10}]))
    with pytest.raises(ValueError, match="selection basis"):
        audit.load_targets(path, {"fixture-case"})
