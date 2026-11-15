"""Export public metadata only; never emit question, answer, label or passage text."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_dir
    prediction = root / "bailian-baseline/prediction.jsonl"
    archive = root / "bailian-baseline/prediction.jsonl.attempts.jsonl"
    rows = read_jsonl(prediction)
    cases, events = [], []
    for row in rows:
        attempts = [e for e in row["trajectory"] if e.get("event") == "api_attempt"]
        events += [(f"baseline/{row['id']}", e) for e in attempts]
        cases.append({"case_id": row["id"], "status": row["trajectory"][-1].get("status"),
                      "has_answer": bool(row["answer"]), "tool_calls": row["tool_calls"],
                      "returned_total_tokens": row["total_tokens"], "api_attempts": len(attempts),
                      "response_models": sorted({e.get("response", {}).get("model") for e in attempts}),
                      "all_http_200": all(e.get("http_status") == 200 for e in attempts),
                      "all_enable_thinking_false": all(e["request"].get("enable_thinking") is False
                                                     for e in attempts)})
    for entry in read_jsonl(archive):
        row = entry["prediction"]
        events += [(f"superseded/{row['id']}", e) for e in row["trajectory"]
                   if e.get("event") == "api_attempt"]
    for name in ["connectivity.json", "connectivity-after-recharge.json"]:
        events.append((name, json.loads((root / name).read_text())))
    for row in read_jsonl(root / "project-tool-probe.jsonl"):
        events += [("synthetic_project_tool_probe", e) for e in row["trajectory"]
                   if e.get("event") == "api_attempt"]
    for path in sorted((root / "paired-diagnostics").glob("*/*.api-attempt.json")):
        events.append((path.relative_to(root).as_posix(), json.loads(path.read_text())))
    ledger, seen = [], set()
    for source, event in events:
        response = event.get("response") or {}
        usage = response.get("usage") or {}
        identity = response.get("id") or hashlib.sha256(json.dumps(
            event, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if identity in seen:
            raise ValueError("Duplicate API event in explicit accounting inputs")
        seen.add(identity)
        ledger.append({"source": source, "http_status": event.get("http_status"),
                       "response_id": response.get("id"), "response_model": response.get("model"),
                       "requested_model": event["request"]["model"],
                       "enable_thinking": event["request"].get("enable_thinking"),
                       "returned_total_tokens": usage.get("total_tokens"),
                       "usage_unknown": type(usage.get("total_tokens")) is not int,
                       "error_code": (response.get("error") or {}).get("code")})
    counts = Counter(e["http_status"] for e in ledger)
    result = {"scope": "fixed_nine_validation_cases_plus_disclosed_probes_and_conditional_pairs",
              "prediction_sha256": sha(prediction), "superseded_attempts_sha256": sha(archive),
              "canonical_case_count": len(cases), "canonical_returned_tokens": sum(r["total_tokens"] for r in rows),
              "api_calls_including_failed_attempts": len(ledger), "http_status_counts": dict(counts),
              "known_returned_tokens_all_calls": sum(e["returned_total_tokens"] or 0 for e in ledger),
              "calls_with_unknown_usage": sum(e["usage_unknown"] for e in ledger),
              "unknown_usage_explanation": "Errors without usage are not asserted to have zero billed tokens.",
              "billing_amount_estimated": False, "cases": cases, "api_ledger": ledger}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"cases", "api_ledger"}}))


if __name__ == "__main__":
    main()
