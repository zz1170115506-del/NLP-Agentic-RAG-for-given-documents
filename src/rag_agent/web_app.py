"""Streamlit view: presentation only; inference lives in agent.loop."""
import json
from pathlib import Path
import streamlit as st

from rag_agent.config import Settings
from rag_agent.runtime import make_runtime, run_question
from rag_agent.schemas import Question


@st.cache_resource(show_spinner=False)
def runtime(config_json: str):
    return make_runtime(Settings.model_validate_json(config_json))


def main():
    st.set_page_config(page_title="Evidence Desk · COMP5423", page_icon="📚", layout="wide")
    st.caption("COMP5423  ·  SKILL-AUGMENTED SEARCH AGENT")
    st.title("Evidence Desk")
    st.write("在固定文档集合中查找、核对证据，查看每一步工具操作。")
    with st.sidebar:
        st.subheader("运行设置")
        paths = sorted(Path("configs").glob("*.yaml"))
        names = [str(x) for x in paths]
        if not names:
            st.error("请从项目根目录启动网页，以读取 configs 和 skills。")
            return
        selected = st.selectbox("配置", names, index=names.index("configs/demo.yaml") if "configs/demo.yaml" in names else 0)
        try:
            cfg = Settings.load(selected)
        except Exception as exc:
            st.error(str(exc))
            return
        st.write("模式：", "离线合成演示" if cfg.mode == "demo" else "真实模型 API")
        st.caption("Agent：1.2" if cfg.agent_engine == "agent12" else "Agent：基线")
        st.caption(f"检索：{cfg.method} · 索引：{cfg.index_dir}")
        st.caption(f"最多 {cfg.max_steps} 轮 / {cfg.max_tool_calls} 次工具调用")
        st.caption(f"配置标识：{cfg.config_id}")
        if cfg.mode == "live":
            st.caption(f"模型：{cfg.llm_model or '尚未配置'}")
        st.page_link("https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents", label="项目与设计文档", icon="↗️")
    if cfg.mode == "demo":
        st.info("离线演示使用自写虚构语料和确定性控制器，不调用 LLM，不代表真实模型表现，也不能作为正式预测提交。")
    else:
        st.info("真实模式会调用已配置的 API。密钥仅从本地环境读取；提交一次问题会产生一次运行。")
    if st.session_state.get("active_config_id") != cfg.config_id:
        st.session_state.pop("result", None)
        st.session_state.active_config_id = cfg.config_id
    with st.form("question_form"):
        question = st.text_area("输入问题", value="Where is the university attended by the architect of Lumen Observatory located?", height=105)
        submitted = st.form_submit_button("检索并回答", type="primary", disabled=st.session_state.get("busy", False))
    if submitted:
        if not question.strip():
            st.warning("请输入问题。")
        else:
            st.session_state.busy = True
            st.session_state.pop("result", None)
            try:
                cfg.check_live()
                store, search = runtime(cfg.model_dump_json())
                with st.status("正在检索并核对证据…", expanded=True) as status:
                    progress = st.empty()
                    def on_event(event):
                        label = event.get("event") or event.get("role") or "step"
                        progress.write(f"执行进度：{label}")
                    result = run_question(Question(id="web", question=question.strip()), cfg, store=store, search=search, on_event=on_event)
                    st.session_state.result = result.model_dump()
                    status.update(label=f"运行结束：{result.state.stop_reason}", state="complete" if result.state.candidate_answer else "error")
            except Exception as exc:
                st.error(f"无法开始运行：{exc}")
                st.code("rag-agent prepare --config configs/demo.yaml --source tests/fixtures/corpus.jsonl\nrag-agent index --config configs/demo.yaml --methods sparse")
            finally:
                st.session_state.busy = False
    saved = st.session_state.get("result")
    if not saved:
        st.caption("首次使用请先按 README 导入小语料并建立索引。")
        return
    prediction, state = saved["prediction"], saved["state"]
    st.divider()
    st.subheader("回答")
    st.caption("本次记录：" + ("离线合成演示" if saved["mode"] == "demo" else "真实 API 运行"))
    st.caption(prediction["question"])
    st.write(prediction["answer"] or "本次没有得到可提交的答案，请查看终止状态和工具记录。")
    answer_event = next((event for event in reversed(prediction["trajectory"]) if event.get("event") == "answer"), {})
    if answer_event.get("explanation"):
        st.caption(answer_event["explanation"])
    cols = st.columns(4)
    for col, label, value in zip(cols, ["执行轮数", "工具调用", "API tokens", "终止状态"], [state["steps"], prediction["tool_calls"], prediction["total_tokens"], state["stop_reason"]]):
        col.metric(label, value)
    st.caption("Token 数仅来自 API usage；演示模式的 0 表示未调用 API。")
    st.write("已选 skills：", ", ".join(state["selected_skills"]) or "本题无需加载 skill")
    tabs = st.tabs(["文档证据", "工具过程", "完整运行轨迹"])
    with tabs[0]:
        resolved = next((event for event in prediction["trajectory"] if event.get("event") == "evidence_resolution"), {})
        if resolved.get("citations"):
            st.caption("答案实际引用的原文范围（按模型请求中可见的文字恢复）")
            for citation in resolved["citations"]:
                st.write(f"{citation['evidence_id']} · {citation['doc_id']} · {citation['offset']}–{citation['end']}")
                st.text(citation["text"])
        if resolved.get("errors"):
            st.error("引用检查未通过：" + "; ".join(resolved["errors"]))
        for evidence in state["evidence"]:
            evidence_id = evidence.get("evidence_id")
            label = f"{evidence_id} · " if evidence_id else ""
            if evidence_id and evidence_id in state.get("selected_evidence_ids", []):
                label += "答案引用 · "
            label += f"{evidence['doc_id']} · 字符位置 {evidence['offset']}"
            with st.expander(label, expanded=True):
                st.text(evidence["text"])
                url = evidence.get("url", "")
                if url.startswith(("https://", "http://")):
                    st.link_button("来源 URL（仅用于溯源）", url)
        if not state["evidence"]:
            st.write("没有可展示的原文片段。")
    with tabs[1]:
        for item in prediction["trajectory"]:
            if item.get("role") == "assistant" and item.get("tool_calls"):
                calls = item["tool_calls"]
                if not isinstance(calls, list):
                    st.warning("服务返回了无效的工具调用结构。")
                    st.json(item)
                    continue
                for call in calls:
                    function = call.get("function") if isinstance(call, dict) else None
                    if not isinstance(function, dict):
                        st.warning("服务返回了无效的工具参数结构。")
                        st.json(call)
                        continue
                    st.write(f"调用 {function.get('name', '未知工具')}")
                    arguments = function.get("arguments", "")
                    st.code(arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False), language="json")
            elif item.get("role") == "tool":
                with st.expander(f"返回 · {item.get('name', item.get('tool_call_id', 'tool'))}"):
                    try:
                        st.json(json.loads(item["content"]))
                    except (ValueError, TypeError):
                        st.text(item["content"])
            elif item.get("event") in ("error", "skill_selected", "context_trim", "run_end"):
                st.json(item)
    with tabs[2]:
        st.caption("保存实际请求、响应、工具参数与结果；此处不要求或补写模型隐藏思维链。")
        st.json(prediction["trajectory"], expanded=False)
    st.download_button("下载本题运行记录", json.dumps(prediction, ensure_ascii=False) + "\n", file_name="demo_prediction.jsonl" if saved["mode"] == "demo" else "single_prediction.jsonl", mime="application/jsonl")


if __name__ == "__main__":
    main()
