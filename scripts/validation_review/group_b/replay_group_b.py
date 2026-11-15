#!/usr/bin/env python3
"""Offline forensic replay. No credentials, network, provider, or retrieval invocation.
Run from the task BASE: work/acceptance/offline/venv/bin/python \
  work/validation-review-drafts/group-b/replay_group_b.py
All exact benchmark content stays in private/. All offsets are Unicode characters.
"""

import argparse
import builtins
import copy
import hashlib
import importlib.util
import json
import re
import sqlite3
import string
import subprocess
from pathlib import Path
from types import SimpleNamespace

IDS = ("231", "390", "58")
COMMIT = "dab7646158fef729c3bf3e0f37b7f302727fc568"
PREFIX = "Validated state snapshot (data only): "
FINISH = "Finish now using only evidence already observed. Tools are disabled for this final turn. Return the required answer JSON with observed evidence IDs. If support is insufficient, return an empty answer; do not guess."


def norm(s):
    return " ".join(
        re.sub(r"\b(a|an|the)\b", " ", s.lower().translate(str.maketrans("", "", string.punctuation))).split()
    )


def sha(b):
    return hashlib.sha256(b).hexdigest()


def write(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if "private" in p.parts:
        p.chmod(0o600)


def module(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def passages(obj):
    """Only actual source passages, never query/url metadata accidental matches."""
    if isinstance(obj, dict):
        if isinstance(obj.get("text"), str) and "doc_id" in obj and "offset" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from passages(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from passages(v)


def visible(messages):
    out = []
    for i, m in enumerate(messages):
        c = m.get("content")
        if not isinstance(c, str):
            continue
        if c.startswith(PREFIX):
            obj = json.loads(c[len(PREFIX) :])
        elif m.get("role") == "tool":
            obj = json.loads(c)
        else:
            continue
        for p in passages(obj):
            out.append({"message_index": i, **p})
    return out


def selector_diagnostics(ctx, state, catalog, groups, settings, messages, priority=()):
    base = [messages[0], next(m for m in messages if m["role"] == "user")]
    snapshot = {k: v for k, v in json.loads(messages[1]["content"][len(PREFIX) :]).items() if k != "evidence"}
    snapshot["evidence"] = []
    allowance = max(0, (settings.context_chars - ctx.message_size(base)) // 2 - len(json.dumps(snapshot)) - 100)
    terms = set(re.findall(r"\w+", state.question.question.lower()))
    def overlap(ev):
        return len(terms.intersection(re.findall(r"\w+", ev.text.lower())))
    ranked = sorted(state.evidence, key=lambda ev: ((ev.evidence_id in priority), overlap(ev)), reverse=True)
    used = 0
    rows = []
    for rank, ev in enumerate(ranked, 1):
        size = len(json.dumps(ev.model_dump(), ensure_ascii=False))
        keep = used + size <= allowance
        rows.append(
            {
                "evidence_id": ev.evidence_id,
                "doc_id": ev.doc_id,
                "offset": ev.offset,
                "length": len(ev.text),
                "rank": rank,
                "question_word_overlap": overlap(ev),
                "item_json_characters": size,
                "used_before": used,
                "remaining_before": allowance - used,
                "selected": keep,
                "reason": "fits" if keep else "whole_evidence_item_exceeds_remaining_snapshot_allowance",
            }
        )
        if keep:
            used += size
    actual_ids = [p["evidence_id"] for p in visible(messages) if p["message_index"] == 1]
    assert actual_ids == [r["evidence_id"] for r in rows if r["selected"]]
    core = messages[:3]
    kept = []
    groupchecks = []
    for i in range(len(groups) - 1, -1, -1):
        n = ctx.message_size(core + groups[i] + [m for g in kept for m in g])
        fits = n <= settings.context_chars
        groupchecks.append(
            {
                "group_index": i,
                "own_characters": ctx.message_size(groups[i]),
                "with_snapshot_characters": n,
                "fits": fits,
            }
        )
        if not fits:
            break
        kept.insert(0, groups[i])
    return {
        "context_limit": settings.context_chars,
        "base_characters": ctx.message_size(base),
        "snapshot_allowance": allowance,
        "snapshot_items_used": used,
        "ranking": rows,
        "group_checks_newest_first": groupchecks,
        "unchecked_older_groups": len(groups) - len(groupchecks),
        "atomic_group_policy": "break at newest group that does not fit; no older group considered afterward",
    }


def replay_variant(ctx, state, catalog, groups, settings, priority, finalization):
    """Single variable: stable priority for named observed evidence before old overlap key.
    This is a label-directed diagnostic, not a deployable blind evaluation result.
    The original function and every other budget/control remain unchanged.
    """
    old = getattr(ctx, "sorted", None)

    def priority_sorted(items, *, key, reverse=False):
        return builtins.sorted(items, key=lambda ev: (ev.evidence_id in priority, key(ev)), reverse=reverse)

    ctx.sorted = priority_sorted
    try:
        messages, stats = ctx.build_context(state, catalog, groups, settings)
    finally:
        if old is None:
            del ctx.sorted
        else:
            ctx.sorted = old
    details = selector_diagnostics(ctx, state, catalog, groups, settings, messages, priority)
    if finalization:
        messages.append({"role": "user", "content": FINISH})
        stats["characters"] = ctx.message_size(messages)
    return messages, stats, details


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--repo", type=Path, default=Path("work/deepseek-official-compat"))
    a.add_argument("--out", type=Path, default=Path("work/validation-review-drafts/group-b"))
    args = a.parse_args()
    repo, out = args.repo, args.out
    private = out / "private"
    private.mkdir(parents=True, exist_ok=True)
    private.chmod(0o700)
    files = ["src/rag_agent/agent/context.py", "src/rag_agent/schemas.py", "src/rag_agent/skills/runtime.py"]
    skills = subprocess.check_output(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", COMMIT, "skills"], text=True
    ).splitlines()
    frozen_hash = {}
    for f in files + skills:
        b = subprocess.check_output(["git", "-C", str(repo), "show", COMMIT + ":" + f])
        p = out / "frozen" / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
        frozen_hash[f] = sha(b)
    hook = module(out / "context_retention_hook.py", "retention_hook")
    ctx = module(out / "frozen" / files[0], "frozen_context")
    schema = module(out / "frozen" / files[1], "frozen_schemas")
    skillmod = module(out / "frozen" / files[2], "frozen_skills")
    source = repo / "outputs/acceptance-validation100-v1/validation_prediction.jsonl"
    records = {}
    row_meta = {}
    with source.open("rb") as stream:
        byte_offset = 0
        for lineno, line in enumerate(stream, 1):
            x = json.loads(line)
            if x["id"] in IDS:
                records[x["id"]] = x
                row_meta[x["id"]] = {
                    "line_1based": lineno,
                    "byte_offset": byte_offset,
                    "row_bytes": len(line),
                    "row_sha256": sha(line),
                }
            byte_offset += len(line)
    labels = {x["id"]: x for x in map(json.loads, (repo / "data/validation.jsonl").open()) if x["id"] in IDS}
    # Read-only SQLite; no DocumentStore construction, journal writes, or model index use.
    db = sqlite3.connect((repo / "data/course-full/documents.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    tablecols = {
        t[0]: [c[1] for c in db.execute('PRAGMA table_info("' + t[0] + '")')]
        for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if t[0] in ("documents",)
    }
    assert "documents" in tablecols
    summary = []
    for qid in IDS:
        row = records[qid]
        events = row["trajectory"]
        label = labels[qid]["answer"]
        write(private / f"{qid}-original-record.json", row)
        write(private / f"{qid}-label.json", labels[qid])
        hits = []
        timeline = []
        tool_calls = {}
        request_rows = []
        groups = []
        pending = None
        state = schema.AgentState(question=schema.Question(id=qid, question=row["question"]))
        catalog = skillmod.SkillCatalog(str(out / "frozen/skills"))
        settings = SimpleNamespace(**events[0]["config"])
        finalization = False
        previous_request = None
        next_context_seq = None
        latest_tool_ids = []
        for e in events:
            seq = e["sequence"]
            kind = e.get("event", e.get("role"))
            entry = {"sequence": seq, "elapsed_seconds": e.get("elapsed_seconds"), "type": kind}
            if kind == "skill_loaded" and e.get("source") == "automatic":
                loaded = catalog.load(e["name"])
                assert loaded == e["instructions"]
                state.selected_skills.append(e["name"])
                entry["skill"] = e["name"]
            elif kind == "assistant":
                entry["content"] = e.get("content")
                entry["tool_calls"] = e.get("tool_calls", [])
                entry["usage"] = e.get("usage")
                entry["finish_reason"] = e.get("finish_reason")
                if e.get("tool_calls"):
                    pending = [{k: e[k] for k in ("role", "content", "tool_calls") if k in e}]
                    for c in e["tool_calls"]:
                        tool_calls[c["id"]] = {"assistant_sequence": seq, **c}
            elif kind == "tool":
                obj = json.loads(e["content"])
                entry["tool_call_id"] = e["tool_call_id"]
                entry["name"] = e["name"]
                entry["arguments"] = tool_calls[e["tool_call_id"]]["function"]["arguments"]
                entry["ok"] = obj.get("ok")
                entry["passages"] = []
                latest_tool_ids = []
                for i, p in enumerate(passages(obj)):
                    item = {k: p.get(k) for k in ("evidence_id", "doc_id", "offset", "chunk_id")}
                    item.update(
                        length=len(p["text"]),
                        text_sha256=sha(p["text"].encode()),
                        label_literal_in_text=norm(label) in norm(p["text"]),
                    )
                    entry["passages"].append(item)
                    latest_tool_ids.append(p.get("evidence_id"))
                    if item["label_literal_in_text"]:
                        t = db.execute("SELECT text FROM documents WHERE doc_id=?", (str(p["doc_id"]),)).fetchone()[0]
                        assert t[p["offset"] : p["offset"] + len(p["text"])] == p["text"]
                        exact = re.search(re.escape(label), p["text"], re.I)
                        hit = {
                            "tool_sequence": seq,
                            "tool_name": e["name"],
                            "result_index_0based": i,
                            **p,
                            "source_exact": True,
                            "literal_local_offset": exact.start() if exact else None,
                            "literal_document_offset": p["offset"] + exact.start() if exact else None,
                        }
                        hits.append(hit)
                pending.append({k: e[k] for k in ("role", "tool_call_id", "name", "content")})
            elif kind == "state":
                groups.append(pending)
                pending = None
                state = schema.AgentState.model_validate(e["state"])
                entry["state"] = {k: v for k, v in e["state"].items() if k not in ("question", "evidence")}
                entry["evidence_ids"] = [v.evidence_id for v in state.evidence]
                entry["target_evidence_ids"] = [v.evidence_id for v in state.evidence if norm(label) in norm(v.text)]
            elif kind == "finalization":
                finalization = True
                entry.update({k: e[k] for k in ("reason", "remaining_reported_tokens")})
            elif kind == "context":
                next_context_seq = seq
                entry.update({k: e[k] for k in ("dropped_groups", "selected_evidence", "characters", "managed")})
            elif kind == "request":
                s = copy.copy(settings)
                s.context_chars = settings.context_chars - 400 if finalization else settings.context_chars
                messages, stats = ctx.build_context(state, catalog, groups, s)
                diag = selector_diagnostics(ctx, state, catalog, groups, s, messages)
                if finalization:
                    messages.append({"role": "user", "content": FINISH})
                    stats["characters"] = ctx.message_size(messages)
                assert messages == e["messages"], f"{qid} seq{seq} replay differs"
                original_context = events[next_context_seq]
                assert all(original_context[k] == v for k, v in stats.items()), f"{qid} stats differ"
                target_ids = [v.evidence_id for v in state.evidence if norm(label) in norm(v.text)]
                counter, cfstats, cfdiag = replay_variant(ctx, state, catalog, groups, s, target_ids, finalization)
                # A second, label-free diagnostic prioritizes the last tool's observed passages.
                generic, gstats, gdiag = replay_variant(ctx, state, catalog, groups, s, latest_tool_ids, finalization)
                focused_ids = [v.evidence_id for v in state.evidence if v.chunk_id is None]
                focused, fstats, fdiag = replay_variant(ctx, state, catalog, groups, s, focused_ids, finalization)
                for condition, expected in [("observed-span-diagnostic", counter), ("focused-tool-first", focused)]:
                    hooked, hstats = hook.make_wrapper(ctx.build_context, condition)(state, catalog, groups, s)
                    if finalization:
                        hooked.append({"role": "user", "content": FINISH})
                    assert hooked == expected, f"{qid} hook {condition} mismatch"
                best_by_doc = {}
                for item in diag["ranking"]:
                    best_by_doc.setdefault(item["doc_id"], item["evidence_id"])
                diversity, dstats, ddiag = replay_variant(
                    ctx, state, catalog, groups, s, set(best_by_doc.values()), finalization
                )
                later = next(v for v in events[seq + 1 :] if v.get("event") == "api_attempt")
                assert later["request"]["messages"] == messages
                cf_payload = copy.deepcopy(later["request"])
                cf_payload["messages"] = counter
                g_payload = copy.deepcopy(later["request"])
                g_payload["messages"] = generic
                f_payload = copy.deepcopy(later["request"])
                f_payload["messages"] = focused
                rid = f"{qid}-request-{seq}"
                write(private / f"{rid}-baseline.json", later["request"])
                write(private / f"{rid}-target-retention-diagnostic.json", cf_payload)
                write(private / f"{rid}-latest-tool-retention-diagnostic.json", g_payload)
                write(private / f"{rid}-focused-tool-retention-diagnostic.json", f_payload)
                def targetseen(msgs):
                    return [p["evidence_id"] for p in visible(msgs) if norm(label) in norm(p["text"])]
                info = {
                    "request_sequence": seq,
                    "api_attempt_sequence": later["sequence"],
                    "context_sequence": next_context_seq,
                    "finalization": finalization,
                    "baseline_exact_replay": True,
                    "actual_api_messages_identical": True,
                    "target_ids_in_full_state": target_ids,
                    "target_ids_in_actual_request": targetseen(messages),
                    "baseline": {"stats": stats, **diag},
                    "target_retention_diagnostic": {
                        "reference_aware": True,
                        "changed_variable": "evidence ranking: target observed EIDs get stable first priority",
                        "stats": cfstats,
                        "visible_target_ids": targetseen(counter),
                        "selected_ids": [p["evidence_id"] for p in visible(counter)],
                        "ranking": cfdiag["ranking"],
                    },
                    "latest_tool_retention_diagnostic": {
                        "reference_aware": False,
                        "changed_variable": "evidence ranking: last successful tool EIDs get stable first priority",
                        "prioritized_ids": latest_tool_ids,
                        "stats": gstats,
                        "visible_target_ids": targetseen(generic),
                        "selected_ids": [p["evidence_id"] for p in visible(generic)],
                    },
                    "messages_chars": ctx.message_size(messages),
                    "payload_sha256": sha(json.dumps(later["request"], ensure_ascii=False, sort_keys=True).encode()),
                    "api_request_body_utf8_bytes": len(
                        json.dumps(later["request"], ensure_ascii=False, separators=(",", ":")).encode()
                    ),
                    "actual_tool_roles": sum(m["role"] == "tool" for m in messages),
                    "selected_evidence_ids": [p["evidence_id"] for p in visible(messages)],
                }
                assert (
                    ctx.message_size(counter) <= settings.context_chars
                    and ctx.message_size(generic) <= settings.context_chars
                )
                info["focused_tool_retention"] = {
                    "reference_aware": False,
                    "prioritized_ids": focused_ids,
                    "stats": fstats,
                    "visible_target_ids": targetseen(focused),
                    "selected_ids": [p["evidence_id"] for p in visible(focused)],
                }
                info["doc_diversity_retention"] = {
                    "reference_aware": False,
                    "policy": "best original-overlap evidence per doc first; old overlap order otherwise",
                    "stats": dstats,
                    "visible_target_ids": targetseen(diversity),
                    "selected_ids": [p["evidence_id"] for p in visible(diversity)],
                }
                request_rows.append(info)
                previous_request = info
                entry.update(
                    {
                        k: info[k]
                        for k in (
                            "context_sequence",
                            "api_attempt_sequence",
                            "selected_evidence_ids",
                            "target_ids_in_full_state",
                            "target_ids_in_actual_request",
                            "messages_chars",
                        )
                    }
                )
            elif kind == "api_attempt":
                response = e.get("response", {})
                choices = response.get("choices", [])
                entry.update(
                    {
                        "attempt": e.get("attempt"),
                        "http_status": e.get("http_status"),
                        "outcome": e.get("outcome"),
                        "request_model": e["request"].get("model"),
                        "response_model": response.get("model"),
                        "tool_choice": e["request"].get("tool_choice"),
                        "usage": response.get("usage"),
                        "finish_reason": choices[0].get("finish_reason") if choices else None,
                        "target_evidence_visible": previous_request["target_ids_in_actual_request"],
                    }
                )
            elif kind == "answer":
                entry.update({k: e[k] for k in ("answer", "supporting_evidence", "explanation")})
            elif kind == "run_end":
                entry.update({k: e[k] for k in ("status", "stop_reason", "eligible", "usage_complete")})
                entry["state"] = {k: v for k, v in e["state"].items() if k not in ("question", "evidence")}
            timeline.append(entry)
        # Locate the first transformation where each observed target disappears.
        losses = []
        for hit in hits:
            ns = next(e for e in events[hit["tool_sequence"] + 1 :] if e.get("event") == "state")
            nr = next(r for r in request_rows if r["request_sequence"] > hit["tool_sequence"])
            eid = hit["evidence_id"]
            ranking = next(v for v in nr["baseline"]["ranking"] if v["evidence_id"] == eid)
            stateev = next(v for v in ns["state"]["evidence"] if v["evidence_id"] == eid)
            assert stateev["text"] == hit["text"]
            losses.append(
                {
                    "raw_tool_field": f"trajectory[{hit['tool_sequence']}].content JSON data.{'matches' if hit['tool_name'] == 'find_in_document' else 'results'}[{hit['result_index_0based']}].text",
                    "full_state_field": f"trajectory[{ns['sequence']}].state.evidence[{next(i for i, v in enumerate(ns['state']['evidence']) if v['evidence_id'] == eid)}].text",
                    "actual_request_field": f"trajectory[{nr['api_attempt_sequence']}].request.messages[1].content JSON evidence (target absent)",
                    "tool_sequence": hit["tool_sequence"],
                    "state_sequence": ns["sequence"],
                    "context_sequence": nr["context_sequence"],
                    "request_sequence": nr["request_sequence"],
                    "api_attempt_sequence": nr["api_attempt_sequence"],
                    "evidence_id": eid,
                    "doc_id": hit["doc_id"],
                    "offset": hit["offset"],
                    "length": len(hit["text"]),
                    "literal_document_offset": hit["literal_document_offset"],
                    "state_preserves_exact_text": True,
                    "first_loss_layer": "full_state_to_model_context_snapshot_and_atomic_history_group_omission",
                    "selection": ranking,
                    "context_budget": nr["baseline"]["context_limit"],
                    "snapshot_allowance": nr["baseline"]["snapshot_allowance"],
                    "group_checks": nr["baseline"]["group_checks_newest_first"],
                    "actual_api_target_visible": eid in nr["target_ids_in_actual_request"],
                    "counterfactual_target_visible": eid in nr["target_retention_diagnostic"]["visible_target_ids"],
                }
            )
        final = next(e for e in events if e.get("event") == "answer")
        rawfinal = next(e for e in reversed(events) if e.get("role") == "assistant")["content"]
        stop = events[-1]
        result = {
            "id": qid,
            "question": row["question"],
            "reference_answer": label,
            "reference_normalized": norm(label),
            "exported_answer": row["answer"],
            "exported_normalized": norm(row["answer"]),
            "normalized_em": int(norm(row["answer"]) == norm(label)),
            "raw_final_content": rawfinal,
            "parsed_final": final,
            "export_matches_parsed": row["answer"] == final["answer"],
            "config_id": events[0]["config_id"],
            "source_row": row_meta[qid],
            "total_tokens": row["total_tokens"],
            "tool_calls": row["tool_calls"],
            "final_status": stop["status"],
            "requests": request_rows,
            "raw_target_hits": hits,
            "first_losses": losses,
            "timeline": timeline,
        }
        write(private / f"{qid}-analysis.json", result)
        summary.append(
            {
                "id": qid,
                "config_id": events[0]["config_id"],
                "event_count": len(events),
                "api_request_count": len(request_rows),
                "tool_calls": row["tool_calls"],
                "total_tokens": row["total_tokens"],
                "normalized_em": result["normalized_em"],
                "final_status": stop["status"],
                "export_matches_parsed": result["export_matches_parsed"],
                "original_record": row_meta[qid],
                "losses": losses,
                "context_replay_all_exact": True,
                "counterfactual_is_offline_only": True,
                "hook_both_conditions_exact": True,
                "new_api_calls": 0,
                "request_diagnostics": [
                    {
                        k: r[k]
                        for k in (
                            "request_sequence",
                            "api_attempt_sequence",
                            "context_sequence",
                            "finalization",
                            "target_ids_in_full_state",
                            "target_ids_in_actual_request",
                            "messages_chars",
                            "actual_tool_roles",
                            "selected_evidence_ids",
                        )
                    }
                    | {
                        "target_retention": {
                            k: r["target_retention_diagnostic"][k]
                            for k in ("reference_aware", "stats", "visible_target_ids", "selected_ids")
                        },
                        "latest_tool_retention": r["latest_tool_retention_diagnostic"],
                        "focused_tool_retention": r["focused_tool_retention"],
                        "doc_diversity_retention": r["doc_diversity_retention"],
                    }
                    for r in request_rows
                ],
            }
        )
        print(
            json.dumps(
                {
                    "id": qid,
                    "requests_replayed": len(request_rows),
                    "hits": len(hits),
                    "losses": [
                        {
                            "tool": v["tool_sequence"],
                            "EID": v["evidence_id"],
                            "rank": v["selection"]["rank"],
                            "allowance": v["snapshot_allowance"],
                            "remaining": v["selection"]["remaining_before"],
                            "size": v["selection"]["item_json_characters"],
                        }
                        for v in losses
                    ],
                },
                ensure_ascii=False,
            )
        )
    manifest = {
        "frozen_commit": COMMIT,
        "frozen_file_sha256": frozen_hash,
        "source_prediction_path": "outputs/acceptance-validation100-v1/validation_prediction.jsonl",
        "source_prediction_sha256": sha(source.read_bytes()),
        "question_input_sha256": sha((repo / "data/validation-questions.jsonl").read_bytes()),
        "labels_sha256": sha((repo / "data/validation.jsonl").read_bytes()),
        "ids": list(IDS),
        "new_api_calls": 0,
        "writes_old_repo": False,
        "reads_credentials": False,
        "uses_reference_for_target_diagnostic": True,
        "summary": summary,
    }
    write(out / "public/group-b-replay-summary.json", manifest)
    db.close()


if __name__ == "__main__":
    main()
