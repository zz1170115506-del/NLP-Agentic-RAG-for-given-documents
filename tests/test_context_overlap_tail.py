"""A mostly overlapping passage can still contain the only answer-bearing tail."""
import copy
import json
from pathlib import Path

from rag_agent.agent.context import build_context, message_size
from rag_agent.config import Settings
from rag_agent.evidence import observed_and_visible
from rag_agent.schemas import AgentState, Evidence, Question
from rag_agent.skills import SkillCatalog


ROOT = Path(__file__).resolve().parents[1]


def tool_group(name, call_id, arguments, data):
    return [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": call_id, "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments)}}]},
        {"role": "tool", "tool_call_id": call_id, "name": name,
         "content": json.dumps({"ok": True, "data": data})},
    ]


def test_partial_overlap_keeps_unique_answer_tail_when_it_fits():
    document = "x" * 950 + "Aurora received the copper award." + "x" * 50
    anchor = Evidence(doc_id="synthetic-anchor", offset=0, text=document[:900],
                      url="synthetic://anchor", evidence_id="E1")
    tail = Evidence(doc_id=anchor.doc_id, offset=100, text=document[100:1000],
                    url=anchor.url, evidence_id="E2")
    noise = [Evidence(doc_id=f"synthetic-noise-{i}", offset=0, text="z" * 900,
                      url=f"synthetic://noise/{i}", evidence_id=f"E{i + 3}") for i in range(19)]
    state = AgentState(question=Question(id="synthetic-overlap", question="Which award did Aurora receive?"),
                       evidence=[anchor, tail, *noise])
    hits = [{**item.model_dump(), "snippet": item.text, "score": 1.0, "method": "sparse",
             "metadata": {}} for item in [tail, *noise]]
    groups = [tool_group("open_document", "open-anchor", {"doc_id": anchor.doc_id, "offset": 0},
                         anchor.model_dump()),
              tool_group("search", "search-tail", {"query": "Aurora award", "top_k": 20},
                         {"query": "Aurora award", "results": hits})]
    settings = Settings(mode="demo", use_skills=False, context_chars=24000)
    # The latest real-shaped parallel-result group cannot fit wholesale. Its
    # observed ranges must therefore be delivered through the managed snapshot.
    assert message_size(groups[-1]) > settings.context_chars
    state_before, groups_before = state.model_dump(), copy.deepcopy(groups)

    messages, _ = build_context(state, SkillCatalog(str(ROOT / "skills")), groups, settings)
    audit = [message for group in groups for message in group]
    _, visible = observed_and_visible([*audit, {"event": "request", "messages": messages}])

    # [0,900) and [100,1000) overlap by 800/900, but only the latter includes
    # the answer in [950,983). Range overlap must not erase those distinct facts.
    assert any(item["evidence_id"] == "E2" and item["text"] == tail.text
               and item["offset"] == tail.offset for item in visible)
    assert "copper award" in "\n".join(message.get("content") or "" for message in messages)
    assert message_size(messages) <= settings.context_chars
    assert state.model_dump() == state_before
    assert groups == groups_before
