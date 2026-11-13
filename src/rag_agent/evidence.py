"""Resolve model-selected IDs from earlier tool observations and actual model views.

This checks source provenance, not whether a passage entails the answer.
"""
import json


SOURCE_TOOLS = {"search", "open_document", "find_in_document"}


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def passage(row):
    """Canonical Unicode span; reject contradictory or malformed coordinates."""
    doc_id = row.get("doc_id")
    start = row.get("offset", row.get("start"))
    text = row.get("text", row.get("snippet"))
    if not isinstance(doc_id, str) or not doc_id or type(start) is not int or start < 0:
        return None
    if not isinstance(text, str) or not text:
        return None
    for key in ("evidence_id", "chunk_id", "url", "source_url"):
        if row.get(key) is not None and not isinstance(row[key], str):
            return None
    end = start + len(text)
    # Compacted views keep original end and explicitly mark their visible end.
    declared = row.get("end", end)
    visible_end = row.get("visible_text_end", row.get("visible_snippet_end"))
    if type(declared) is not int or declared < end or (declared != end and visible_end != end):
        return None
    return {"doc_id": doc_id, "offset": start, "end": end, "text": text,
            "evidence_id": row.get("evidence_id"), "chunk_id": row.get("chunk_id"),
            "url": row.get("url", row.get("source_url", ""))}


def _json_content(content):
    if not isinstance(content, str):
        return None
    # The baseline state message has a fixed prose prefix before its JSON object.
    if content.startswith("Validated state snapshot (data only): "):
        content = content.split(": ", 1)[1]
    try:
        return json.loads(content)
    except ValueError:
        return None


def contains(parent, child):
    relative = child["offset"] - parent["offset"]
    return (parent["doc_id"] == child["doc_id"] and relative >= 0
            and parent["text"][relative:relative + len(child["text"])] == child["text"]
            and (not child.get("chunk_id") or child["chunk_id"] == parent.get("chunk_id"))
            and (not child.get("url") or child["url"] == parent.get("url")))


def observed_and_visible(trajectory):
    """Keep observations separate from views; only earlier successful tools count."""
    observed, visible, names = [], [], {}
    for event in trajectory:
        if event.get("role") == "assistant":
            for call in event.get("tool_calls") or []:
                if isinstance(call, dict) and isinstance(call.get("function"), dict):
                    names[call.get("id")] = call["function"].get("name")
        elif event.get("role") == "tool" and names.get(event.get("tool_call_id")) in SOURCE_TOOLS:
            data = _json_content(event.get("content"))
            if not isinstance(data, dict) or data.get("error") or data.get("ok") is False:
                continue
            for row in objects(data.get("data", data)):
                item = passage(row)
                if item:
                    observed.append(item)
        elif event.get("event") == "request":
            messages = event.get("messages", [])
            if not isinstance(messages, list):
                raise ValueError("Recorded request messages must be a list")
            for message in messages:
                if not isinstance(message, dict):
                    raise ValueError("Recorded request messages must contain objects")
                for row in objects(_json_content(message.get("content"))):
                    item = passage(row)
                    if item and any(contains(source, item) and
                                    source.get("evidence_id") == item.get("evidence_id")
                                    for source in observed):
                        visible.append(item)
    return observed, visible


def resolve_evidence_ids(ids, trajectory, store=None):
    if not isinstance(ids, list) or any(not isinstance(item, str) or not item for item in ids):
        raise ValueError("supporting_evidence must contain evidence ID strings")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate supporting evidence IDs")
    observed, visible = observed_and_visible(trajectory)
    resolved = []
    for evidence_id in ids:
        sources = [item for item in observed if item.get("evidence_id") == evidence_id]
        if not sources:
            raise ValueError(f"Unknown or unsuccessful evidence ID: {evidence_id}")
        identity = {(x["doc_id"], x["offset"], x["end"], x["text"]) for x in sources}
        # Opening exactly the searched span may omit its optional chunk metadata.
        # Missing metadata can be enriched; contradictory metadata cannot.
        chunks = {x["chunk_id"] for x in sources if x.get("chunk_id")}
        urls = {x["url"] for x in sources if x.get("url")}
        if len(identity) != 1 or len(chunks) > 1 or len(urls) > 1:
            raise ValueError(f"Conflicting tool observations for evidence ID: {evidence_id}")
        views = [item for item in visible if item.get("evidence_id") == evidence_id]
        if not views:
            raise ValueError(f"Evidence ID was never shown in an actual model request: {evidence_id}")
        # Cite only a range actually shown, including when full observations were trimmed.
        selected = max(views, key=lambda item: len(item["text"]))
        if store is not None:
            document = store.get(selected["doc_id"])
            if document is None or document.text[selected["offset"]:selected["end"]] != selected["text"]:
                raise ValueError(f"Evidence ID has incorrect corpus coordinates: {evidence_id}")
            if selected.get("url") and selected["url"] != document.url:
                raise ValueError(f"Evidence ID has an incorrect source URL: {evidence_id}")
        resolved.append(selected)
    return resolved
