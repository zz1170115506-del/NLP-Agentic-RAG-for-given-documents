"""Export browsable QA traces. Use --root STAGE=DIR with the layouts in SOURCES.

The exporter copies selected structural fields only. Raw requests, query text, model
prose, reference labels, source text, network headers and service IDs stay local.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import time


SOURCES = {
    "acceptance": ("*/*.jsonl", "*/part-*/predictions.jsonl"),
    "interfaces": ("*.jsonl",),
    "bailian": ("**/prediction.jsonl", "**/*.attempts.jsonl", "**/*.api-attempt.json", "**/project-tool-probe.jsonl"),
    "qwen": ("qwen4b-*-live/prediction.jsonl",),
    "early": ("*.jsonl", "*/*.jsonl"),
    "rerank": ("api-*/*/*.json",),
    "prototype": ("*.jsonl", "evaluation-audit/*.jsonl"),
    "frozen": ("**/*.api-attempt.json",),
}
STAGES = {
    "acceptance": "全项目验收、功能对照与 100 题验证/测试",
    "interfaces": "CLI 和网页端验收",
    "bailian": "百炼基线、早期失败、证据修复与冻结请求对照",
    "qwen": "Qwen 256 / 2560 维真实问答",
    "early": "早期课程验证、模型对照与消融",
    "prototype": "原型与早期评测",
    "rerank": "早期重排真实问答",
    "frozen": "复盘阶段单次冻结请求",
}
NUMBER = (float, int)
ID = re.compile(r"[A-Za-z0-9_.:+-]{1,95}\Z")
SECRET = re.compile(r"(sk-|bearer|authorization|password|github_pat|gh[pousr]_|AKIA|/Users/)", re.I)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def identifier(value):
    if not isinstance(value, (str, int)):
        return None
    value = str(value)
    if ID.fullmatch(value) and not SECRET.search(value):
        return value
    return "hash-" + digest(value.encode())[:16]


def number(value):
    return value if type(value) in NUMBER and math.isfinite(value) else None


def clean(values):
    return {k: v for k, v in values.items() if v is not None}


def numbers(data, keys):
    return clean({key: number(data.get(key)) for key in keys})


def ids(items):
    return [identifier(v) for v in items if isinstance(v, (str, int))] if isinstance(items, list) else None


def as_dict(s):
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except (TypeError, ValueError):
            return {}
    return s if isinstance(s, dict) else {}


def usage(data):
    return numbers(as_dict(data), ["prompt_tokens", "completion_tokens", "total_tokens",
                                   "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"])


def span(item):
    item = as_dict(item)
    if not item.get("doc_id") and not item.get("chunk_id"):
        return None
    out = clean({key: identifier(item.get(key)) for key in ("doc_id", "chunk_id", "evidence_id", "method")})
    out.update(numbers(item, ["offset", "end", "length", "score"]))
    if isinstance(item.get("text"), str):
        out["text_chars"] = len(item["text"])
    out.update(numbers(as_dict(item.get("metadata")), ["bm25_rank", "qwen4b_rank"]))
    return out


def spans(value):
    return [v for item in value if (v := span(item))] if isinstance(value, list) else []


def public_event(e, sequence):
    kind = e.get("event") or e.get("role") or "untyped"
    out = {"position": sequence, "kind": identifier(kind), **numbers(e, ["sequence", "elapsed_seconds"])}
    if kind == "run_start":
        for k in ["provider", "model", "mode", "config_id", "engine"]:
            if k in e:
                out[k] = identifier(e[k])
        if "injected_provider" in e:
            out["injected_provider"] = bool(e["injected_provider"])
    elif kind == "api_attempt":
        request, response = as_dict(e.get("request")), as_dict(e.get("response"))
        out.update(numbers(e, ["attempt", "http_status"]))
        out.update(clean({"outcome": identifier(e.get("outcome")), "request_model": identifier(request.get("model")),
                          "response_model": identifier(response.get("model")), "response_usage": usage(response.get("usage")),
                          "request_message_count": len(request.get("messages", [])), "max_tokens": number(request.get("max_tokens"))}))
        err = as_dict(e.get("error")) or as_dict(response.get("error"))
        if e.get("error_type") or err.get("code") or err.get("type"):
            out["error_category"] = identifier(e.get("error_type") or err.get("code") or err.get("type"))
    elif kind == "assistant":
        out.update(clean({"finish_reason": identifier(e.get("finish_reason")), "usage": usage(e.get("usage"))}))
        calls = []
        for call in e.get("tool_calls") or []:
            fn = as_dict(call.get("function", call))
            args = as_dict(fn.get("arguments"))
            item = clean({"tool": identifier(fn.get("name")), "doc_id": identifier(args.get("doc_id")),
                          "method": identifier(args.get("method")), **numbers(args, ["top_k", "offset", "limit"])})
            if isinstance(args.get("query"), str):
                item["query_sha256"] = digest(args["query"].encode())
            calls.append(item)
        if calls:
            out["calls"] = calls
    elif kind == "tool":
        content = as_dict(e.get("content"))
        data = as_dict(content.get("data", content))
        out.update(clean({"tool": identifier(e.get("name")), "ok": content.get("ok") if type(content.get("ok")) is bool else None}))
        err = as_dict(content.get("error"))
        if err.get("code") or err.get("type"):
            out["error_category"] = identifier(err.get("code") or err.get("type"))
        out["spans"] = spans(data.get("results") or data.get("matches") or data.get("passages") or [])
        if value := span(data):
            out["spans"].append(value)
        if q := data.get("query"):
            if isinstance(q, str):
                out["query_sha256"] = digest(q.encode())
    elif kind == "context":
        out.update(numbers(e, ["characters", "unused_characters", "dropped_groups"]))
        for k in ("selected_snapshot_ids", "visible_evidence_ids", "focused_evidence_ids", "budget_omitted_ids"):
            if k in e:
                out[k] = ids(e[k])
    elif kind in ("answer", "evidence_resolution"):
        out["cited_evidence_ids"] = ids(e.get("supporting_evidence", e.get("citations")))
        out["spans"] = spans(e.get("evidence"))
    elif kind in ("run_end", "finalization"):
        out.update(clean({k: identifier(e.get(k)) for k in ("status", "stop_reason", "reason")}))
        out.update({k: e[k] for k in ("eligible", "usage_complete") if type(e.get(k)) is bool})
    return clean(out)


def materialize(path):
    for attempt in range(4):
        raw = path.read_bytes()
        if len(raw) == path.stat().st_size:
            return raw
        time.sleep(0.5 * (attempt + 1))
    raise OSError("Source file was not fully materialized: " + path.name)


def load_file(path):
    payload = materialize(path)
    if path.suffix == ".jsonl":
        data = [json.loads(line) for line in payload.splitlines() if line.strip()]
    else:
        data = [json.loads(payload)]
    return digest(payload), data


def extract(row, source):
    if isinstance(row.get("result"), dict):
        row = row["result"]
    pred = row.get("prediction", row)
    if "trajectory" in pred and isinstance(pred["trajectory"], list):
        return pred, pred["trajectory"], pred["id"], "prediction"
    if pred.get("event") == "api_attempt":
        case = re.search(r"(?:^|/)([0-9]+)(?:/|-(?:control|treatment))", source)
        return pred, [pred], case.group(1) if case else "unnumbered", "frozen_request"
    return None


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def export_qwen_rankings(root, directory):
    folder = directory / "rankings"
    folder.mkdir(exist_ok=True)
    index = ["# Qwen 实际候选排名", "", "每行对应一次检索中的一个候选。returned 表示工具实际返回；同一次调用按题号、检索序号和查询 SHA-256 关联。", ""]
    entries = []
    for source in sorted(root.glob("qwen4b-*-live/retrieval.jsonl")):
        file_sha, requests = load_file(source)
        width, = {r["diagnostics"]["qwen4b"]["dimension"] for r in requests}
        score_fields = ["bm25_rank", "full_rank", "prefix_rank", "int8_rank", "full_score", "prefix_score", "int8_score"]
        columns = ["question_id", "search_index", "query_sha256", "top_k", "doc_id", "chunk_id", "returned", *score_fields]
        count = 0
        path = folder / f"int8-{width}.csv"
        with path.open("w", newline="") as dest:
            writer = csv.DictWriter(dest, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for r in requests:
                if not re.fullmatch("[0-9a-f]{64}", r["query_sha256"]):
                    raise ValueError("Bad query digest")
                for h in r["diagnostics"]["qwen4b"]["rankings"]:
                    writer.writerow({"question_id":identifier(r["id"]), "search_index":number(r["search_index"]),
                                     "query_sha256":r["query_sha256"], "top_k":number(r["top_k"]),
                                     "doc_id":identifier(h["doc_id"]), "chunk_id":identifier(h["chunk_id"]),
                                     "returned":h["chunk_id"] in r["returned_chunk_ids"], **numbers(h,score_fields)})
                    count += 1
        entries.append({"source":f"qwen/{source.parent.name}/{source.name}", "source_sha256":file_sha,
                        "dimension":width,"search_calls":len(requests),"candidate_rows":count})
        index.append(f"- [{width} 维，每次检索的完整候选排名]({path.name}) · {len(requests)} 次调用，{count} 条候选记录")
    (folder / "README.md").write_text("\n".join(index) + "\n")
    return entries


def export_retrieval_replays(roots, output):
    extra = []
    folder = output/"rankings"
    folder.mkdir(exist_ok=True)
    index = folder/"README.md"
    for stage, root in roots:
        if stage not in ("rerank", "frozen"):
            continue
        sources = sorted(root.glob("*/queries/*.json" if stage == "rerank" else "**/replay-private.jsonl"))
        if not sources:
            continue
        filename = f"{stage}-offline-searches.jsonl"
        n = 0
        with (folder/filename).open("w") as dest:
            for p in sources:
                file_sha, records = load_file(p)
                extra.append({"source":f"{stage}/{p.relative_to(root).as_posix()}", "source_sha256":file_sha})
                for r in records:
                    if stage == "rerank":
                        groups = []
                        for g, v in r["groups"].items():
                            hits = v.get("ordered")
                            if hits is None:
                                hits = [{"doc_id":doc,"chunk_id":chunk,"rank":rank}
                                        for rank,(doc,chunk) in enumerate(v.get("final_ids", []),1)]
                            groups.append((g, hits, v.get("timing", v)))
                    else:
                        groups = [(r.get("kind"), r["results"], {"total_seconds":r.get("seconds")})]
                    for g, hits, timing in groups:
                        norm = []
                        for h in hits:
                            v = span(h) or {}
                            v.update(numbers(h, ["start","end","rank","score"]))
                            norm.append(v)
                        query_hash = r.get("question_sha256")
                        if isinstance(r.get("query"), str):
                            query_hash = digest(r["query"].encode())
                        if query_hash is not None and not re.fullmatch("[0-9a-f]{64}",query_hash):
                            raise ValueError("Invalid offline query digest")
                        out = {"source_sha256":file_sha,"question_id":identifier(r.get("id")),"query_sha256":query_hash,
                               "experiment":identifier(p.parent.parent.name) if stage=="rerank" else "frozen-bm25",
                               "group":identifier(g),"timing":numbers(timing,["retrieval_seconds","rerank_seconds","total_seconds",
                                                                           "median_total_seconds","median_retrieval_seconds","median_rerank_seconds"]),
                               "ranked_hits":norm}
                        dest.write(json.dumps(out,ensure_ascii=False,separators=(",",":"))+"\n")
                        n += 1
        with index.open("a") as dest:
            dest.write(f"\n- [历史离线检索 {stage} 的排序与耗时]({filename}) · {len(sources)} 个来源，{n} 个查询或排序组。\n")
    return extra


def build(roots, output):
    output.mkdir(parents=True, exist_ok=True)
    records_dir = output / "records"
    records_dir.mkdir(exist_ok=True)
    sources, unique, stages = [], {}, defaultdict(list)
    for stage, root in roots:
        candidates = sorted({p for pat in SOURCES[stage] for p in root.glob(pat)})
        for path in candidates:
            rel = path.relative_to(root).as_posix()
            if path.name.endswith(".events.jsonl") or path.name in {"events.jsonl","questions.jsonl","references.jsonl"} or "reference" in path.name or "question" in path.name:
                continue
            if path.stem in {"corpus","retrieval","embedding-pilot","embedding-pilot-online","index-build"}:
                continue
            file_sha, rows = load_file(path)
            source = f"{stage}/{rel}"
            refs = []
            for i, row in enumerate(rows, 1):
                parsed = extract(row, source)
                if not parsed:
                    continue
                pred, trajectory, qid, category = parsed
                key = digest(canonical(pred))
                refs.append(key)
                if key in unique:
                    continue
                events = [public_event(e,j) for j,e in enumerate(trajectory)]
                start = next((e for e in events if e["kind"] == "run_start"), {})
                end = next((e for e in reversed(events) if e["kind"] == "run_end"), {})
                http = [e for e in events if e["kind"] == "api_attempt"]
                tools = [e for e in events if e["kind"] == "tool"]
                stats = clean({"id": identifier(qid), "category": category, "mode": start.get("mode"),
                               "model": start.get("model"), "config_id": start.get("config_id"),
                               "answered": bool(pred.get("answer")) if category == "prediction" else None,
                               "status": end.get("status"), "events": len(events), "api_attempts": len(http),
                               "http_statuses": dict(Counter(str(e.get("http_status","unknown")) for e in http)),
                               "tool_events": len(tools), **numbers(pred, ["tool_calls","total_tokens"])})
                unique[key] = stats
                file = records_dir / key[:2] / (key[:20]+".jsonl")
                file.parent.mkdir(exist_ok=True)
                with file.open("w") as dest:
                    for obj in [dict(record_sha256=key, **stats), *events]:
                        dest.write(json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n")
            if refs:
                stages[stage].append((source,refs))
                sources.append({"source":source, "source_sha256":file_sha, "record_sha256":refs})
    lines = ["# 问答日志", "", "下表按项目阶段导航。点进题号可查看该次运行的完整事件顺序、请求状态、用量、工具动作与返回片段坐标；模型可见及因预算省略的证据编号按原运行版本记录。", "",
             "同一条轨迹的多个源文件通过标准化 JSON 的 SHA-256 关联到同一个日志。总数按不同轨迹计算，包含失败历史、合成问题和离线演示。出现的 HTTP 状态反映日志记录，运行模式与提供方见每条轨迹的开始事件；冻结请求只反映单次调用。缺失字段表示源日志没有记录该值。", "",
             "| 阶段 | 来源文件 | 不同记录 |", "|---|---:|---:|"]
    for stage, groups in stages.items():
        keys = set(k for _,group in groups for k in group)
        lines.append(f"| [{STAGES[stage]}]({stage}.md) | {len(groups)} | {len(keys)} |")
        section = [f"# {STAGES[stage]}", "", "[返回日志目录](README.md)", ""]
        for source,keys in groups:
            section.extend([f"## {source}", "", "| 题号与事件明细 | 状态 | API 尝试 | 工具回包 | token |","|---|---|---:|---:|---:|"])
            for key in keys:
                st = unique[key]
                section.append(f"| [{st['id']}](records/{key[:2]}/{key[:20]}.jsonl) | {st.get('status',st['category'])} | {st['api_attempts']} | {st['tool_events']} | {st.get('total_tokens','—')} |")
            section.append("")
        (output/f"{stage}.md").write_text("\n".join(section).rstrip()+"\n")
    counts = {"sources": len(sources), "source_file_digests":len({s['source_sha256'] for s in sources}),
              "unique_records":len(unique),"source_record_occurrences":sum(len(s['record_sha256']) for s in sources),
              "unique_predictions":sum(s["category"]=="prediction" for s in unique.values()),
              "unique_frozen_requests":sum(s["category"]=="frozen_request" for s in unique.values()),
              "events":sum(s["events"] for s in unique.values()),"api_attempts":sum(s['api_attempts'] for s in unique.values()),
              "tool_events":sum(s['tool_events'] for s in unique.values())}
    lines.extend(["", f"合计 {counts['sources']} 份源文件、{counts['unique_records']} 条去重记录、{counts['events']} 个事件。其中记录的 API 尝试为 {counts['api_attempts']} 次，工具回包为 {counts['tool_events']} 次。不同完整运行可能共享相同请求或分支记录，不能用全表次数结算云服务账单。","","[来源、原始文件哈希与逐记录映射](manifest.json)"])
    (output/"README.md").write_text("\n".join(lines)+"\n")
    ranking_sources = []
    for stage, root in roots:
        if stage == "qwen":
            ranking_sources.extend(export_qwen_rankings(root, output))
    offline_sources = export_retrieval_replays(roots, output)
    if ranking_sources or offline_sources:
        with (output/"README.md").open("a") as dest:
            dest.write("\n[两个维度的实际候选排名、早期离线重排及冻结 BM25 检索](rankings/README.md)\n")
    dump(output/"manifest.json", {"counts":counts,"sources":sources,"rankings":ranking_sources,"offline_sources":offline_sources})
    print(json.dumps(counts))


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",action="append",required=True,metavar="STAGE=DIR",help="Supported stages: "+", ".join(SOURCES))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    roots=[]
    for spec in args.root:
        stage,_,root=spec.partition("=")
        path=Path(root)
        if stage not in SOURCES or not path.is_dir():
            parser.error("Invalid stage or missing input directory")
        roots.append((stage,path))
    build(roots,args.output)
