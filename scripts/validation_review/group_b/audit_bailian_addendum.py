#!/usr/bin/env python3
"""Read-only addendum: classify the new-provider run without calling any API."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("work/validation-failure-review"))
    parser.add_argument("--out", type=Path, default=Path("work/validation-review-drafts/group-b"))
    a = parser.parse_args()
    out = a.out
    spec = importlib.util.spec_from_file_location("offline_replay", out / "replay_group_b.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    source = a.repo / "outputs/validation-review/bailian-baseline/prediction.jsonl"
    evaluations = a.repo / "outputs/validation-review/bailian-baseline/evaluation/per-question-private.json"
    metrics = {v["id"]: v for v in json.loads(evaluations.read_text())}
    report = []
    narratives = {
        "231": "新百炼运行3次HTTP200，使用4次工具、9687 token，以search_stalled进入最后轮次后由模型直接空答，解析/导出一致。与旧轨迹的区别是：本次原工具返回中没有参考串，也没有旧doc43835:0片段；不能套用旧E9在state到context丢失的诊断。已有定向hook严格要求片段先被观察到，因此对此运行是空操作；检索路线需要另行单变量复测，不应偷加旧轨迹的证据。",
        "390": "新百炼运行6次HTTP200，10次工具、23082 token，最终以reserve_final_usage进入收尾并由模型空答，解析/导出一致。新seq16取回doc3282:750，编号E15，seq20/27实际API中尚不可见；到seq36及最终seq44已经可见。故最终空答不能简单归因于歌名被隐藏。新seq23还取得doc20259:750，E18，其葡萄牙文段说明同名CD和对早年热门曲的重录，并不证明所问合辑的第3轨。模型最后明确指出缺合辑和第3轨对应关系，与语义证据缺口一致。继续强保留讣闻只改变排序，未为最终请求增添该线索；不能把这一次算作纯可见性修复样本。",
        "58": "新百炼只有前2次API成功；第三次seq20收到HTTP400，响应error.code/type均为Arrearage，程序seq21记录provider_error并终止。2次成功请求已报告6545 token、4次工具，失败请求用量未知，usage_complete=false。没有模型final答复，也没有answer事件；导出空串来自运行错误路径，而不是模型主动弃答。因此不能将新模型58的EM=0当作拒答能力证据，不能与旧模型最终明确空答混为一谈。恢复账户后必须完成或重新运行该题，再判断上下文与答案；本子任务没有调用API或修改账户。",
    }
    if metrics.get("58", {}).get("status") == "insufficient_evidence":
        narratives["58"] = (
            "充值后重新运行的58已完整结束：5次HTTP200、8次工具均为search、19081 token，usage_complete=true。seq34因search_stalled=2提前收尾（剩14475 token），seq37发送最终请求，seq38模型明确返回空答，解析/导出一致，EM=0。与旧提供商历史的关键区别是：新工具结果从未出现所问奖项，也没有旧E30/E37的致谢窗口；只取到同doc28406的参考文献尾段（offset45750与50250），未检到4作者/3部门定位片段，也没有执行open/find。因此新58的首次缺口是检索与论文定位，不能套用旧上下文丢失诊断，focused-tool-first在此新轨迹没有可优先的定位窗口。旧账户中断的58另存attempt-0，仍标provider_error/Arrearage；本条有效弃答不覆盖或改写旧失败史。历史final-pair仅在旧观察集合上检验保留策略，不能视作修复新百炼完整运行。"
        )
    for raw in source.read_bytes().splitlines(keepends=True):
        row = json.loads(raw)
        qid = row["id"]
        if qid not in m.IDS:
            continue
        label = metrics[qid]["reference"]
        events = row["trajectory"]
        calls = {}
        timeline = []
        hits = []
        apis = []
        last_context = None
        m.write(out / "private" / f"{qid}-bailian-original-record.json", row)
        m.write(out / "private" / f"{qid}-bailian-evaluation.json", metrics[qid])
        for e in events:
            seq = e["sequence"]
            kind = e.get("event", e.get("role"))
            line = {"sequence": seq, "type": kind, "elapsed_seconds": e.get("elapsed_seconds")}
            public = ""
            if kind == "assistant":
                line["content"] = e.get("content")
                line["tool_calls"] = e.get("tool_calls", [])
                for c in e.get("tool_calls", []):
                    calls[c["id"]] = c
                public = (
                    "模型决定调用" + str(len(e.get("tool_calls", []))) + "个工具"
                    if e.get("tool_calls")
                    else "模型原始final为空答"
                )
            elif kind == "tool":
                obj = json.loads(e["content"])
                target = []
                allp = []
                for p in m.passages(obj):
                    info = {k: p.get(k) for k in ("evidence_id", "doc_id", "offset")}
                    info["length"] = len(p["text"])
                    info["target_literal"] = m.norm(label) in m.norm(p["text"])
                    allp.append(info)
                    if info["target_literal"]:
                        hits.append({"sequence": seq, **info})
                        target.append(p["evidence_id"])
                line.update(
                    name=e["name"],
                    arguments=calls[e["tool_call_id"]]["function"]["arguments"],
                    passages=allp,
                    ok=obj.get("ok"),
                )
                public = f"{e['name']}，ok={obj.get('ok')}，片段={len(allp)}，目标IDs={target}"
            elif kind == "api_attempt":
                visible = [
                    {k: p.get(k) for k in ("evidence_id", "doc_id", "offset")}
                    for p in m.visible(e["request"]["messages"])
                    if m.norm(label) in m.norm(p["text"])
                ]
                response = e.get("response") or {}
                line.update(
                    http_status=e.get("http_status"),
                    actual_request_target_passages=visible,
                    usage=response.get("usage"),
                    error_code=response.get("error", {}).get("code"),
                    response_model=response.get("model"),
                    context_sequence=last_context,
                )
                apis.append(line.copy())
                public = f"HTTP{line['http_status']}，context seq{last_context}，实际可见目标={visible}，error={line['error_code']}，response_model={line['response_model']}，usage={line['usage']}"
            elif kind == "context":
                last_context = seq
                line.update({k: e[k] for k in ["selected_evidence", "dropped_groups", "characters"]})
                public = f"保留{e['selected_evidence']}片段；丢{e['dropped_groups']}工具组；{e['characters']}字符"
            elif kind == "state":
                state = e["state"]
                line.update(
                    evidence_count=len(state["evidence"]),
                    target_ids=[p["evidence_id"] for p in state["evidence"] if m.norm(label) in m.norm(p["text"])],
                    steps=state["steps"],
                    tools=state["tool_calls"],
                    tokens=state["total_tokens"],
                    stalled=state["stalled_searches"],
                )
                public = json.dumps(
                    {k: v for k, v in line.items() if k not in ["sequence", "elapsed_seconds", "type"]},
                    ensure_ascii=False,
                )
            elif kind == "request":
                public = f"构造请求，{m.visible(e['messages']) and len(m.visible(e['messages'])) or 0}可见片段；以随后的api_attempt为实际发送证据"
            elif kind == "answer":
                line.update({k: e[k] for k in ["answer", "supporting_evidence", "explanation"]})
                public = "解析后的空答，与原始模型final相同"
            elif kind == "finalization":
                line.update(reason=e["reason"], remaining_reported_tokens=e["remaining_reported_tokens"])
                public = f"{e['reason']}；余{e['remaining_reported_tokens']} token"
            elif kind == "error":
                line.update(code=e["code"], message=e["message"])
                public = "程序记录" + e["code"]
            elif kind == "run_end":
                line.update(status=e["status"], usage_complete=e["usage_complete"])
                public = f"{e['status']}；usage_complete={e['usage_complete']}"
            else:
                public = kind
            line["public_description"] = public
            timeline.append(line)
        result = {
            "id": qid,
            "row_sha256": hashlib.sha256(raw).hexdigest(),
            "row_bytes": len(raw),
            "config_id": events[0]["config_id"],
            "event_count": len(events),
            "api_calls": apis,
            "raw_target_hits": hits,
            "status": metrics[qid]["status"],
            "tokens": row["total_tokens"],
            "tool_calls": row["tool_calls"],
            "normalized_em": metrics[qid]["em"],
            "model_abstention": metrics[qid]["status"] == "insufficient_evidence",
            "has_answer_event": any(e.get("event") == "answer" for e in events),
            "narrative": narratives[qid],
        }
        m.write(out / "private" / f"{qid}-bailian-analysis.json", {**result, "timeline": timeline})
        for isprivate in [True, False]:
            lines = [
                f"# ID {qid}：百炼独立基线追加复盘",
                "",
                "这不是旧提供商轨迹的续写或同一实验条件。",
                "",
                narratives[qid],
                "",
                "| seq | 秒 | 事件 | 实际记录 |",
                "|---:|---:|---|---|",
            ]
            for e in timeline:
                content = e["public_description"]
                if isprivate and e["type"] == "assistant":
                    content = (e.get("content") or "") + "；" + json.dumps(e.get("tool_calls", []), ensure_ascii=False)
                if isprivate and e["type"] == "tool":
                    content += "；" + e["arguments"]
                content = content.replace("|", "\\|").replace("\n", "<br>")
                lines.append(f"| {e['sequence']} | {e['elapsed_seconds']:.6f} | {e['type']} | {content} |")
            p = out / ("private" if isprivate else "public") / f"{qid}-bailian-timeline.md"
            p.write_text("\n".join(lines) + "\n")
            p.chmod(0o600 if isprivate else 0o644)
        report.append(result)
    manifest = {
        "source_commit_reported_by_root": "8c8e545126e329919d2c16b18cacea6e139ebb29",
        "config_id": "900fc3b95b775d2a",
        "requested_and_success_response_model": "deepseek-v4-flash-0731",
        "source_path": "outputs/validation-review/bailian-baseline/prediction.jsonl",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "evaluation_sha256": hashlib.sha256(evaluations.read_bytes()).hexdigest(),
        "new_api_calls_by_this_audit": 0,
        "coverage_events": sum(x["event_count"] for x in report),
        "coverage_api_attempts": sum(len(x["api_calls"]) for x in report),
        "questions": report,
    }
    m.write(out / "public/bailian-addendum.json", manifest)
    counts = {
        "events": sum(x["event_count"] for x in report),
        "api_attempts": sum(len(x["api_calls"]) for x in report),
        "http_200": sum(a.get("http_status") == 200 for x in report for a in x["api_calls"]),
        "http_errors": sum(a.get("http_status") != 200 for x in report for a in x["api_calls"]),
        "assistant": sum(
            sum(
                e["type"] == "assistant"
                for e in json.loads((out / "private" / f"{x['id']}-bailian-analysis.json").read_text())["timeline"]
            )
            for x in report
        ),
        "tool": sum(x["tool_calls"] for x in report),
    }
    manifest["coverage"] = counts
    manifest["prior_58_provider_error_archive"] = "attempt-0/58-attempt-summary.json"
    m.write(out / "public/bailian-addendum.json", manifest)
    (out / "public/BAILIAN_ADDENDUM.md").write_text(
        "# 百炼基线追加：三题的故障层已发生变化\n\n"
        + "\n\n".join(f"ID {q['id']}：{q['narrative']}" for q in report)
        + f"\n\n当前有效基线完整覆盖{counts['events']}个记录事件、{counts['api_attempts']}次真实API尝试（{counts['http_200']}次HTTP200、{counts['http_errors']}次HTTP错误）、{counts['assistant']}次模型assistant响应及{counts['tool']}次工具返回。公开与私密timeline均保留每个事件；231/390原始JSONL行SHA与充值前完全相同，仅58重新完成。旧58的23事件、2次HTTP200加1次Arrearage保留在attempt-0，不计入当前有效基线总数。本地审计没有产生新调用。\n"
    )
    print(
        json.dumps(
            {
                "events": manifest["coverage_events"],
                "api_attempts": manifest["coverage_api_attempts"],
                "statuses": {q["id"]: q["status"] for q in report},
            }
        )
    )


if __name__ == "__main__":
    main()
