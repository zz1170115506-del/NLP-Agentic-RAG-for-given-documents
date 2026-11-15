"""Final no-label structural/HTTP/usage/latency audit; never calls the API."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from acceptance_diagnostics_summary import duration
from acceptance_validation_analysis import FIELDS, distribution
from audit_predictions import audit
from rag_agent.evaluation.io import file_sha256, iter_jsonl, read_predictions
from rag_agent.evaluation.validate import run_metadata, validate_record


def main():
    sha_path = Path("work/acceptance/independent-resume-sha.json")
    sha_checks = json.loads(sha_path.read_text())
    for split in ("validation", "test"):
        root = Path(f"outputs/acceptance-{split}100-v1")
        prediction_path = root / f"{split}_prediction.jsonl"
        question_path = Path("data/validation-questions.jsonl" if split == "validation" else "data/test.jsonl")
        raw, questions = list(iter_jsonl(prediction_path)), list(iter_jsonl(question_path))
        if len(raw) != 100 or len(questions) != 100 or any(set(r) != FIELDS for r in raw):
            raise ValueError("Requires 100 exact six-field records")
        if [(r["id"], r["question"]) for r in raw] != [(r["id"], r["question"]) for r in questions]:
            raise ValueError("Question/ID/order mismatch")
        result = audit(question_path, prediction_path, official_compat=True, score=False)
        result.update(exact_six_fields=True, exact_question_id_order=True,
                      prediction_sha256=file_sha256(prediction_path), input_sha256=file_sha256(question_path))
        predictions = read_predictions(prediction_path)
        rows, response_ids, dates, formal_reasons = [], [], set(), Counter()
        for record in predictions:
            attempts = [event for event in record.trajectory if event.get("event") == "api_attempt"]
            for event in attempts:
                response = event.get("response") or {}
                response_ids.append(response.get("id"))
                if response.get("created"):
                    dates.add(datetime.fromtimestamp(response["created"], timezone.utc).date().isoformat())
            formal_reasons.update(validate_record(record, formal=True))
            rows.append({"id": record.id, "status": run_metadata(record)[1].get("status"),
                         "total_tokens": record.total_tokens, "tool_calls": record.tool_calls,
                         "http_attempts": len(attempts), "seconds": duration(record.trajectory)[0]})
        result["rows"] = rows
        result["raw_http_response_ids_unique_nonempty"] = bool(all(response_ids)) and len(response_ids) == len(set(response_ids))
        result["formal_record_error_reasons"] = dict(formal_reasons)
        result["latency_seconds"] = distribution([r["seconds"] for r in rows])
        result["timing_note"] = "Per-question monotonic elapsed seconds; sum is not parallel wall time"
        result["tools_per_question"] = distribution([r["tool_calls"] for r in rows])
        result["tokens_per_question"] = distribution([r["total_tokens"] for r in rows])
        result["http_per_question"] = distribution([r["http_attempts"] for r in rows])
        result["response_utc_dates"] = sorted(dates)
        if dates != {"2026-11-15"}:
            raise ValueError("Review tariff for a different date")
        usage = result["raw_usage"]
        result["cache_hit_share_of_prompt"] = usage["prompt_cache_hit_tokens"] / usage["prompt_tokens"]
        result["tariff_estimate_cny"] = (usage["prompt_cache_hit_tokens"] * .02
                                         + usage["prompt_cache_miss_tokens"] + usage["completion_tokens"] * 4) / 1e6
        result["tariff"] = {"source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
                            "checked_date": "2026-11-15", "currency": "CNY",
                            "per_million_hit_miss_completion": [.02, 1, 4],
                            "note": "Sunday Flash off-peak tariff estimate, not returned/paid cost"}
        dry = json.loads((root / "independent-recovery-dry-run.json").read_text())
        cli = json.loads((root / "independent-cli-resume.json").read_text())
        result["recovery_dry_run"] = dry
        result["cli_resume"] = cli
        sha_checks[split]["after_sha256"] = file_sha256(prediction_path)
        sha_checks[split]["unchanged"] = sha_checks[split]["before_sha256"] == sha_checks[split]["after_sha256"]
        result["resume_file_sha256"] = sha_checks[split]
        if not sha_checks[split]["unchanged"] or dry["pending"] != 0 or dry["new_api_calls"] != 0:
            raise ValueError("Resume changed a completed prediction or found pending rows")
        (root / "independent-completion-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"split": split, **{key: result[key] for key in
              ("official_compat_valid", "citation_passed", "statuses", "total_tokens", "tool_calls",
               "http_attempts", "raw_usage", "latency_seconds", "tariff_estimate_cny", "cli_resume",
               "resume_file_sha256", "formal_record_error_reasons")}}, ensure_ascii=False, indent=2))
    sha_path.write_text(json.dumps(sha_checks, indent=2) + "\n")


if __name__ == "__main__":
    main()
