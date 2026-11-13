"""Explicit synthetic fixtures for independent section 1.2 integration tests.

FixtureBackend is not a section 1.1 retrieval implementation. ScenarioClient is
not an LLM. A real client can use the same fixture documents to test the actual
API before a teammate supplies the final retriever.
"""
from __future__ import annotations

import json
import re


QUESTION = "Which researcher founded Cedarwatch Observatory, taught at Alder College, and received the Lyra Medal in 2018?"
DOCUMENTS = {
    "register": "SYNTHETIC TEST DOCUMENT. Cedarwatch Observatory was founded by researcher Elara Venn in 2009. The register does not record her employment or awards; those facts require separate sources.",
    "college": "SYNTHETIC TEST DOCUMENT. Elara Venn taught astronomy at Alder College from 2011 to 2020. Elara Wren taught mathematics there and is a different person.",
    "medal": "SYNTHETIC TEST DOCUMENT. The Lyra Medal was awarded to Elara Venn in 2018 for her astronomy research. The 2017 recipient was Nolan Reed.",
    "long-register": "SYNTHETIC TEST DOCUMENT. The Cedarwatch register records that researcher Elara Venn founded the observatory. " + "Historical catalog entry with no additional identifying facts. " * 230,
}


class FixtureBackend:
    """Controlled responses, explicitly for tests, with separate source documents."""
    is_fixture = True

    def __init__(self):
        self.calls = []

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        self.calls.append({"name": "search", "query": query})
        lowered = query.casefold()
        if "biographical ledger" in lowered:
            ids = []
        elif "elara venn" in lowered:
            ids = []
            if any(word in lowered for word in ("college", "taught", "employment", "alder")):
                ids.append("college")
            if any(word in lowered for word in ("medal", "award", "lyra", "2018")):
                ids.append("medal")
            ids = ids or ["register", "college", "medal"]
        elif "cedarwatch" in lowered:
            ids = ["register"]
        else:
            ids = []
        return [{"doc_id": name, "score": 1.0 / (rank + 1), "snippet": DOCUMENTS[name],
                 "source_url": "https://example.invalid/agent12/" + name,
                 "start": 0, "end": len(DOCUMENTS[name])}
                for rank, name in enumerate(ids[:top_k])]

    def open_document(self, doc_id: str, start: int = 0, length: int = 6000) -> dict:
        self.calls.append({"name": "open_document", "doc_id": doc_id})
        text = DOCUMENTS[doc_id]
        start = min(start, len(text))
        end = min(len(text), start + length)
        return {"doc_id": doc_id, "text": text[start:end], "source_url": "https://example.invalid/agent12/" + doc_id,
                "start": start, "end": end, "total_length": len(text), "has_more": end < len(text)}

    def find_in_document(self, doc_id: str, query: str, window: int = 250) -> dict:
        text = DOCUMENTS[doc_id]
        matches = []
        for match in list(re.finditer(re.escape(query), text, flags=re.IGNORECASE))[:20]:
            start, end = max(0, match.start() - window), min(len(text), match.end() + window)
            matches.append({"text": text[start:end], "start": start, "end": end})
        return {"doc_id": doc_id, "source_url": "https://example.invalid/agent12/" + doc_id, "matches": matches}


class ScenarioClient:
    """A mock decision policy for testing the real loop, not model evaluation.

    Later queries use a candidate extracted from returned evidence. A changed
    fixture candidate changes the generated query; no reference answers are read.
    """
    def __init__(self, scenario="multi-hop"):
        if scenario not in ("multi-hop", "recovery", "context"):
            raise ValueError("Unknown offline scenario")
        self.scenario = scenario
        self.requests = []

    def complete(self, messages, tools, *, allow_tools=True, **kwargs):
        self.requests.append(messages)
        state = json.loads(next(message["content"] for message in messages if message.get("name") == "agent_state"))
        evidence = state.get("evidence", [])
        queries = state.get("queries", [])
        if self.scenario == "context":
            if not evidence and allow_tools:
                return self._call("open_document", {"doc_id": "long-register", "length": 12000})
        elif not queries and allow_tools:
            query = "Cedarwatch biographical ledger" if self.scenario == "recovery" else "Cedarwatch Observatory founder"
            return self._call("search", {"query": query}, conditions=["observatory founder", "Alder College employment", "Lyra Medal in 2018"])
        elif queries and not queries[-1].get("hits") and not evidence and allow_tools:
            return self._call("search", {"query": "Cedarwatch founding register"}, next_check="Reformulate after an empty result")
        joined = "\n".join(entry.get("text", "") for entry in evidence)
        found = re.search(r"researcher ([A-Z][a-z]+ [A-Z][a-z]+)", joined)
        candidate = found.group(1) if found else None
        docs = {entry["doc_id"] for entry in evidence}
        if candidate and self.scenario != "context" and allow_tools:
            if "college" not in docs:
                return self._call("search", {"query": candidate + " Alder College employment"}, candidate=candidate,
                                  next_check="Verify employment using the newly observed name")
            if "medal" not in docs:
                return self._call("search", {"query": candidate + " Lyra Medal 2018"}, candidate=candidate,
                                  next_check="Verify the award and year")
        content = {"answer": candidate or "", "supporting_evidence": [entry["evidence_id"] for entry in evidence],
                   "unresolved_conditions": [] if candidate else ["No candidate found in fixture evidence"]}
        return {"demo": True, "choices": [{"message": {"role": "assistant", "content": json.dumps(content)}, "finish_reason": "stop"}]}

    def _call(self, name, arguments, **progress):
        return {"demo": True, "choices": [{"message": {"role": "assistant", "content": json.dumps(progress),
                 "tool_calls": [{"id": "fixture_call", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]},
                 "finish_reason": "tool_calls"}]}
