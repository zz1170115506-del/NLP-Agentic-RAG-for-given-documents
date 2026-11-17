"""Trace two completed live runs from candidate pools to actual API payloads, offline."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from retrieval_binding import groups, ordered_chunks, verify_search

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_evidence_retention import audit_record, coverage


# Fixed before examining the 2560-dimensional run. Coordinates use Unicode characters.
ANCHORS = {
    "58": {
        "funding_window": ("28406", 38806, 39216, "30e950c39578a499fc5297c9f95e1b6e5a6e8a84db3be3f3f5bcf167b57bcf28"),
        "award_and_grant": ("28406", 38992, 39072, "5072403959035f3f3f79e07af73b7d58d0b851914b806add998dd52153775b06"),
    },
    "788": {
        "hospital_before_1927": ("57904", 586, 684, "be5d634ae960d9dbef18832fd32455e38f0e7a2cdbd3869ce926994343707489"),
        "other_mosque_built_1860": ("95802", 120, 182, "606627b82f9cb4f8c60461a0e3b9e333cb5d6da9f4c25b541110f44c7f689dab"),
        "target_completion_1958": ("70534", 1930, 1967, "83a8e7c42286c616f03ef99e0f62d847599aecd4cdcae6725d515325f11012cc"),
        "target_completion_1985": ("56202", 3638, 3756, "56e04a196c1ef01a2b060177601efa4e94d0d45fbbdd9290a5abbcc7652f67ae"),
        "distance_list_origin": ("6743", 11, 50, "125bd3f080e7f6b98e0b53e5f0b62db60593a6437fb040737b997c75fbbb0d41"),
        "distance_list_hospital": ("6743", 723, 746, "927411cca4a3efe1ffd6ca6d58238e4264c7c01ce5e5c79aefb3fb957141703d"),
        "distance_list_target": ("6743", 885, 906, "e6a77a0442c65e85ca64319bd9185a2a2c41ce7446efe72c302afc84426351ea"),
    },
}


def require(test, msg):
    if not test:
        raise ValueError(msg)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def load_anchors(database):
    result = {}
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        for case, specs in ANCHORS.items():
            result[case] = []
            for label, (doc, offset, end, expected) in specs.items():
                body, = db.execute("SELECT text FROM documents WHERE doc_id=?", (doc,)).fetchone()
                snippet = body[offset:end]
                require(digest(snippet.encode()) == expected, "Anchor source changed: " + label)
                result[case].append(dict(label=label, doc_id=doc, offset=offset, end=end, text=snippet))
    return result


def collect_searches(rows, tools, anchors, dimension):
    require(len(rows) == len(tools), "Search count mismatch")
    output = []
    for i, (log, tool) in enumerate(zip(rows, tools), start=1):
        verify_search(log, tool, [], expected_dimension=dimension)
        rankings = log["diagnostics"]["qwen4b"]["rankings"]
        physical = ordered_chunks(rankings, "bm25_rank")
        returned = log["returned_chunk_ids"]
        require(i == log["search_index"], "Search index mismatch")
        matches = []
        for anchor in anchors:
            for rank in rankings:
                if rank["doc_id"] != anchor["doc_id"]:
                    continue
                doc, offset, length = rank["chunk_id"].split(":")
                require(doc == rank["doc_id"], "Malformed chunk ID")
                overlap = min(int(offset) + int(length), anchor["end"]) - max(int(offset), anchor["offset"])
                if overlap > 0:
                    matches.append(dict(anchor=anchor["label"], chunk=rank["chunk_id"], overlapping_chars=overlap,
                                        bm25_rank=rank["bm25_rank"], int8_rank=rank["int8_rank"],
                                        native_fp_rank=rank["full_rank"], returned=rank["chunk_id"] in returned))
        output.append(dict(index=i, tool_sequence=tool["sequence"], query_sha256=log["query_sha256"],
                           pool_sha256=digest(json.dumps(physical, separators=(",", ":")).encode()),
                           pool_size=len(physical), returned=returned, matches=matches))
    return output


def collect_run(directory, dimension, anchors):
    pred = directory / "prediction.jsonl"
    records = [json.loads(line) for line in pred.read_text().splitlines()]
    require([r["id"] for r in records] == ["960", "1035", "64", "231", "390", "58", "1155", "1066", "788"],
            "Expected the nine completed questions in the original order")
    meta = json.loads((directory / "prediction.jsonl.meta.json").read_text())
    require(meta["mode"] == "live" and meta["input_count"] == len(records), "Expected live-run metadata")
    events = groups(directory / "events.jsonl", "record")
    retrieval = groups(directory / "retrieval.jsonl", None)
    cases = {}
    for record in records:
        case = record["id"]
        if case not in anchors:
            continue
        keys = [key for key, traj in events.items() if key[0] == case and traj == record["trajectory"]]
        require(len(keys) == 1, "Attempt must match predictions one-to-one")
        public, private = audit_record(record, anchors[case])
        requests = private["requests"]
        require(public["all_tool_groups_paired"] and not public["unobserved_view_spans"] and requests,
                "Invalid request or tool binding")
        answers = [e for e in record["trajectory"] if e.get("event") == "answer"]
        require(len(answers) == 1 and answers[0]["answer"] == record["answer"], "Final answer event mismatch")
        citation_ids = answers[0].get("supporting_evidence", [])
        observed = [span for tool in private["tools"] for span in tool["returned_spans"]]
        target_reports = {}
        for anchor in anchors[case]:
            def visible(spans):
                return coverage(anchor, spans, require_id=False)["visible_chars"]
            tool_views = [dict(sequence=t["sequence"], method=t["tool_name"], chars=visible(t["returned_spans"]),
                               ids=sorted({s["evidence_id"] for s in t["returned_spans"] if visible([s])}))
                          for t in private["tools"] if visible(t["returned_spans"])]
            observed_ids = {eid for event in tool_views for eid in event["ids"]}
            views = []
            for req in requests:
                context = req["context_event"] or {}
                omitted = set(context.get("budget_omitted_ids", []))
                views.append(dict(api_sequence=req["sequence"], chars=visible(req["visible_spans"]),
                                  budget_omitted_anchor_ids=sorted(omitted & observed_ids)))
            cites = [v for v in requests[-1]["visible_spans"] if v["evidence_id"] in citation_ids and visible([v])]
            target_reports[anchor["label"]] = dict(
                doc_id=anchor["doc_id"], offset=anchor["offset"], end=anchor["end"],
                chars=anchor["end"]-anchor["offset"], text_sha256=digest(anchor["text"].encode()),
                union_tool_chars=visible(observed), tool_events=tool_views, api_views=views,
                final_chars=views[-1]["chars"], cited_final_chars=visible(cites),
                overlapping_cited_ids=sorted({v["evidence_id"] for v in cites}))
        search_tools = [e for e in record["trajectory"] if e.get("role") == "tool" and e.get("name") == "search"
                        and json.loads(e["content"]).get("ok") is True]
        cases[case] = dict(dimension=dimension, prediction_nonempty=bool(record["answer"]),
                           answer_sha256=digest(record["answer"].encode()), cited_ids=citation_ids,
                           actual_final_request=requests[-1]["sequence"], tool_counts=public["tool_type_counts"],
                           evidence=target_reports,
                           searches=collect_searches(retrieval[keys[0]], search_tools, anchors[case], dimension))
    require(set(cases) == set(anchors), "Missing focus question")
    return dict(prediction_sha256=digest(pred.read_bytes()), input_sha256=meta["source_sha256"], cases=cases)


def compare_queries(left, right):
    def index(row):
        by_query = defaultdict(list)
        for search in row["searches"]:
            by_query[search["query_sha256"]].append(search)
        return by_query

    before, after = index(left), index(right)
    rows = []
    for query in sorted(before.keys() & after.keys()):
        pairs = list(zip(before[query], after[query]))
        for a, b in pairs:
            require(a["pool_sha256"] == b["pool_sha256"], "Same query produced a different BM25 pool")
            rows.append(dict(query_sha256=query, search_256=a["index"], search_2560=b["index"],
                             same_pool=True, top_k_overlap=len(set(a["returned"]) & set(b["returned"]))))
    return dict(matched_occurrences=rows, distinct_shared_queries=len(before.keys() & after.keys()),
                unmatched_occurrences_256=len(left["searches"])-len(rows),
                unmatched_occurrences_2560=len(right["searches"])-len(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    anchors = load_anchors(args.documents)
    before = collect_run(args.baseline, 256, anchors)
    after = collect_run(args.candidate, 2560, anchors)
    require(before["input_sha256"] == after["input_sha256"], "Question file mismatch")
    data = dict(baseline_256=before, candidate_2560=after,
                paired_queries={case: compare_queries(before["cases"][case], after["cases"][case]) for case in anchors})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
