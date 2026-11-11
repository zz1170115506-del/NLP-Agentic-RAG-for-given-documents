"""Explicit real-model pair/long-input checks; no LLM API or benchmark labels."""
import argparse
import json
from pathlib import Path

from rag_agent.config import Settings
from rag_agent.retrieval.rerank import LocalCrossEncoder
from rag_agent.schemas import SearchHit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/rerank-eval-d.yaml")
    parser.add_argument("--output", default="outputs/rerank-eval/real-model-smoke.json")
    args = parser.parse_args()
    config = Settings.load(args.config)
    ranker = LocalCrossEncoder(config)
    texts = ["Berlin is a city in Germany.", "Mars is known as the Red Planet."]
    hits = [SearchHit(doc_id=f"synthetic-{i}", chunk_id=f"synthetic-{i}:0:{len(text)}",
                      offset=0, text=text, score=1 / (i + 1), method="hybrid")
            for i, text in enumerate(texts)]
    ordered, short_diag = ranker.rerank("Which planet is known as the Red Planet?", hits, 2)
    assert ordered[0].doc_id == "synthetic-1"
    # Deliberately exceed 512 tokens; the relevant sentence is at the tail.
    long_text = "电路🙂 " + "Irrelevant maintenance information. " * 700 + "The launch code is cyan-2049."
    long_hit = SearchHit(doc_id="synthetic-long", chunk_id="synthetic-long:7:long",
                         offset=7, text=long_text, score=1.0, method="hybrid")
    result, long_diag = ranker.rerank("What is the launch code?", [long_hit], 1)
    windows = long_diag["candidates"][0]["windows"]
    assert len(windows) <= config.rerank_max_windows
    assert max(w["pair_tokens"] for w in windows) <= 512
    assert windows[-1]["end"] == 7 + len(long_text)
    assert result[0].text == long_text and result[0].offset == 7
    assert long_diag["candidates"][0]["rerank_score"] == max(w["score"] for w in windows)
    assert windows[-1]["score"] == max(w["score"] for w in windows)
    try:
        ranker.rerank("planet " * 600, hits, 2)
    except ValueError:
        assert ranker.last_diagnostics["status"] == "error"
    else:
        raise AssertionError("Overlong query must be explicitly rejected")
    summary = {"status": "passed", "scope": "real model on synthetic query/passage probes",
               "api_calls": 0, "checks": ["relevant_pair_ranked_first", "full_pair_token_budget",
                 "long_passage_tail_scored", "max_window_score", "original_unicode_coordinates",
                 "bounded_windows_with_omissions_reported", "overlong_query_explicit_error"],
               "short_pair": short_diag, "long_pair": long_diag,
               "overlong_query": ranker.last_diagnostics}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": "passed", "model": short_diag["model"], "checks": summary["checks"]}))


if __name__ == "__main__":
    main()
