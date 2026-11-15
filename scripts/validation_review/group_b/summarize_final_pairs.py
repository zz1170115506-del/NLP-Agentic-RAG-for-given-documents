#!/usr/bin/env python3
"""Summarize six existing paired API records and frozen-validator results, offline."""

import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path


def sha(b):
    return hashlib.sha256(b).hexdigest()


def canon(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def save(p, x, private=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2) + "\n")
    if private:
        p.chmod(0o600)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--group-root", type=Path, default=Path("work/validation-review-drafts/group-b"))
    a.add_argument(
        "--api-root",
        type=Path,
        default=Path("work/validation-failure-review/outputs/validation-review/paired-diagnostics"),
    )
    args = a.parse_args()
    root = args.group_root
    pairs = root / "paired-final-diagnostics"
    manifest = json.loads((pairs / "pair-manifest.json").read_text())
    spec = importlib.util.spec_from_file_location("offline_context_review", root / "replay_group_b.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    explanations = {
        "231": "control沿用错误出生月份的人物候选并称没有歌曲桥接；treatment明确认出正确出生/星座及合作歌曲候选，说明E9确已被理解，但仍指出缺入帮年龄及专辑/发行关系，最终answer保持空串。候选识别改善，没有达到EM或全部约束通过；不能把explanation中出现候选名计为answer正确。",
        "390": "control缺合辑及人物关联；treatment明确引用E43的人物死亡线索，但仍指出未把该人物或代表作连接到所问合辑和第三轨。讣闻中的字面歌名没有补上轨次关系，空答符合现有语义证据缺口；不应通过要求模型放宽断言来制造EM提升。",
        "58": "control已识别论文，但表示未见致谢奖项而空答；treatment给出奖项答案并选择E37，冻结引用门控核对原成功find结果、真实请求可见性、SQLite原文/坐标/URL均通过，规范化EM由0变1。该奖项在同论文Funding段直接出现，语义支持充分。此结果支持旧观察集合下的上下文保留政策影响最终回答；新百炼完整运行未取到该段的问题仍未被解决。treatment因同一装箱排序变化也增加E33并移出E25，不能描述成只多了一句话，也未单独排除其他片段交互。",
    }
    reports = []
    event_lines = []
    private_lines = [
        "# 三题历史最终轮次真实成对诊断（私密）",
        "",
        "此文件含原始模型答案及精确标签匹配，只限本地或授权范围。新旧历史不得合并计算正式盲测成绩。",
        "",
    ]
    for c in manifest["cases"]:
        q = c["case_id"]
        events = {
            arm: json.loads((args.api_root / q / (arm + ".api-attempt.json")).read_text())
            for arm in ["control", "treatment"]
        }
        assert {k: v for k, v in events["control"]["request"].items() if k != "messages"} == {
            k: v for k, v in events["treatment"]["request"].items() if k != "messages"
        }
        changed = [
            i
            for i, (x, y) in enumerate(
                zip(events["control"]["request"]["messages"], events["treatment"]["request"]["messages"])
            )
            if x != y
        ]
        assert changed == [1]
        arms = {}
        private_lines += [f"## ID {q}", "", explanations[q], ""]
        for arm, e in events.items():
            original = args.api_root / q / (arm + ".api-attempt.json")
            dest = pairs / "private" / f"{q}-{arm}.api-attempt.json"
            shutil.copyfile(original, dest)
            dest.chmod(0o600)
            vpath = pairs / "private" / f"{q}-{arm}.response-validation.json"
            v = json.loads(vpath.read_text())
            assert (
                e["http_status"] == 200 and e["response"]["model"] == e["request"]["model"] == "deepseek-v4-flash-0731"
            )
            assert e["request"]["enable_thinking"] is False and "thinking" not in e["request"]
            assert v["actual_request_supplied"] and v["actual_canonical_request_sha256"] == sha(canon(e["request"]))
            assert v["response_sha256"] == sha(canon(e["response"])) and v["schema_and_citation_check"] == "passed"
            raw = e["response"]["choices"][0]["message"]["content"]
            rawobj = json.loads(raw)
            assert rawobj["answer"] == v["parsed_answer"]
            visible = m.visible(e["request"]["messages"])
            ids = [p["evidence_id"] for p in visible]
            assert ids == c[arm]["selected_evidence_ids"]
            fields = {
                "http_status": 200,
                "request_model": e["request"]["model"],
                "response_model": e["response"]["model"],
                "status": v["status"],
                "model_abstention": v["model_abstention"],
                "normalized_em": v["normalized_em"],
                "schema_check": "passed",
                "citation_gate": "not_required_for_empty_answer"
                if v["model_abstention"]
                else "passed_original_observed_visible_and_exact_corpus",
                "raw_answer_matches_saved_parsed_answer": True,
                "full_batch_prediction_export_executed": False,
                "supporting_evidence_ids": rawobj.get("supporting_evidence", []),
                "resolved_evidence_ids": v.get("resolved_evidence_ids", []),
                "selected_evidence_ids": ids,
                "actual_request_characters": len(
                    json.dumps(e["request"]["messages"], ensure_ascii=False, separators=(",", ":"))
                ),
                "usage": e["response"].get("usage"),
                "finish_reason": e["response"]["choices"][0].get("finish_reason"),
                "api_record_file": "private/" + dest.name,
                "api_record_file_sha256": sha(dest.read_bytes()),
                "actual_canonical_request_sha256": sha(canon(e["request"])),
                "actual_messages_sha256": sha(canon(e["request"]["messages"])),
                "response_sha256": sha(canon(e["response"])),
                "validation_file": "private/" + vpath.name,
                "validation_sha256": sha(vpath.read_bytes()),
                "actual_request_supplied": True,
            }
            arms[arm] = fields
            private_lines += [
                f"### {arm}",
                "",
                f"HTTP200；模型{fields['response_model']}；schema={fields['schema_check']}；citation={fields['citation_gate']}；EM={fields['normalized_em']}；usage={json.dumps(fields['usage'])}",
                "",
                "实际原始final：",
                "```json",
                raw,
                "```",
                "",
                "冻结解析/引用核验后的结果（evidence可能由程序从ID补全，不是模型新写引文）：",
                "```json",
                json.dumps(v, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
            event_lines.append(
                {
                    "location": f"{q}/{arm}/api_attempt",
                    "type": "API",
                    "case_id": q,
                    "arm": arm,
                    "description": f"HTTP200；输入{fields['actual_request_characters']}字符；模型0731；usage={json.dumps(fields['usage'], ensure_ascii=False)}；实际request SHA={fields['actual_canonical_request_sha256']}",
                }
            )
            event_lines.append(
                {
                    "location": f"{q}/{arm}/response.choices[0].message",
                    "type": "assistant",
                    "case_id": q,
                    "arm": arm,
                    "description": f"{'原始空答' if fields['model_abstention'] else '原始非空答案'}；schema通过；citation={fields['citation_gate']}；EM={fields['normalized_em']}；引用IDs={fields['supporting_evidence_ids']}；finish_reason={fields['finish_reason']}",
                }
            )
        reports.append(
            {
                "case_id": q,
                "scope": "one isolated final turn on old observed history; not fresh complete-agent evaluation",
                "condition": c["condition"],
                "reference_assisted": c["reference_assisted"],
                "same_budget": {
                    "context_total_chars": 24000,
                    "selector_final_chars": 23600,
                    "max_output_tokens": 1024,
                    "temperature": 0,
                    "tools_disabled": True,
                },
                "only_messages_differ": True,
                "changed_message_indices": [1],
                "all_other_provider_converted_fields_identical": True,
                "selection_changes": {
                    "newly_visible_ids": c["newly_visible_ids"],
                    "no_longer_visible_ids": c["no_longer_visible_ids"],
                },
                "arms": arms,
                "semantic_interpretation": explanations[q],
            }
        )
    output = {
        "frozen_source_commit": manifest["frozen_source_commit"],
        "hook_sha256": manifest["hook_sha256"],
        "validator_sha256": sha((root / "validate_paired_response.py").read_bytes()),
        "pair_input_manifest_sha256": sha((pairs / "pair-manifest.json").read_bytes()),
        "provider_translation_equal_both_arms": {
            "model": "deepseek-v4-flash-0731",
            "removed": "thinking",
            "added": {"enable_thinking": False},
        },
        "actual_api_calls_performed_by_root": 6,
        "new_api_calls_by_this_summarizer": 0,
        "validation_processes": 6,
        "calls_all_http_200": True,
        "calls_all_response_model_exact": True,
        "calls_all_actual_messages_match_prepared": True,
        "calls_all_schema_passed": True,
        "answer_changed_empty_to_reference_match_cases": ["58"],
        "public_results_exclude_answers_and_labels": True,
        "cases": reports,
        "events": event_lines,
    }
    save(root / "public/paired-final-results.json", output)
    private_report = pairs / "private/PAIRED_FINAL_RESULTS.md"
    private_report.write_text("\n".join(private_lines) + "\n")
    private_report.chmod(0o600)
    lines = [
        "# 历史最终轮次：三组成对API结果",
        "",
        "以下6次真实调用由root执行，本脚本仅做离线核验。两臂均百炼0731、thinking关闭、temperature0、工具禁用、max_tokens1024、总上下文上限24000；实际发送请求除messages[1]中的证据选择之外逐字段相同。每个响应都在独立进程中使用OLD冻结解析器与只读语料验证。",
        "",
        "| ID | 条件 | control → treatment EM | schema/引用 | 语义结论 |",
        "|---|---|---|---|---|",
    ]
    for c in reports:
        lines.append(
            f"| {c['case_id']} | {c['condition']}；参考辅助={c['reference_assisted']} | {c['arms']['control']['normalized_em']} → {c['arms']['treatment']['normalized_em']} | 两臂schema通过；{'非空答案E37来源/可见/原文坐标通过' if c['case_id'] == '58' else '两臂空答，无非空引用待核验'} | {c['semantic_interpretation']} |"
        )
    lines += [
        "",
        "空答通过schema不意味着完成了引用证明：冻结程序对空answer直接返回insufficient_evidence；只有58 treatment的非空回答实际经过ID来源、历史可见性和语料原文核验。也没有JSON解析后误删答案：6臂raw answer与解析后保存结果逐字一致。成对实验仅调用最终一轮并验证响应，未执行完整batch预测导出链，不能声称该导出链也在此实验中复测。",
        "",
        "单变量是保留政策；58同时因容量重排加入E33、E37并移出E25，记录如实保留。结果支持这一次旧观察集合下的可见性改动有效，不能据此宣称新百炼完整运行、其他题或一般正确率已改善。231/390 treatment的explanation虽识别了更好的候选，answer仍空，EM不能因此算1。",
        "",
        "以下是6个API事件及对应6个assistant响应字段，位置来自实际诊断记录；不是伪造的历史sequence。诊断过程无新工具调用。",
        "",
        "| 记录位置 | 类型 | 可公开观察 |",
        "|---|---|---|",
    ]
    for e in event_lines:
        lines.append(f"| {e['location']} | {e['type']} | {e['description'].replace('|', '/')} |")
    lines += [
        "",
        "精确raw final与规范化标签仅见`../paired-final-diagnostics/private/PAIRED_FINAL_RESULTS.md`。公开JSON保留实际请求/响应SHA、用量、证据ID、schema、citation、EM与语义判定，未公开答案和原标签。",
        "",
    ]
    (root / "public/PAIRED_FINAL_RESULTS.md").write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "validated_actual_pairs": 3,
                "all_http200": True,
                "all_schema_passed": True,
                "em_by_case": {
                    c["case_id"]: [c["arms"][a]["normalized_em"] for a in ["control", "treatment"]] for c in reports
                },
                "public_event_rows": len(event_lines),
                "new_api_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__ + ": " + str(exc))
        raise SystemExit(1)
