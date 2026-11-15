"""Audit two already-executed API arms and replay their proposed searches offline."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from reproduce_group_c import read_db, sha, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--attempt-dir", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--corpus-db", type=Path, required=True)
    p.add_argument("--sparse-db", type=Path, required=True)
    args = p.parse_args()
    private = args.root / "private"
    prepared = private / "1066-single-variable-seq20"
    output = private / "1066-executed-pair"
    expected_protocol = json.loads((prepared / "protocol.json").read_text())
    sparse, docs = read_db(args.sparse_db), read_db(args.corpus_db)
    actual, public = {}, {"id": "1066", "historical_api_sequence": 20, "status": "EXECUTED_NEXT_ACTION_ONLY",
                          "offline_api_calls": 0, "model_calls_by_this_script": 0, "arms": {}, "final_em": None,
                          "historical_evidence_budget": expected_protocol["evidence_allowance_unchanged"],
                          "context_limit": expected_protocol["context_chars_limit_unchanged"],
                          "single_evidence_slot_swap": expected_protocol["changed_evidence_list_index"],
                          "retained_evidence": expected_protocol["retained_evidence_id"],
                          "removed_evidence": expected_protocol["removed_evidence_id"]}
    conditions = json.loads((private / "semantic-notes.json").read_text())["1066"]["conditions"]
    for arm in ("control", "treatment"):
        attempt_path = args.attempt_dir / f"{arm}.api-attempt.json"
        event = json.loads(attempt_path.read_text())
        expected = json.loads((prepared / f"{arm}-request.json").read_text())
        expected["model"] = "deepseek-v4-flash-0731"
        expected.pop("thinking", None)
        expected["enable_thinking"] = False
        assert expected == event["request"], "Actual request differs beyond the identical provider adaptation"
        assert event["http_status"] == 200
        response = event["response"]
        assert response["model"] == "deepseek-v4-flash-0731"
        message = response["choices"][0]["message"]
        write(output / f"{arm}.api-attempt.json", event)
        calls = []
        for index, call in enumerate(message.get("tool_calls", []), 1):
            assert call["function"]["name"] == "search"
            arguments = json.loads(call["function"]["arguments"])
            query, top_k = arguments["query"], arguments.get("top_k", 5)
            tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE)))[:64]
            expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
            start = time.perf_counter()
            rows = sparse.execute("""SELECT r.doc_id,r.chunk_id,r.offset,r.text,r.url,c.score
                FROM (SELECT rowid,bm25(fts) AS score FROM fts WHERE fts MATCH ? ORDER BY score,rowid LIMIT ?) c
                JOIN records r ON r.seq=c.rowid ORDER BY c.score,r.seq""", (expression, top_k)).fetchall()
            elapsed = time.perf_counter() - start
            hits = []
            for rank, row in enumerate(rows, 1):
                hit = dict(row)
                hit.update(rank=rank, score=-hit["score"], end=hit["offset"]+len(hit["text"]))
                doc = dict(docs.execute("SELECT doc_id,text,url FROM documents WHERE doc_id=?", (hit["doc_id"],)).fetchone())
                assert doc["text"][hit["offset"]:hit["end"]] == hit["text"]
                destination = private / "documents" / f"{doc['doc_id']}.json"
                if not destination.exists():
                    write(destination, doc)
                hit["exact_preannotated_condition_spans"] = [i for i, condition in enumerate(conditions, 1)
                    if any(e["doc_id"] == hit["doc_id"] and hit["offset"] <= e["start"] and hit["end"] >= e["end"]
                           for e in condition.get("support", []))]
                hits.append(hit)
            calls.append(dict(index=index, tool_call_id=call["id"], name="search", arguments=arguments,
                              query_sha256=hashlib.sha256(query.encode()).hexdigest(), seconds=elapsed,
                              query_provenance="actual API next-action response; no labels used", offline_only=True,
                              sent_back_to_model=False, hits=hits))
            print(json.dumps({"arm": arm, "search_number": index, "hits": len(hits), "seconds": elapsed}), flush=True)
        write(output / f"{arm}-offline-searches.json", calls)
        actual[arm] = event
        public["arms"][arm] = dict(http_status=event["http_status"], response_model=response["model"],
            usage=response["usage"], finish_reason=response["choices"][0]["finish_reason"],
            api_attempt_sha256=sha(attempt_path), prepared_request_sha256=sha(prepared / f"{arm}-request.json"),
            exact_expected_request_after_provider_adaptation=True,
            calls=[{**{k: c[k] for k in ("index", "tool_call_id", "query_sha256", "seconds", "offline_only", "sent_back_to_model")},
                    "top_k": c["arguments"].get("top_k", 5),
                    "hits": [{k: h[k] for k in ("rank", "doc_id", "offset", "end", "exact_preannotated_condition_spans")} for h in c["hits"]]}
                   for c in calls])
    assert {k: v for k, v in actual["control"]["request"].items() if k != "messages"} == {
        k: v for k, v in actual["treatment"]["request"].items() if k != "messages"}
    public["provider_adaptation_same_both_arms"] = {"model": "deepseek-v4-flash-0731", "enable_thinking": False,
        "removed_field": "thinking", "all_other_payload_fields_match_prepared_pair": True}
    public["interpretation"] = "Both responses choose two search calls. The first query is identical; the treatment's second query uses the retained candidate and director, while control remains broad. Searches were executed only offline and never returned to the model; final EM is unmeasured. One pair measures a local next-action difference, not full-run accuracy or statistical reliability."
    write(output / "audit.json", public)
    write(args.root / "public" / "1066-pair-audit.json", public)
    sparse.close()
    docs.close()


if __name__ == "__main__":
    main()
