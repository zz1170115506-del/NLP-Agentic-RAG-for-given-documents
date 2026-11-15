#!/usr/bin/env python3
"""Render private exact timelines and public redacted summaries from offline replay."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NARRATIVES = json.loads((ROOT / "private/narratives.json").read_text())
PURPOSE = {"231": "多线索定位合作歌曲", "390": "区域合辑的第三首曲目", "58": "论文致谢中的资助奖项"}


def compact_event(e, private):
    t = e["type"]
    if t == "assistant":
        if private:
            return (e.get("content") or "") + "；工具：" + json.dumps(e.get("tool_calls", []), ensure_ascii=False)
        return (
            "模型决定调用" + str(len(e.get("tool_calls", []))) + "个工具"
            if e.get("tool_calls")
            else "模型原始final为空答"
        )
    if t == "tool":
        ids = ",".join(p.get("evidence_id", "?") or "?" for p in e["passages"])
        hit = ",".join(p.get("evidence_id", "?") or "?" for p in e["passages"] if p["label_literal_in_text"])
        s = f"{e['name']}；成功={e['ok']}；返回{len(e['passages'])}片段；IDs={ids}；待核实目标={hit or '无'}"
        return s + ("；参数=" + e["arguments"] if private else "")
    if t == "api_attempt":
        return f"HTTP={e['http_status']}；{e['request_model']}→{e['response_model']}；tool_choice={e['tool_choice']}；usage={json.dumps(e['usage'], ensure_ascii=False)}；目标可见={e['target_evidence_visible']}"
    if t == "request":
        return f"字符={e['messages_chars']}；选中{e['selected_evidence_ids']}；full state目标={e['target_ids_in_full_state']}；真实request目标={e['target_ids_in_actual_request']}；API seq{e['api_attempt_sequence']}"
    if t == "context":
        return f"选中{e['selected_evidence']}；丢工具组{e['dropped_groups']}；字符{e['characters']}"
    if t == "state":
        return f"完整state共{len(e['evidence_ids'])}段；目标={e['target_evidence_ids']}；steps={e['state']['steps']}；tools={e['state']['tool_calls']}；tokens={e['state']['total_tokens']}；stalled={e['state']['stalled_searches']}"
    if t == "finalization":
        return f"{e['reason']}；剩余报告token={e['remaining_reported_tokens']}"
    if t == "answer":
        return (
            json.dumps({k: e[k] for k in ["answer", "supporting_evidence", "explanation"]}, ensure_ascii=False)
            if private
            else "解析后answer为空，与API原始final一致"
        )
    if t == "run_end":
        return f"{e['status']}；usage_complete={e['usage_complete']}；eligible={e['eligible']}"
    if t == "skill_loaded":
        return "自动加载过程指引：" + e["skill"]
    if t == "user":
        return "原始问题（见私密题目记录）" if private else "原始问题输入（公开省略）"
    return t


def esc(s):
    return str(s).replace("|", "\\|").replace("\n", "<br>")


for qid in ("231", "390", "58"):
    x = json.loads((ROOT / "private" / f"{qid}-analysis.json").read_text())
    for private in (True, False):
        folder = ROOT / ("private" if private else "public")
        lines = [
            f"# ID {qid}：{PURPOSE[qid]}",
            "",
            "事件序号使用原始轨迹的0起点sequence；每个记录事件都有一行。字符不是API token，所有offset是Python Unicode字符坐标。",
            "",
        ]
        if private:
            lines += [
                "本文件含原题、原标签、原始API/工具信息，仅供本地诊断。",
                "",
                f"原题：{x['question']}",
                "",
                f"原标签：`{x['reference_answer']}`；归一化：`{x['reference_normalized']}`；原输出空串，归一化EM={x['normalized_em']}。",
                "",
                NARRATIVES[qid],
                "",
                "原始JSONL行定位：`" + json.dumps(x["source_row"], ensure_ascii=False) + "`。",
                "",
            ]
        lines += ["| seq | 秒 | 事件 | 观察到的动作或状态 |", "|---:|---:|---|---|"]
        for e in x["timeline"]:
            lines.append(
                f"| {e['sequence']} | {e.get('elapsed_seconds', 0):.6f} | {e['type']} | {esc(compact_event(e, private))} |"
            )
        if private:
            lines += ["", "## 直接命中片段（原文逐字，来源已用只读SQLite核对）", ""]
            for h in x["raw_target_hits"]:
                lines += [
                    f"seq{h['tool_sequence']}，{h['evidence_id']}，doc{h['doc_id']}，offset{h['offset']}，{len(h['text'])}字符；参考串起点{h['literal_document_offset']}：",
                    "",
                    "```text",
                    h["text"],
                    "```",
                    "",
                ]
        p = folder / f"{qid}-timeline.md"
        p.write_text("\n".join(lines) + "\n")
        p.chmod(0o600 if private else 0o644)

summary = """# 第二类三题：上下文证据保留逐题复盘

本次为冻结历史的离线复盘，没有调用模型或新检索，也没有读取凭据或改旧项目源码。冻结提交为 `dab7646158fef729c3bf3e0f37b7f302727fc568`，配置身份为 `61d7cc3701b2a42a`。15次模型请求已按原选择器重放，与逐条实际 `api_attempt.request.messages` 完全相等；两个诊断hook条件在这15个请求上也与独立构造全等。历史请求模型名与返回模型名不同，沿用原兼容说明；本复盘不把其版本能力等同于未来提供商。

| ID/题意 | 首次相关工具原文 | 首次模型不可见 | 关键限制 | 语义判断 |
|---|---|---|---|---|
| 231 合作歌曲 | seq8，E9，doc43835，offset0，900字 | state10完整 → context11/request12/api13缺失 | 排第11，整项1114字，剩938字；工具组加快照57490 > 24000 | 歌名、合作艺人、生日星座构成强候选；仍缺帮派年龄、专辑关联核实 |
| 390 合辑第三轨 | seq29，E43，doc3282，offset750，476字 | state31完整 → context32/request33/api34缺失 | 排第36，整项741字，剩651字；加组57293 > 24000 | 讣闻仅支持艺人的代表作，不证明合辑第3轨；不可直接当成完整答案 |
| 58 论文资助奖项 | seq23，E30，doc28406，offset38250，900字 | state24完整 → context25/request26/api27缺失 | 排第14，整项1075字，剩432字；加组58288 > 24000 | 同论文致谢直接给出所问奖项，直接答案证据被丢 |
| 58 再次文内查找 | seq39，E37，doc28406，offset38806，410字 | state40完整 → context42/request43/api44缺失 | 排第31，整项552字，剩549字；加组26951 > 收尾23600 | 同一直接证据再次丢失，仅比快照剩余配额多3个字符 |

工具text完整转入内部state；真正丢失发生于state到模型快照的筛选，同时过大的整组assistant/tool历史被删除。原代码按题目与片段的单词集合交集排序，不区分功能词或题目中的回答槽位；只使用约一半剩余字符给证据，整项装不下便跳过，随后尝试整组保留历史。最新一组装不下就break，较早组不会继续尝试。这是可复现的上下文可见性缺陷，不是网络、模型输出长度或JSON导出截断。

三题全部由模型原始final直接返回空答，解析后与JSONL一致，原始EM均0。231/390分别以search_stalled提前收尾，收尾前剩24071/11538 token；58剩10530，恰达到动态保留最终轮次预算的阈值，触发reserve_final_usage。不能把这些情况统称为token耗尽。390曾在api13/20收到人物线索E6，seq14也明确认出候选；从context25起E6被挤掉，最终失去已发现候选。

同总预算、同问题/技能/原工具历史、不添加证据，只提高已观察目标片段的优先级：231最终请求14931字符含E9；390最终14900含E43；58最终15011含E30和E37。这个定向对照利用了参考诊断选择，必须标记为参考辅助，不能计入盲测成绩，也没有证明模型会正确回答。

无标签通用对照结果：优先已有open/find定位片段，只对58生效，最终15056字符可见E37；其余两题从未使用这样的工具，因此无变化。每doc最高原重合片段优先，对231/390无效，对58仅最后请求可见短E37（14912字符），早先E30仍不可见。最近工具结果优先在58最终成功，但390下一轮又失去目标，231始终没恢复。不能将“增加文档多样性”宣传为三题统一解法。

可复现的真实API诊断方式：保存百炼独立基线，再在单独诊断进程用 `context_retention_hook.py` 的 `focused-tool-first`（无标签）或 `observed-span-diagnostic`（参考辅助）条件。后者仅匹配新运行state里已经观察到的doc+offset；若新基线/轨迹没有这些片段，不注入、不伪造工具结果。每个条件单独输出并记录hook SHA、提供商/模型、源码/config身份、题目清单及预算；hook与基线构成源码外干预，不能只靠原config_id称身份相同。须核查新 `api_attempt.request.messages` 再判可见性，最后分别报告原始final、解析/导出、EM以及是否补齐题意约束。

百炼新基线已另做追加审计，见 [BAILIAN_ADDENDUM.md](BAILIAN_ADDENDUM.md)：231本次未检到旧目标；390最终已见讣闻目标但缺合辑桥接；58充值后已重新有效弃答，但新轨迹没有取得旧资助片段，首缺口在检索/定位；旧Arrearage尝试单独保留。以上15次精确重放专指旧提供商完整历史，不混合两种提供商的结果。

三组历史最终轮次成对API现已完成，真实结果见 [PAIRED_FINAL_RESULTS.md](PAIRED_FINAL_RESULTS.md)：231/390两臂均EM0，58由EM0变EM1并通过E37引用核验。不能将此单轮旧观察集合结果等同于新百炼完整运行已修复。

原始完整三题记录、题目/标签、中文私密叙述、每轮构造payload都在 `private/`。公开三份timeline保留每个事件、ID和坐标，不含原题、原标签或长篇原文。`group-b-replay-summary.json` 给出完整量化证据和输入hash。
"""
(ROOT / "public/README.md").write_text(summary)
(ROOT / "README.md").write_text("""# Group B 本地复现

只运行离线脚本；不会打开 `.env`、使用网络、调用提供商、启动Qwen或写旧repo。

从任务BASE执行：

```sh
work/acceptance/offline/venv/bin/python work/validation-review-drafts/group-b/replay_group_b.py
work/acceptance/offline/venv/bin/python work/validation-review-drafts/group-b/audit_bailian_addendum.py
work/acceptance/offline/venv/bin/python work/validation-review-drafts/group-b/render_reports.py
work/acceptance/offline/venv/bin/python work/validation-review-drafts/group-b/verify_artifacts.py
```

也可用CLI传入 `--repo` 与 `--out`；out目录需先放同目录的 `context_retention_hook.py`。依赖原测试环境已有pydantic和PyYAML。冻结源通过只读 `git show` 提取，原语料SQLite使用mode=ro，输出均在本目录。依赖原始100题JSONL、原标签以及文档SQLite；无需模型缓存或向量索引。

`private/` 目录700、文件600，含原题/标签/长引文/精确请求，只供本地或许可范围内移交。`public/` 是不含这些内容的可公开草稿。所有文件尚未发布。历史最终轮次的6份成对诊断输入与核验方法见 `paired-final-diagnostics/README.md`；三组已由root统一转换百炼0731完成实际调用；pair manifest保留发送前输入身份，真实结果单列在public/PAIRED_FINAL_RESULTS.md。

基线重放15/15请求与真实API消息完全相等；两个hook条件共30次离线构造与重放完全相等。排序干预没有改总预算或增加新证据；定向条件明确参考辅助。离线对照的成功仅指证据出现在构造的请求中，真实模型回答仍由root后续独立复测。
""")
# Hash both scripts and generated redacted outputs for root's integration.
paths = (
    sorted(ROOT.glob("*.py"))
    + [ROOT / "README.md"]
    + sorted((ROOT / "public").rglob("*"))
    + [
        ROOT / "paired-final-diagnostics" / n
        for n in ["pair-manifest.json", "README.md", "pair-validation-selfcheck.json"]
        if (ROOT / "paired-final-diagnostics" / n).exists()
    ]
)
manifest = {
    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in paths
    if p.is_file() and p.name != "ARTIFACT_HASHES.json"
}
(ROOT / "public/ARTIFACT_HASHES.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(
    json.dumps(
        {
            "private_reports": 3,
            "public_reports": 3,
            "events": sum(
                len(json.loads((ROOT / "private" / f"{q}-analysis.json").read_text())["timeline"])
                for q in ["231", "390", "58"]
            ),
            "hashes": len(manifest),
        }
    )
)
