"""Export complete private event tables and public counters without question/answer text."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("work/validation-review-drafts/group-a"))
    args = parser.parse_args()
    directory = args.directory
    replays = list(map(json.loads, (directory / "replay-private.jsonl").read_text().splitlines()))
    summaries = []
    for ident in ("960", "1035", "64"):
        item = json.loads((directory / f"{ident}-timeline-private.json").read_text())
        lines = [f"# ID {ident} 私有完整时间线", "", "此文件包含原题、参考答案和原查询，只进入团队可恢复的私有加密附件。",
                 "", "## 输入与严格评分", "", item["question"], "",
                 f"参考答案：`{item['reference_answer']}`；导出：`{item['exported_answer']}`。",
                 f"规范化参考：`{item['normalized_reference']}`；规范化导出：`{item['normalized_export']}`；严格EM={item['strict_em']}。",
                 "", f"工具{item['tools']}次，HTTP{item['http_attempts']}次，原始usage合计{item['total_tokens']}tokens。兼容错误{item['compat_errors']}，引用错误{item['grounding_errors']}。",
                 "", "## 全部事件（sequence与零基轨迹索引一致）", "",
                 "| seq / 秒 | 类型 | 实际内容与可观察依据 |", "|---|---|---|"]
        action_rows, seen_sequences = [], set()
        for event in item["timeline"]:
            sequence, kind = event["sequence"], event["type"]
            seen_sequences.add(sequence)
            public = {"sequence": sequence, "seconds": event["seconds"], "type": kind}
            if kind == "api_attempt":
                usage = event["response"].get("usage", {})
                ids = [e.get("evidence_id") for e in event["visible_evidence"]]
                detail = (f"请求R{event['request_round']}：HTTP{event['http_status']}，tool_choice={event['request'].get('tool_choice')}；"
                          f"actual messages={event['message_chars']}字符；tool消息={event['tool_messages']}；证据={ids}；usage={usage}")
                public.update(request_round=event["request_round"], http_status=event["http_status"],
                              tool_choice=event["request"].get("tool_choice"), message_chars=event["message_chars"],
                              visible_evidence_ids=ids, visible_chunks=[e.get("chunk_id") for e in event["visible_evidence"]],
                              tool_messages=event["tool_messages"], usage=usage)
                action_rows.append(public)
            elif kind == "assistant":
                detail = f"模型实际可见输出：{event.get('content')}；调用={event.get('tool_calls')}"
                public.update(request_round=event["request_round"], call_ids=[x["id"] for x in event.get("tool_calls", []) or []],
                              tool_names=[x["function"]["name"] for x in event.get("tool_calls", []) or []],
                              final_empty_answer=(not event.get("tool_calls") and item["exported_answer"] == ""))
                action_rows.append(public)
            elif kind == "tool":
                detail = (f"调用{event['call_id']}；{event['tool_name']}({event['arguments']})；结果{event['results_count']}；"
                          f"新证据{event['new_passages']}；相同query重复={event.get('exact_repeated_query')}。完整排名表见下。")
                public.update(request_round=event["request_round"], call_id=event["call_id"], tool_name=event["tool_name"],
                              actual_top_k=event["arguments"].get("top_k"), results_count=event["results_count"],
                              new_passages=event["new_passages"], repeated_query=event.get("exact_repeated_query"),
                              results=[{k:r[k] for k in ("rank", "doc_id", "chunk_id", "offset", "end", "new_evidence")} for r in event["results"]])
                action_rows.append(public)
            elif kind == "state":
                state = event["event"]["state"]
                detail = {k: state.get(k) for k in ("steps", "tool_calls", "stalled_searches", "active_queries", "candidate_answer")}
            elif kind == "run_start":
                detail = event["metadata"]
            elif kind == "user":
                detail = "原题作为user消息进入；完整文字见本文件开头与JSON。"
            elif kind == "request":
                detail = "逻辑请求快照；真正传输的payload以紧随其后的api_attempt.request.messages为准。"
            elif kind == "skill_loaded":
                detail = {k:v for k,v in event["event"].items() if k != "instructions"}
            else:
                detail = event.get("event", {})
            lines.append(f"| {sequence} / {event['seconds']} | {kind} | {cell(detail)} |")
        lines += ["", "## 每次工具返回的完整名次与坐标", ""]
        for event in item["timeline"]:
            if event["type"] != "tool":
                continue
            lines += [f"### seq{event['sequence']} / {event['call_id']}", "", f"参数：`{json.dumps(event['arguments'], ensure_ascii=False)}`", "",
                      "| rank | doc / chunk | [offset,end) | 新证据 |", "|---:|---|---|---|"]
            lines += [f"| {h['rank']} | {h['doc_id']} / {h['chunk_id']} | [{h['offset']},{h['end']}) | {h['new_evidence']} |" for h in event["results"]]
        lines += ["", "## 离线重放记录", "", "原query按top5和top20各执行一次；所有重复历史调用仍在时间线中逐次保留。query变体与参考答案辅助查询分别标记，不算在线结果。", "",
                  "| 名称 / 类型 | query | top_k | 结果ID/排名 |", "|---|---|---:|---|"]
        for replay in replays:
            if replay["id"] != ident:
                continue
            lines.append(f"| {replay['name']} / {replay['kind']} | {cell(replay['query'])} | {replay['top_k']} | " +
                         cell([(h["rank"], h["chunk_id"]) for h in replay["results"]]) + " |")
        lines += ["", f"原始全部messages/response和原文在`{ident}-timeline-private.json`，未经缩写的历史预测在`{ident}-original-private.json`；"
                  "新定位文档与邻接片段在`located-documents-private.json`和`located-chunks-private.json`。字符坐标为Python Unicode、左闭右开。"]
        (directory / f"{ident}-timeline-private.md").write_text("\n".join(lines) + "\n")
        expected = Counter(e["type"] for e in item["timeline"] if e["type"] in {"api_attempt", "assistant", "tool"})
        actual = Counter(e["type"] for e in action_rows)
        if expected != actual or len(seen_sequences) != len(item["timeline"]):
            raise ValueError("Event coverage mismatch")
        summaries.append({"id":ident, "historical_em":item["strict_em"], "tools":item["tools"],
                          "http_attempts":item["http_attempts"], "total_tokens":item["total_tokens"],
                          "raw_usage":item["raw_usage"], "exact_query_duplicates":item["exact_query_duplicates"],
                          "compat_errors":item["compat_errors"], "grounding_errors":item["grounding_errors"],
                          "all_event_count":len(item["timeline"]), "api_assistant_tool_coverage":dict(actual),
                          "actions":action_rows})
    summary = {"scope":"group A IDs960/1035/64; historical source dab7646 config61d7; offline only",
               "historical_prediction_sha256":"17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8",
               "bm25_replay_count":len(replays), "bm25_replay_kinds":dict(Counter(r["kind"] for r in replays)),
               "historical_prefix_comparisons":sum(len(r["historical_prefix_matches"]) for r in replays),
               "all_historical_prefixes_exact":all(c["match"] for r in replays for c in r["historical_prefix_matches"]),
               "cases":summaries}
    public_text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if re.search(r"sk-[a-fA-F0-9]{16,}|/(?:Users|private)/", public_text):
        raise ValueError("Sensitive public output")
    (directory / "group-a-public-statistics.json").write_text(public_text)
    hashes = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob("*")
              if p.is_file() and p.name != "private-evidence-manifest.json" and
              ("private" in p.name or p.name == "identity.json" or p.suffix == ".py")}
    (directory / "private-evidence-manifest.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(json.dumps({"cases":len(summaries),"every_api_assistant_tool_event_covered":True,"offline_replays":len(replays)}))


if __name__ == "__main__":
    main()
