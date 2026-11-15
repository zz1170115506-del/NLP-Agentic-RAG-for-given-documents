"""Publish allowlisted acceptance statistics, never raw questions/answers/traces."""
from __future__ import annotations

import json
from pathlib import Path
import re


OUT = Path("docs/acceptance_evidence")


def read(path):
    return json.loads(Path(path).read_text())


def select(value, keys):
    return {key: value[key] for key in keys if key in value}


def save(name, value):
    forbidden = {"question", "answer", "text", "content", "messages", "search_queries", "query", "trajectory", "request", "response"}

    def scan(item):
        if isinstance(item, dict):
            if forbidden & set(item):
                raise ValueError(f"Private raw-content field in {name}")
            for nested in item.values():
                scan(nested)
        elif isinstance(item, list):
            for nested in item:
                scan(nested)

    scan(value)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if re.search(r"sk-[a-fA-F0-9]{16,}|/Users/|/private/|file://", text):
        raise ValueError(f"Sensitive token or absolute local path in {name}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text)


def feature_summary(value):
    return select(value, (
        "id", "engine", "feature", "status", "requested_model", "response_models",
        "tool_calls", "tool_names", "total_tokens", "raw_success_usage_total", "http_attempts",
        "http_statuses", "usage_complete", "selected_skills", "automatic_skills",
        "skill_bodies_in_actual_requests", "tool_results_in_followup_requests",
        "max_actual_request_chars", "feature_checks", "passed", "source_identity_unchanged"))


def main():
    for source, output in (
        ("work/acceptance/input-audit.json", "input-hashes.json"),
        ("work/acceptance/candidate-selection.json", "candidate-identity.json"),
        ("outputs/acceptance-validation100-v1/execution_binding.json", "validation-binding.json"),
        ("work/acceptance/indexes/index-acceptance-status.json", "index-status.json"),
        ("outputs/acceptance-validation100-v1/independent-recovery-dry-run.json", "validation-recovery.json"),
    ):
        save(output, read(source))
    save("requirements-verification.json", {
        "source": "COMP5423 project guide, August 2026 v1.0, all six pages read and visually inspected",
        "pdf_sha256": "1826731f2cba92f0c03a13888e2b2938174342bab468f68a1e3ac3eb6d54f13a",
        "requirement_count": 43, "course_program_ids": [f"C{i:02}" for i in range(1, 23)],
        "additional_task_ids": [f"X{i:02}" for i in range(1, 16)],
        "later_course_deliverable_ids": [f"L{i:02}" for i in range(1, 7)],
        "status_location": "../task_NLP-Agentic-RAG-for-given-documents_全项目程序验收与缺口补齐_prompt_2return.md",
        "note": "Requirements are separated into course minimum/bonus, extra task, and later report/video/submission. No instructor grading claim."})
    analysis = read("outputs/acceptance-validation100-v1/independent-analysis.json")
    # Keep compact per-ID counters; full analysis stays in the evidence archive.
    analysis["rows"] = [select(row, ("id", "status", "normalized_em", "normalized_token_f1",
                                    "total_tokens", "tool_calls", "http_attempts", "seconds", "stage_proxy"))
                        for row in analysis["rows"]]
    save("validation100-statistics.json", analysis)
    for split in ("validation", "test"):
        save(f"{split}100-completion-audit.json", read(
            f"outputs/acceptance-{split}100-v1/independent-completion-audit.json"))
    diagnostics = read("outputs/acceptance-diagnostics/independent-summary-final.json")
    diagnostic_keys = ("name", "prediction_sha256", "expected", "records", "provisional", "coverage",
                       "ordinary_record_passed", "official_compat_record_passed", "valid_record_rate",
                       "grounding_passed", "grounding_rate", "completed", "answered", "answer_rate",
                       "honest_abstentions", "failed", "statuses", "correct", "em", "f1", "tool_calls",
                       "total_tokens", "raw_usage", "usage_complete_records", "token_accounting_mismatches",
                       "http_attempts", "http_errors", "transport_errors", "sum_question_seconds",
                       "median_question_seconds", "mean_question_seconds", "timed_records",
                       "archived_attempts", "all_attempts_total_tokens", "all_attempts_tool_calls")
    save("diagnostic-comparison.json", {
        **select(diagnostics, ("scope", "questions_sha256", "labels_sha256", "question_ids", "scoring", "timing_note")),
        "runs": [select(run, diagnostic_keys) for run in diagnostics["runs"]]})
    features = read("outputs/acceptance-features-v1/summary.json")
    save("feature-probes.json", {**select(features, ("scope", "expected", "records", "passed", "total_tokens", "http_attempts")),
                                "cases": [feature_summary(case) for case in features["cases"]],
                                "supplement": feature_summary(read("outputs/acceptance-recovery-probe-v1/summary.json"))})
    web = read("work/acceptance/web/final-audit.json")
    save("final-cli-web.json", {
        **select(web, ("same_question", "same_answer", "same_config", "production_source_commit",
                       "web_server_restarted_after_freeze", "ui_evidence_observed", "download_observed")),
        "answer_relationship": "same calendar date; original answer strings differ",
        **{kind: select(web[kind], ("config_id", "total_tokens", "tool_calls", "compat_errors", "grounding_errors"))
           for kind in ("cli", "web")}})
    offline = read("work/acceptance/offline-summary.json")
    save("earlier-clean-install.json", select(offline, (
        "status", "python", "base_git_sha", "source_package_sha256", "main_pytest_passed",
        "agent12_pytest_passed", "agent12_subtests_passed", "agent12_source_changes_since_suite_run",
        "ruff", "pip_check", "installed_extras", "installed_cli_no_pythonpath",
        "unlabeled_prediction_count", "completed_demo_answers", "demo_abstentions", "rerun_attempts",
        "rerun_skipped", "api_calls", "reproduced_and_fixed", "provenance_policy", "scope")))
    context = read("work/acceptance/diagnostics/context-delivery-review.json")
    save("context-delivery.json", select(context, ("scope", "regression_before_fix", "regression_after_fix",
                                                   "fixed_file_sha256", "new_actual_api_after_fix")))
    save("frozen-regression.json", {"code_commit": "dab7646", "main_pytest_passed": 151,
         "agent12_unittest_passed": 70, "note": "Separate suites; earlier clean-install counts are separate checkpoints.",
         "private_log_locations": ["work/acceptance/final-pytest.log", "work/acceptance/final-agent12-unittest.log"]})
    benchmark = {}
    for route, name in (("encoder", "e5-cpu-shard1.json"), ("instruction", "qwen-cpu-shard1-local-tokenizer.json")):
        benchmark[route] = select(read(f"work/acceptance/indexes/{name}"), (
            "method", "device", "batch_size", "model_id", "revision", "corpus_fingerprint",
            "total_source_chunks", "before_source_chunks", "after_source_chunks", "added_source_chunks",
            "added_vector_rows", "added_shards", "ready", "elapsed_seconds_including_model_load_and_resume",
            "source_chunks_per_second_including_setup", "peak_rss_bytes"))
    benchmark["e5_batch_threads"] = read("work/acceptance/indexes/e5-batch-thread-benchmark.json")
    benchmark["bounded_retrieval"] = select(read("work/acceptance/indexes/bounded-sparse-e5.json"), (
        "scope", "questions_sha256", "labels_sha256", "corpus", "protocol", "deferred", "summary",
        "loaded_routes", "qwen_model_loaded", "peak_rss_bytes"))
    benchmark["sql_final"] = select(read("work/acceptance/indexes/sparse-sql-production-fix.json"), (
        "question_id", "seconds", "exact_ids_scores_offsets_urls", "exact_texts", "rows", "caveat"))
    benchmark["sql_interpretation"] = "No stable speedup established: original single-query approximately 24.49s, final 24.54s; concurrency/cache confounding."
    save("index-benchmarks.json", benchmark)
    print(json.dumps({"public_summary_files": sorted(p.name for p in OUT.glob("*.json")),
                      "sensitive_token_and_absolute_local_path_scan": "passed"}, indent=2))


if __name__ == "__main__":
    main()
