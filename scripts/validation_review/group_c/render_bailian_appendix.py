"""Append separately identified completed baseline timelines; never send model requests."""
import argparse
import json
from pathlib import Path

from render_group_c import cell, describe
from reproduce_group_c import IDS, write

MARKER = "<!-- BAILIAN-APPENDIX -->"


def failure_rows(record):
    rows = []
    for event in record["trajectory"]:
        kind = event.get("event", event.get("role"))
        if kind == "api_attempt":
            desc = f"首请求HTTP{event['http_status']}，Arrearage；无模型答题回复，usage_unknown={event.get('usage_unknown')}。实际输入只认本事件request.messages。"
        elif kind == "error":
            desc = "服务商账户错误被记录；没有Agent答题决定。"
        elif kind == "run_end":
            desc = "provider_error结束，reported_tokens=0，工具0，EM未测；不与充值后运行拼接。"
        else:
            desc = describe(dict(kind=kind, **event), False)
        rows.append(dict(sequence=event["sequence"], kind=kind, description=desc))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    private, public = args.root / "private", args.root / "public"
    target = private / "bailian-baseline"
    notes = json.loads((target / "semantic-notes.json").read_text())
    identity = json.loads((target / "identity.json").read_text())
    summaries = json.loads((target / "summary.json").read_text())
    timelines, failures = {}, {}
    overview = ["# 第三组：充值后百炼有效基线", "", "初次3题均为账户错误，未形成模型答题。充值后另行完成3题，下面统计只对应有效运行。原失败轨迹保留，不纳入模型EM分母。", "",
                f"有效预测SHA-256：`{identity['prediction_sha256']}`；配置`{identity['metadata']['config_id']}`；实际源码指纹`{identity['metadata']['runtime_identity']['code_sha256']}`。请求/响应模型均为`deepseek-v4-flash-0731`。固定语料、BM25与历史一致；服务商、模型响应身份及模型选择的查询/实际top_k存在差异，因此跨运行不能作单变量因果比较。", "",
                "|题号|有效API/工具/token|结果|严格EM|新运行首个有证据的问题|", "|---|---|---|---|---|---|"]
    for id in IDS:
        audit = json.loads((target / f"{id}-audit.json").read_text())
        note = notes[id]
        failed = json.loads((target / "initial-failures" / f"{id}-record.json").read_text())
        failures[id] = failure_rows(failed)
        summaries[id].update(first_evidenced_problem=note["first_problem"], conclusion=note["public_conclusion"],
                             proposal=note["proposal"], initial_provider_failure_retained=True)
        outcome = "非空、不同实体候选" if summaries[id]["nonempty"] else "原始模型弃答"
        overview.append(f"|{id}|{audit['api_requests']}/{audit['tool_calls']}/{audit['total_tokens']}|{outcome}|{audit['em']}|{cell(note['first_problem'])}|")
        for is_private, dest in ((True, private), (False, public)):
            lines = [MARKER, "", "## 充值后百炼基线对照", "", note["public_conclusion"], "", f"本次有效运行：配置`{summaries[id]['config_id']}`，{audit['api_requests']}个HTTP200、{audit['tool_calls']}次search、usage总计{audit['total_tokens']}；严格EM={audit['em']}。没有open/find，所有search使用配置默认top5。", "", "首次问题：" + note["first_problem"], ""]
            if is_private:
                lines += ["### 本次原题、答案与叙述", "", audit["question"], "", f"参考原值：`{json.dumps(audit['reference_answer'],ensure_ascii=False)}`；导出：`{json.dumps(audit['prediction_answer'],ensure_ascii=False)}`；规范化：`{audit['normalized_reference']}` vs `{audit['normalized_prediction']}`。", "", note["narrative"], ""]
                if "alias_assessment" in note:
                    lines += ["别名/评分核查：" + note["alias_assessment"], ""]
            lines += ["### 初次账户错误尝试：全部事件", "", "|seq/index|事件|定位与结果|", "|---|---|---|"]
            for row in failures[id]:
                lines.append(f"|{row['sequence']}|{row['kind']}|{cell(row['description'])}|")
            lines += ["", "### 充值后有效运行：全部事件", "", "seq为本次轨迹自己的零起算位置，不与历史seq混用。实际模型输入只读取`api_attempt.request.messages`。", "", "|seq/index|事件|定位与结果|", "|---|---|---|"]
            public_rows = []
            for row in audit["timeline"]:
                description = describe(row, is_private)
                lines.append(f"|{row['sequence']}|{row['kind']}|{cell(description)}|")
                public_rows.append(dict(sequence=row["sequence"], kind=row["kind"], description=describe(row, False)))
            if not is_private:
                timelines[id] = public_rows
            lines += ["", "### 本次逐条件语义核查", "", "|条件|判定|支持/反证定位|缺口与实际可见性|", "|---|---|---|---|"]
            excerpts = []
            for i, condition in enumerate(note["conditions"], 1):
                locators = []
                for tag in ("support", "counter"):
                    for e in condition.get(tag, []):
                        locator = f"doc{e['doc_id']}[{e['start']}:{e['end']}]"
                        locators.append(("反证 " if tag == "counter" else "支持 ") + locator)
                        if is_private:
                            excerpts += [f"#### 条件{i} {tag} {locator}", "", f"来源：{e['url']}；本次工具覆盖：{e['new_tools']}；本次实际请求覆盖：{e['new_actual_requests']}。", "", "```text", e["text"], "```", ""]
                # Public text uses neutral condition numbering; private annotations may name candidates.
                name = condition["condition"] if is_private else f"条件{i}（对应历史条件表）"
                gap = condition["gap"] if is_private else "完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。"
                lines.append(f"|{cell(name)}|{cell(condition['status'])}|{cell('; '.join(locators))}|{cell(gap)}|")
            if is_private:
                lines += ["", "### 本次精确片段", ""] + excerpts
                lines += ["### 最后原始回复与处理链", "", "```json", audit["final_original_model_content"], "```", ""]
                if audit["prediction_answer"]:
                    lines += ["原始模型非空 → JSON解析成功 → supporting_evidence ID及原文坐标验证通过 → answer事件保持非空 → completed → Prediction保持相同答案。这里引用审计只验证片段来源，不验证全部线索在语义上成立；错误候选不是导出阶段造成。", ""]
                else:
                    lines += ["原始模型空answer → JSON解析成功 → 空答分支直接insufficient_evidence，尚未验证非空答案引用 → answer/run_end/Prediction均为空；没有解析错误或引用拒绝清空非空内容。", ""]
            lines += ["### 可复测项及解释边界", "", note["proposal"], "", "本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。", ""]
            chapter = dest / f"{id}-review.md"
            original = chapter.read_text().split(MARKER, 1)[0].rstrip()
            chapter.write_text(original + "\n\n" + "\n".join(lines) + "\n")
    write(public / "group-c-bailian-summary.json", summaries)
    write(public / "group-c-bailian-timelines.json", timelines)
    write(public / "group-c-initial-failure-timelines.json", failures)
    (public / "group-c-bailian-review.md").write_text("\n".join(overview) + "\n")
    print(json.dumps({"valid_event_counts": {q: len(v) for q, v in timelines.items()}, "failed_event_counts": {q: len(v) for q, v in failures.items()}}))


if __name__ == "__main__":
    main()
