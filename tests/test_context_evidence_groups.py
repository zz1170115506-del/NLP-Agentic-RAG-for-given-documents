"""Keep complementary observed intervals together under a real request budget.

All documents and questions below are synthetic. The assertions inspect the
whole model view (snapshot plus tool history), not a selector's ranking score.
"""
import copy
import json
from pathlib import Path

import pytest

from rag_agent.agent.context import build_context, message_size
from rag_agent.agent.loop import _update_state
from rag_agent.config import Settings
from rag_agent.evaluation.validate import _check_pairing
from rag_agent.evidence import observed_and_visible
from rag_agent.schemas import AgentState, Document, Question
from rag_agent.skills import SkillCatalog


ROOT = Path(__file__).resolve().parents[1]
FINAL_PROMPT = ("Finish now using only evidence already observed. Tools are disabled for this final turn. "
                "Return the required answer JSON with observed evidence IDs. "
                "If support is insufficient, return an empty answer; do not guess.")


class Store:
    def __init__(self, texts):
        self.documents = {key: Document(doc_id=key, text=text, url=f"https://example.invalid/{key}")
                          for key, text in texts.items()}

    def get(self, key):
        return self.documents.get(key)


def span(store, doc_id, offset, length):
    doc = store.get(doc_id)
    return {"doc_id": doc_id, "offset": offset, "text": doc.text[offset:offset + length],
            "url": doc.url, "chunk_id": f"{doc_id}:{offset}:{length}"}


def observe(state, store, name, arguments, rows, call_id):
    data = rows[0] if name == "open_document" else {"results": rows}
    result = {"ok": True, "data": copy.deepcopy(data)}
    _update_state(state, name, arguments, result, store)
    return [
        {"role": "assistant", "content": None, "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }]},
        {"role": "tool", "name": name, "tool_call_id": call_id,
         "content": json.dumps(result, ensure_ascii=False)},
    ]


def focused(state, store, item, call_id):
    return observe(state, store, "open_document",
                   {"doc_id": item["doc_id"], "offset": item["offset"], "limit": len(item["text"])},
                   [item], call_id)


def actual_view(messages, groups):
    trajectory = [message for group in groups for message in group]
    _, visible = observed_and_visible([*trajectory, {"event": "request", "messages": messages}])
    return visible


def covered(item, visible):
    """Exact text containment may cover a smaller original ID without inventing one."""
    for parent in visible:
        relative = item["offset"] - parent["offset"]
        if (parent["doc_id"] == item["doc_id"] and relative >= 0
                and parent["text"][relative:relative + len(item["text"])] == item["text"]):
            return True
    return False


def original_sources_only(visible, state, store):
    by_id = {item.evidence_id: item for item in state.evidence}
    assert visible
    for item in visible:
        original = by_id[item["evidence_id"]]
        assert (item["doc_id"], item["offset"], item["text"], item["url"], item["chunk_id"]) == (
            original.doc_id, original.offset, original.text, original.url, original.chunk_id)
        doc = store.get(item["doc_id"])
        assert doc.text[item["offset"]:item["offset"] + len(item["text"])] == item["text"]


@pytest.mark.parametrize("noise_length", [1100, 1500, 1900])
def test_final_request_cannot_keep_detail_while_losing_its_overlapping_counterfact(noise_length):
    question = ("Which registered tower location does the anchor record identify near a hospital founded "
                "after the survey with a reported bed count and lagoon access?")
    early = "The hospital was founded before the survey; later capacity figures are not its opening date. "
    early = early.ljust(900, "x")
    later = ("Tower location, hospital bed count, lagoon access and registered survey detail. " * 15)[:750]
    anchor = ("The anchor record identifies the registered tower location, hospital founding threshold, "
              "survey, reported bed count and lagoon access. ").ljust(400, "a")
    texts = {"hospital": early + later, "primary": anchor}
    texts.update({f"noise-{i}": ("Routine operations and maintenance summary. " * 60)[:noise_length]
                  for i in range(17)})
    store = Store(texts)
    state = AgentState(question=Question(id="synthetic-atomic-final", question=question))
    counterfact, detail = span(store, "hospital", 0, 900), span(store, "hospital", 750, 900)
    groups = [observe(state, store, "search", {"query": "hospital archive", "top_k": 1},
                      [counterfact], "search-counterfact")]
    for i in range(17):
        groups.append(focused(state, store, span(store, f"noise-{i}", 0, noise_length), f"open-noise-{i}"))
    groups.append(focused(state, store, detail, "open-detail"))
    primary = span(store, "primary", 0, len(anchor))
    groups.append(focused(state, store, primary, "open-primary"))
    pair_ids = {item.evidence_id for item in state.evidence if item.doc_id == "hospital"}
    original_state, original_groups = state.model_dump(), copy.deepcopy(groups)
    settings = Settings(mode="demo", use_skills=False, context_chars=23600, max_total_tokens=30000)

    messages, info = build_context(state, SkillCatalog(str(ROOT / "skills")), groups, settings)
    final_messages = [*messages, {"role": "user", "content": FINAL_PROMPT}]
    visible = actual_view(final_messages, groups)

    assert covered(primary, visible), "The independent primary anchor must remain usable."
    pair_coverage = (covered(counterfact, visible), covered(detail, visible))
    assert pair_coverage in {(True, True), (False, False)}, \
        "Showing only one side can turn a counterexample into apparent supporting evidence."
    if not any(pair_coverage):
        assert any(set(group["member_ids"]) == pair_ids and group["reason"] in {
            "budget", "exceeds_context_capacity"} for group in info["omitted_evidence_groups"])
    assert message_size(messages) <= 23600
    assert message_size(final_messages) <= 24000
    assert not _check_pairing(final_messages, "atomic final request")[0]
    original_sources_only(visible, state, store)
    assert state.model_dump() == original_state
    assert groups == original_groups


def test_oversized_local_chain_is_omitted_without_binding_distant_or_other_documents():
    # Ten overlapping full observations cannot all fit in 23,600 characters.
    # A remote range in the same document, and another document at offset zero,
    # remain separate units and must not be discarded with that chain.
    chain_text = ("Connected archive records. " * 600)[:13200]
    remote_text = "Separate appendix: the independent location anchor remains valid. " + "r" * 420
    same_document = chain_text + "gap" * 400 + remote_text
    other_text = "Another document confirms the independent anchor. " + "o" * 350
    store = Store({"large-document": same_document, "other-document": other_text})
    state = AgentState(question=Question(id="synthetic-oversize-chain",
                                        question="Which independent anchor confirms the location?"))
    groups = []
    chain = [span(store, "large-document", offset, 2400) for offset in range(0, 12000, 1200)]
    for index, item in enumerate(chain):
        groups.append(focused(state, store, item, f"open-chain-{index}"))
    chain_ids = {item.evidence_id for item in state.evidence}
    remote = span(store, "large-document", len(chain_text) + 1200, len(remote_text))
    other = span(store, "other-document", 0, len(other_text))
    groups.extend([focused(state, store, remote, "open-remote"),
                   focused(state, store, other, "open-other")])
    independent_ids = {item.evidence_id for item in state.evidence} - chain_ids
    settings = Settings(mode="demo", use_skills=False, context_chars=23600, max_total_tokens=30000)

    messages, info = build_context(state, SkillCatalog(str(ROOT / "skills")), groups, settings)
    visible = actual_view(messages, groups)

    assert not any(covered(item, visible) for item in chain)
    assert covered(remote, visible) and covered(other, visible)
    omitted = [group for group in info["omitted_evidence_groups"] if set(group["member_ids"]) == chain_ids]
    assert len(omitted) == 1
    assert omitted[0]["reason"] == "exceeds_context_capacity"
    assert omitted[0]["doc_id"] == "large-document"
    assert omitted[0]["offset"] == 0 and omitted[0]["end"] == 13200
    assert not independent_ids.intersection(omitted[0]["member_ids"])
    assert message_size(messages) <= 23600
    assert not _check_pairing(messages, "oversize omission request")[0]
    original_sources_only(visible, state, store)


def test_contained_inspection_cannot_replace_the_larger_source_and_lose_its_tail():
    opening = "The river station was assessed by a regional survey. "
    unique_tail = "The terminal note identifies the controlling research grant."
    document = opening.ljust(1640, "x") + unique_tail
    anchor_text = "Independent anchor: this record belongs to the river station."
    store = Store({"research": document, "anchor": anchor_text})
    state = AgentState(question=Question(id="synthetic-contained-tail",
                                        question="Which research grant controlled the river station survey?"))
    complete = span(store, "research", 0, len(document))
    contained = span(store, "research", 300, 900)
    groups = [observe(state, store, "search", {"query": "river research grant", "top_k": 1},
                      [complete], "search-complete")]
    groups.append(focused(state, store, contained, "inspect-contained"))
    groups.append(focused(state, store, span(store, "anchor", 0, len(anchor_text)), "inspect-anchor"))

    messages, _ = build_context(state, SkillCatalog(str(ROOT / "skills")), groups,
                                Settings(mode="demo", use_skills=False, context_chars=6000))
    visible = actual_view(messages, groups)

    assert covered(complete, visible)
    assert covered(contained, visible)
    assert any(unique_tail in item["text"] for item in visible)
    original_sources_only(visible, state, store)
    assert message_size(messages) <= 6000
    assert not _check_pairing(messages, "contained source request")[0]
