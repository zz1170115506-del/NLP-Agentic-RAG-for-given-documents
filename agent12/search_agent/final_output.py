"""Read one complete model-authored answer object without changing raw output."""
import json


def parse_final_object(content):
    if not isinstance(content, str):
        raise ValueError("Final output must be a string containing an answer JSON object")
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    try:
        value = json.loads(text)
    except ValueError:
        # Never salvage a broken structural response by extracting a nested object.
        if text.startswith(("{", "[")):
            raise ValueError("Final JSON is incomplete or malformed") from None
        decoder, found, position = json.JSONDecoder(), [], 0
        while position < len(text):
            start = text.find("{", position)
            if start < 0:
                break
            try:
                value, end = decoder.raw_decode(text, start)
            except ValueError:
                position = start + 1
            else:
                found.append(value)
                position = end
        if len(found) != 1:
            raise ValueError("Final response must contain exactly one unambiguous complete JSON object") from None
        value = found[0]
    if not isinstance(value, dict) or not isinstance(value.get("answer"), str):
        raise ValueError("Final JSON must contain a string answer")
    return value
