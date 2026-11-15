"""One bounded connectivity probe; credentials stay in the ignored local .env."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from urllib.parse import urlparse

import httpx
from rag_agent.config import Settings
from rag_agent.llm.provider import scrub


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for name in list(os.environ):
        if name.startswith("LLM_"):
            os.environ.pop(name)
    cfg = Settings.load(args.config)
    cfg.check_live()
    assert urlparse(cfg.llm_base_url).hostname == "dashscope.aliyuncs.com"
    payload = {"model": cfg.llm_model, "messages": [{"role": "user", "content": "Reply with OK only."}],
               "max_tokens": 32, "temperature": 0, "stream": False, "enable_thinking": False}
    started = time.monotonic()
    record = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "request": payload,
              "endpoint": cfg.llm_base_url, "config_id": cfg.config_id, "kind": "connectivity_only"}
    with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
        response = client.post(cfg.llm_base_url + "/chat/completions", json=payload,
                               headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    record.update(http_status=response.status_code, elapsed_seconds=time.monotonic() - started)
    try:
        record["response"] = response.json()
    except ValueError:
        record["response"] = {"non_json_response": response.text[:2000]}
    record = scrub(record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    result = record["response"]
    matched = response.is_success and cfg.accepts_response_model(result.get("model"))
    print(json.dumps({"http_status": response.status_code, "requested_model": cfg.llm_model,
                      "response_model": result.get("model"), "model_matches": matched,
                      "usage": result.get("usage"), "error": result.get("error"),
                      "elapsed_seconds": record["elapsed_seconds"]}, ensure_ascii=False))
    return 0 if matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
