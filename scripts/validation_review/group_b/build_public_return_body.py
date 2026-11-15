#!/usr/bin/env python3
"""Build a self-contained public section; only redacted input artifacts are read."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
old = json.loads((ROOT / "public/group-b-replay-summary.json").read_text())
new = json.loads((ROOT / "public/bailian-addendum.json").read_text())
PAIR = ROOT / "paired-final-diagnostics/pair-manifest.json"
pair = json.loads(PAIR.read_text())
DETAIL = {
    "231": (
        "定位一首符合人物经历、出生信息和合作关系的歌曲。",
        "旧raw工具seq8取得E9（doc43835:0，900字符）；state10原样保存。首次不可见发生在context11/request12/api13：E9排第11，整项1114字符但剩938；整个工具组加快照57490字符也超过24000，故两条传递通路均未保留。",
        "片段提供歌曲、合作艺人及出生/星座的强候选，仍需核实帮派年龄和所属专辑；不是仅凭字面命中就已完成题意。旧最终raw/解析/导出均为空答，search_stalled提前收尾，剩24071 token，原EM=0。",
        "新百炼3次HTTP200、4工具、9687 token，仍为空答、EM=0。此新检索未取得旧目标片段或参考串，故首缺口已是检索；历史保留hook对未观察到的目标空操作。",
    ),
    "390": (
        "从区域合辑、文章线索和艺人生平共同定位该合辑的第三首曲目。",
        "旧seq29取得E43（doc3282:750，476字符）；state31完整保存。context32/request33/api34首次不可见：E43排第36，整项741字符但剩651；工具组加快照57293字符超24000。更早E6人物证据曾在api13/api20可见、seq14被模型明确认出，从context25起被挤掉。",
        "讣闻只给出艺人的代表作，未给合辑和第三轨对应关系。保留该片段只能恢复候选，不能证明歌名语义正确。旧最终raw/解析/导出均为空答，search_stalled时余11538 token，原EM=0。",
        "新百炼6次HTTP200、10工具、23082 token，仍为空答、EM=0。新E15（同doc:offset）已经在API seq36和44可见；另有同名CD/重录片段，仍不是所问合辑。最终缺口是合辑与轨次的关联证据，不能再以“模型没见歌名”解释这一新结果。",
    ),
    "58": (
        "识别给定论文，并提取其致谢中用于资助的奖项名称。",
        "旧seq23取得E30（doc28406:38250，900字符）直接资助段；state24完整，context25/request26/api27排第14，1075字符大于剩432而遗漏。seq39文内查找再取E37（同doc:38806，410字符），state40完整；最终context42/request43/api44时整项552字符仅比剩549多3仍整项不选，工具组加快照26951又超收尾23600。",
        "该奖项属于已识别论文的直接致谢记录；论文元数据时间与元素外部事实需单独谨慎核对，但不是只有同名词的无关命中。旧最终raw/解析/导出均为空答，reserve_final_usage在余10530 token时触发，原EM=0。",
        "充值后新百炼5次HTTP200、8次search、19081 token，seq34 search_stalled（余14475）→seq37最终API→seq38明确空答，EM=0。新运行只命中同doc的参考文献尾段，未取得旧奖项窗口，也未open/find；首缺口在检索/论文定位。先前HTTP400 Arrearage的失败尝试另存attempt-0，不能和这次有效弃答混为一条记录。",
    ),
}
lines = [
    "# 第二类三题逐题复盘（可并入总回传）",
    "",
    "公开版仅概述题意和证据坐标，不包含原题全文、原始标签或长篇原文。原题、规范化标签、原始API/工具正文及详细中文叙述均单独保留在private。",
    "",
    "旧历史条件：冻结代码 `dab7646158fef729c3bf3e0f37b7f302727fc568`、config `61d7cc3701b2a42a`、官方兼容请求模型名与实际返回模型名有区别。新百炼条件：基线代码 `8c8e545126e329919d2c16b18cacea6e139ebb29`、config `900fc3b95b775d2a`，请求与成功响应均为 `deepseek-v4-flash-0731`。两者是不同运行，不能把相同ID下的证据编号或故障类别直接互换。",
    "",
    "以下每张时间线使用原始0起点sequence，列出所有记录事件，因此每一次真实API、模型assistant决策、工具调用都各有一行。完整旧历史共123事件，当前有效百炼三题共116事件；合计239事件、29次API尝试、29次assistant响应、46次工具返回。旧58账户中断的23事件独立保存，不计入这239条有效历史。",
    "",
    "| 题目ID | 旧EM | 新百炼EM | 新有效状态 | 新报告token/工具/API |",
    "|---|---:|---:|---|---|",
]
for q in ["231", "390", "58"]:
    n = next(v for v in new["questions"] if v["id"] == q)
    o = next(v for v in old["summary"] if v["id"] == q)
    lines.append(
        f"| {q} | {o['normalized_em']} | {n['normalized_em']} | {n['status']} | {n['tokens']} / {n['tool_calls']} / {len(n['api_calls'])} |"
    )
for q in ["231", "390", "58"]:
    purpose, failure, meaning, baseline = DETAIL[q]
    lines += [
        "",
        f"## ID {q}",
        "",
        f"题意：{purpose}",
        "",
        f"旧历史首次故障：{failure}",
        "",
        f"语义和评分：{meaning}",
        "",
        f"新基线：{baseline}",
        "",
        "旧运行逐事件时间线：",
        "",
    ]
    for suffix, title in [("", None), ("-bailian", "新百炼有效运行逐事件时间线：")]:
        if title:
            lines += ["", title, ""]
        content = (ROOT / "public" / f"{q}{suffix}-timeline.md").read_text()
        table = content[content.index("| seq |") :]
        lines += table.rstrip().splitlines()
    c = next(v for v in pair["cases"] if v["case_id"] == q)
    lines += [
        "",
        "历史最终请求的单变量成对诊断：",
        "",
        f"同24000字符总上限、23600选择器上限及1024输出token；control {c['control']['messages_characters']}字符，treatment {c['treatment']['messages_characters']}字符。条件 `{c['condition']}`，参考辅助={c['reference_assisted']}；仅改变state快照中的证据排序/选择，新增可见IDs={c['newly_visible_ids']}，移出IDs={c['no_longer_visible_ids']}。所有片段都是该题旧轨迹已成功观察的原文，未增加标签或新检索。",
    ]
lines += [
    "",
    "## 共性结论与验证范围",
    "",
    "旧运行的字面证据确实完整到达内部state，随后因快照配额、整项跳过和整组历史删除而对模型不可见；15个原请求已逐条重放，与真实api_attempt.request.messages全等。两种hook在30个离线对照构造上也完全一致。此处的“成功”只指证据进入构造请求，不能当作模型回答成功。",
    "",
    "通用对照的边界已实际检查：聚焦open/find窗口优先只恢复旧58最后一次定位片段；每doc最高词重合片段优先也仅在旧58最后阶段恢复短窗口，对旧231/390无效。新百炼231和58未取得相同目标，390最后已看到歌名，因此历史保留实验不能被包装成对三个新完整运行的统一修复。",
    "",
    "成对实时诊断需另存双方实际百炼请求/响应，并在相同提供商映射后比较。引用核验使用原成功工具历史、该臂真实messages、原state及只读语料；分别记录raw final、解析/导出、引用有效性、规范化EM和语义核验。来源通过不代表满足全部题意，尤其390还必须确认合辑第三轨。前文EM表只统计完整旧/新基线；下文单列已完成的成对API结果，不能混入盲测基线得分。",
    "",
    "可复现文件：`group-b-replay-summary.json`、`bailian-addendum.json`、`verification-result.json`、`ARTIFACT_HASHES.json`；成对输入及核验方法在`../paired-final-diagnostics/README.md`。私密原始记录和payload不随本公开正文展开。",
    "",
]
lines += [
    "",
    "## 历史最终轮次的真实API成对结果",
    "",
    "在上述239个原始轨迹事件之外，本节另列6个真实诊断API记录及6个对应assistant响应字段，共12行；没有为它们伪造历史sequence，也没有新工具调用。",
    "",
    (ROOT / "public/PAIRED_FINAL_RESULTS.md").read_text(),
]
p = ROOT / "public/GROUP_B_RETURN_BODY.md"
p.write_text("\n".join(lines))
assert len(re.findall(r"^\| \d+ \| \d+\.\d{6} \|", p.read_text(), re.M)) == 239
print(
    json.dumps(
        {
            "public_body": "public/GROUP_B_RETURN_BODY.md",
            "events": 239,
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    )
)
