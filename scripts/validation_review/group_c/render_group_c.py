"""Render private detailed reviews and public locator-only reviews from audited artifacts."""
import argparse
import hashlib
import json
from pathlib import Path


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def describe(row, private):
    kind = row["kind"]
    if kind == "api_attempt":
        ids = ",".join(e["evidence_id"] for e in row["visible_evidence"])
        return f"真实API#{row['api_number']}；HTTP {row['http_status']}；usage={row['usage']['total_tokens']}；tool_choice={row['tool_choice']}；实际messages={row['actual_message_chars']}字符；证据[{ids}]；参考字面串在messages/证据={row['reference_literal_in_actual_messages']}/{row['reference_literal_in_visible_evidence']}。输入仅按api_attempt.request.messages审计。"
    if kind == "assistant":
        if row["tool_calls"]:
            names = ", ".join(c["id"] + ":" + c["function"]["name"] for c in row["tool_calls"])
            return (str(row.get("content") or "") + "；" if private else "模型决定发起工具；") + names
        final = json.loads(row["content"])
        status = "已经为空" if final["answer"] == "" else "为非空候选"
        return f"模型最终决定：原始content中的answer{status}。" + (str(row.get("content") or "") if private else "")
    if kind == "tool":
        args = row["arguments"]
        query = args.get("query", "")
        query_text = json.dumps(args, ensure_ascii=False) if private else f"query SHA256={hashlib.sha256(query.encode()).hexdigest()[:16]}，top_k={args.get('top_k')}"
        hits = "; ".join(f"#{h['rank']} {h['doc_id']}:{h['offset']}+{len(h['text'])}({h.get('evidence_id')})" for h in row["ranked_hits"])
        return f"{row['name']} {row['call_id']}；{query_text}；ok={row['ok']}，返回{row['results']}，新证据{row['new_evidence']}，完全重复查询={row['repeated_query']}；{hits}"
    if kind == "state":
        s = row["state"]
        return f"步骤{s['steps']}，工具{s['tool_calls']}，累计token{s['total_tokens']}，stalled_searches={s['stalled_searches']}；完整state证据数{len(row['all_state_evidence_ids'])}，candidate_answer仍空。"
    if kind == "context":
        return f"上下文选择；移除历史组{row['dropped_groups']}，选证据{row['selected_evidence']}，{row['characters']}字符。该事件是程序摘要，实际输入以随后api_attempt为准。"
    if kind == "request":
        return "程序准备请求事件；不把此副本当成实际模型输入证据。"
    if kind == "finalization":
        return f"进入收尾：{row['reason']}；剩余已报告token预算={row['remaining_reported_tokens']}；下一请求工具禁用。"
    if kind == "answer":
        if row.get("answer", "") == "":
            return f"JSON解析接受原始空answer；supporting_evidence={row.get('supporting_evidence', [])}；空答提前返回，未执行非空答案引用解析。"
        return f"JSON解析接受原始非空answer；supporting_evidence={row.get('supporting_evidence', [])}；引用片段坐标验证通过。坐标有效不代表全部条件语义成立。"
    if kind == "run_end":
        status = "为空" if not row.get("state", {}).get("candidate_answer") else "保留非空候选"
        return f"运行结束status={row['status']}；usage_complete={row['usage_complete']}；导出answer{status}。"
    if kind in ("skill_selected", "skill_loaded"):
        return f"{kind}：{row['name']}，来源{row.get('source')}。"
    if kind == "run_start":
        return f"启动baseline；config_id={row['config_id']}；sparse，固定语料。"
    if kind == "user":
        return "Question(id, question)进入Agent；原题仅保留在私有附件。"
    return kind


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    private, public = args.root / "private", args.root / "public"
    public.mkdir(exist_ok=True)
    notes = json.loads((private / "semantic-notes.json").read_text())
    identity = json.loads((private / "identity.json").read_text())
    baseline = json.loads((private / "bailian-provider-status.json").read_text())["rows"]
    resumed_path = private / "bailian-baseline/summary.json"
    resumed = json.loads(resumed_path.read_text()) if resumed_path.exists() else {}
    summaries, public_rows = [], {}
    overview = ["# 第三类三题复盘", "", "历史记录固定为 `dab7646`、配置 `61d7cc3701b2a42a`，预测SHA-256为 `" + identity["prediction_sha256"] + "`。只用官方验证集；未读取测试标签、密钥或环境文件，未调用模型。离线BM25按固定词法/评分/同分排序只读查询，E5与Qwen均未参与。", "", "三题的历史最后一次模型原始回复均直接给出空答案，解析和导出没有把非空答案清空。‘请求曾有参考文字’仅是全程字面指标，不等于最终仍保留关键证据或所有条件均已证明。", "", "百炼初次组三题首请求均HTTP 400 Arrearage；该失败尝试没有模型答题过程，EM未测。充值后另行完成有效运行，新基线及逐事件对照见各题下文与百炼追加汇总，初次失败记录不覆盖。", "", "|题号|历史API/工具/token|完全相同查询重复数|首次有证据的问题|历史EM|百炼初次尝试|", "|---|---|---|---|---|---|"]
    for id, note in notes.items():
        audit = json.loads((private / f"{id}-audit.json").read_text())
        record = json.loads((private / f"{id}-record.json").read_text())
        summary = {k: audit[k] for k in ("id", "tool_calls", "total_tokens", "api_requests", "exact_query_repeats", "finalization_remaining", "empty_origin", "final_status")}
        summary.update(historical_em=0, historical_config_id="61d7cc3701b2a42a", bailian_initial_attempt=baseline[id],
                       bailian_completed_baseline=resumed.get(id),
                       first_evidenced_problem=note["first_problem"], conclusion=note["public_conclusion"], next_single_variable=note["proposal"])
        summaries.append(summary)
        current_em = str(resumed[id]["em"]) if id in resumed else "未测（服务错误）"
        overview.append(f"|{id}|{audit['api_requests']}/{audit['tool_calls']}/{audit['total_tokens']}|{audit['exact_query_repeats']}|{cell(note['first_problem'])}|0|{current_em}|")
        for is_private, dest in ((True, private), (False, public)):
            lines = [f"# 验证题 {id} 逐题复盘", "", note["meaning"], "", "历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。", ""]
            if is_private:
                lines += ["## 原题与评分", "", audit["question"], "", f"参考答案原值：`{json.dumps(audit['reference_answer'], ensure_ascii=False)}`；导出：`{json.dumps(audit['prediction_answer'])}`。", f"规范化参考=`{audit['normalized_reference']}`，规范化导出=`{audit['normalized_prediction']}`，历史严格EM=0（空答）。", "", "## 实际发生了什么", "", note["narrative"], ""]
            else:
                lines += ["## 可证实的结论", "", note["public_conclusion"], ""]
            lines += ["首次问题：" + note["first_problem"], "", f"工具{audit['tool_calls']}次（全部search，open/find均0），真实API{audit['api_requests']}次，总usage={audit['total_tokens']}。收尾前余额：{audit['finalization_remaining']}。", "", "## 按序时间线", "", "|seq/index|事件|观察及定位|", "|---|---|---|"]
            rows = []
            for row in audit["timeline"]:
                description = describe(row, is_private)
                lines.append(f"|{row['sequence']}|{row['kind']}|{cell(description)}|")
                if not is_private:
                    rows.append({"sequence": row["sequence"], "kind": row["kind"], "description": description})
            if not is_private:
                public_rows[id] = rows
            if is_private:
                lines += ["", "## 条件核查", "", "|条件|判定|证据定位|反证/缺口|", "|---|---|---|---|"]
                excerpts = []
                for index, c in enumerate(note["conditions"], 1):
                    refs = []
                    for tag in ("support", "counter"):
                        for ev in c.get(tag, []):
                            locator = f"doc{ev['doc_id']}[{ev['start']}:{ev['end']}]"
                            refs.append(("反证：" if tag == "counter" else "") + locator)
                            excerpts += [f"### 条件{index} {'反证' if tag=='counter' else '支持'} {locator}", "", f"来源：{ev['url']}", f"历史工具覆盖：{ev['historical_tools']}；实际请求覆盖：{ev['actual_requests']}。", "", "```text", ev["text"], "```", ""]
                    lines.append(f"|{cell(c['condition'])}|{c['status']}|{cell('; '.join(refs))}|{cell(c['gap'])}|")
                lines += ["", "## 精确原文片段", ""] + excerpts
                lines += ["## 最后原始模型输出与处理", "", "```json", audit["final_original_model_content"], "```", "", "原始API响应 → JSON解析成功 → `_validate_final`遇空answer立即返回insufficient_evidence（在引用ID解析前）→ answer事件保留空值 → run_end → Prediction导出空值。没有invalid_final、引用拒绝或HTTP错误导致的清空。空答情况下的引用审计通过不代表条件语义充分。固定实现见`dab7646:src/rag_agent/agent/loop.py`的`_validate_final`及最终赋值段。", ""]
                lines += ["## 离线定向查询", "", "全部查询基于题目、历史候选或补查原文生成；无标签辅助定位查询；标签只用于历史评分与字面层审计。结果为事后诊断，不混入历史过程。", "", "|查询|形成依据|前3定位|", "|---|---|---|"]
                queries = json.loads((private / f"{id}-offline-queries.json").read_text())
                for q in queries:
                    lines.append(f"|{cell(q['query'])}|{cell(q['query_origin'])}|{cell('; '.join(str((h['rank'],h['doc_id'],h['offset'])) for h in q['hits'][:3]))}|")
                lines += ["", f"完整top20、原文和耗时见`{id}-offline-queries.json`；不是全语料不存在其他证据的证明。", ""]
            else:
                locators = sorted({f"{e['doc_id']}:{e['start']}:{e['end']}" for c in note["conditions"] for tag in ("support", "counter") for e in c.get(tag, [])})
                lines += ["", "条件核查原文只保存在加密私有附件。公开定位：" + "; ".join(locators) + "。", ""]
            lines += ["## 下一步单变量与未确认项", "", note["proposal"], "", "百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。", ""]
            (dest / f"{id}-review.md").write_text("\n".join(lines))
        api_dir = private / "api"
        api_dir.mkdir(exist_ok=True)
        for event in record["trajectory"]:
            if event.get("event") == "api_attempt":
                for key in ("request", "response"):
                    (api_dir / f"{id}-seq{event['sequence']}-{key}.json").write_text(json.dumps(event[key], ensure_ascii=False, indent=2)+"\n")
    overview += ["", "每题完整逐事件公开定位表：" + "、".join(f"[{q}]({q}-review.md)" for q in notes) + "。原题、参考答案、真实请求、模型原回复和精确原文在私有附件；本目录不包含这些内容。", "", "14条离线候选定向查询保留top20；三题12个观察证据后的上下文选择均与锁定实现精确重放一致。1066同预算历史片段保留请求的准备记录与真实执行结果分别保存；严格单位置替换的真实下一动作对照另见追加章节，不能与较早重新排序诊断混称。", "", "优先级：先以1066验证候选片段留存；再检验1155重复查询的替换；788先保留已观察的条件证据，再单独核查邻近对象与年代关系。当前局部对照没有终局答案，所有EM改善仍未测得。"]
    if resumed:
        overview += ["", "充值后3题均已形成有效模型运行。详情见[百炼有效基线](group-c-bailian-review.md)及各题章节；1155输出非空但属于不同候选，另两题原始模型空答，三题严格EM均为0。", "", "1066已完成真实[单片段保留的下一动作对照](1066-pair-review.md)：两臂都能在离线后续检索找到候选，处理组多返回年份片目；没有继续模型到终局，不能计作EM改善。"]
    (public / "group-c-review.md").write_text("\n".join(overview).replace("百炼初次尝试|", "百炼有效基线EM|")+"\n")
    (public / "group-c-summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2)+"\n")
    (public / "group-c-timelines.json").write_text(json.dumps(public_rows, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"questions": len(notes), "timeline_rows": {q: len(v) for q, v in public_rows.items()}}))


if __name__ == "__main__":
    main()
