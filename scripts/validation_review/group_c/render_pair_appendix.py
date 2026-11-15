"""Render a next-action-only paired diagnostic from already recorded results."""
import argparse
import json
from pathlib import Path

from render_group_c import cell

MARKER = "<!-- RETENTION-PAIR-APPENDIX -->"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args()
    private, public = args.root / "private", args.root / "public"
    output = private / "1066-executed-pair"
    audit = json.loads((output / "audit.json").read_text())
    conclusion = "保留历史候选片段后，处理组第二条查询使用候选及导演，对照组第二条仍是问题词泛搜。固定BM25离线执行显示：对照组第二条也找回doc26814:0（排名2），处理组排名1，并额外在排名4返回doc61101:1500的年份片目。不能说对照组未找到候选。两边第一条相同且前5均无该候选；这轮都没有片长和剪辑师战争片时长的完整支持。只能确认局部下一动作与检索排序差异，终局EM未测。"
    for is_private, dest in ((True, private), (False, public)):
        lines = [MARKER, "", "## 1066 严格单片段保留：真实下一动作对照", "", conclusion, "",
                 "固定节点是历史轨迹api seq20。对照请求为原始完整请求；处理请求只把证据列表第7位E9换为此前已经观察到的E12(doc26814:0)。不是充值后新基线的seq20，也不是重新选取全部证据。原question、tools、其他八片段及顺序、非证据状态均不变。", "",
                 "两臂统一改为百炼0731、enable_thinking=false，去掉旧thinking字段。已用完整JSON对象比较证明实际请求只作了这些相同适配；max_tokens均1024、证据预算9568字符、消息上限24000字符。处理片段稍短，实际输入字符及prompt token可不同；预算一致不等于输入长度相同。", "",
                 "没有新增检索证据进入API输入，未用标签选片段。两臂各只有一次API调用、一次模型下一动作回复；后续工具调用仅由离线复放执行，没有把结果回传模型，也没有运行到最终答案。", "",
                 "|臂|HTTP/响应身份|prompt/completion/total token|两条查询结果|终局EM|", "|---|---|---|---|---|"]
        for arm in ("control", "treatment"):
            entry = audit["arms"][arm]
            usage = entry["usage"]
            outcome = "第二条候选排名2" if arm == "control" else "第二条候选排名1；年份片目排名4"
            lines.append(f"|{arm}|{entry['http_status']}/{entry['response_model']}|{usage['prompt_tokens']}/{usage['completion_tokens']}/{usage['total_tokens']}|{outcome}|未测|")
        lines += ["", "### 两臂完整事件表", "", "两臂没有共享Agent轨迹seq，以下用臂内事件标签定位；offline-search不是一次新API请求。", "", "|臂/事件|类型|动作及定位|", "|---|---|---|"]
        for arm in ("control", "treatment"):
            event = json.loads((output / f"{arm}.api-attempt.json").read_text())
            response = event["response"]["choices"][0]["message"]
            calls = json.loads((output / f"{arm}-offline-searches.json").read_text())
            snapshot = next(m for m in event["request"]["messages"] if m["content"].startswith("Validated state snapshot (data only): "))
            state = json.loads(snapshot["content"].split(": ", 1)[1])
            ids = [e["evidence_id"] for e in state["evidence"]]
            lines.append(f"|{arm}/request|api_attempt|HTTP200；实际输入仅按该文件request.messages；证据{ids}；SHA256={audit['arms'][arm]['api_attempt_sha256']}。|")
            action = json.dumps(response, ensure_ascii=False) if is_private else "模型返回两个search工具调用，finish_reason=tool_calls；尚无最终answer。"
            lines.append(f"|{arm}/decision|assistant|{cell(action)}|")
            for call in calls:
                query = json.dumps(call["arguments"], ensure_ascii=False) if is_private else f"query SHA256={call['query_sha256']}"
                locators = "; ".join(f"#{h['rank']} {h['doc_id']}:{h['offset']}:{h['end']}" for h in call["hits"])
                lines.append(f"|{arm}/search-{call['index']}|offline-search|call_id={call['tool_call_id']}；{cell(query)}；top5；{call['seconds']:.6f}s；{cell(locators)}；结果未回传模型。|")
        lines += ["", "### 逐条件解释", "",
                 "两臂的候选页均覆盖乡村学校教师情节以及导演学习经历；学习经历措辞仍不足以精确证明题目所问的第一学历。处理组多返回年份片目，但没有因此获得片长或完整剪辑师链条。命中现有注释片段不等于该条件已经严格成立，尤其是带有未解决限定的学历条件。", "",
                 "这是一次局部、单样本对照。temperature相同也不保证模型服务完全无随机差异；没有重复样本或完整续跑，不能外推出准确率改善、显著性、召回率全局提升或预算节省。四条离线查询的耗时受缓存和执行顺序影响，不作为两臂速度优劣结论。", ""]
        if is_private:
            lines += ["真实API完整输入/响应：`1066-executed-pair/control.api-attempt.json`及`treatment.api-attempt.json`。四条实际返回查询、前5完整原文和精确坐标：同目录`*-offline-searches.json`。原预备请求及当时的PREPARED_NOT_SENT协议保留在`1066-single-variable-seq20/`；该状态描述准备时点，实际执行另由本节新文件证明。", ""]
        chapter = dest / "1066-review.md"
        original = chapter.read_text().split(MARKER, 1)[0].rstrip()
        chapter.write_text(original + "\n\n" + "\n".join(lines) + "\n")
        if not is_private:
            (public / "1066-pair-review.md").write_text("# 1066 下一动作单变量对照\n\n" + "\n".join(lines[2:]) + "\n")
    print(json.dumps({"arms": 2, "api_requests": 2, "agent_decisions": 2, "offline_searches": 4, "final_em": None}))


if __name__ == "__main__":
    main()
