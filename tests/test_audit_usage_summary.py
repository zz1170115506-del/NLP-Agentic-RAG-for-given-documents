"""Independent reporting must not count raw responses and mirrored usage twice."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_auditor():
    path = Path(__file__).resolve().parents[1] / "scripts/audit_predictions.py"
    spec = importlib.util.spec_from_file_location("audit_predictions_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("version", [1, 2])
def test_success_and_billed_retry_each_count_once(version):
    good = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
            "prompt_cache_hit_tokens": 6, "prompt_cache_miss_tokens": 4}
    retry = {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5,
             "prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 2}
    prediction = SimpleNamespace(trajectory=[
        {"event": "run_start", "audit_version": version, "config": {"llm_base_url": "https://api.deepseek.com"}},
        {"event": "api_attempt", "outcome": "http_error", "usage_unknown": False, "response": {"usage": retry}},
        {"event": "api_usage", "usage": retry},
        {"event": "api_attempt", "outcome": "received", "response": {"usage": good}},
        {"role": "assistant", "usage": good}, {"event": "run_end"}])
    result = load_auditor().usage_audit([prediction])
    assert result["raw_usage"]["total_tokens"] == 17
    assert result["raw_usage"]["prompt_cache_hit_tokens"] == 8
    assert result["raw_usage"]["prompt_cache_miss_tokens"] == 6
    assert result["usage_response_count"] == 2
    assert result["reported_cost_usd"] is None
    assert result["responses_with_cost"] == 0


def test_unknown_currency_cost_is_not_relabelled_usd():
    prediction = SimpleNamespace(trajectory=[
        {"event": "run_start", "audit_version": 2, "config": {"llm_base_url": "https://api.deepseek.com"}},
        {"event": "api_attempt", "outcome": "received", "response": {"usage": {"total_tokens": 12, "cost": 0.01}}},
        {"event": "run_end"}])
    result = load_auditor().usage_audit([prediction])
    assert result["reported_cost_provider_units"] == 0.01
    assert result["reported_cost_usd"] is None
    assert result["reported_cost_currency"] is None
