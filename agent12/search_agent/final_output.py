"""Read one complete model-authored answer object without changing raw output."""
import json
import re

_LEGAL_SUFFIX = re.compile(r"[ ]+(ltd|limited|inc|llc|corp|corporation|co)[.]?$", re.I)
_UNIT_SPACE = re.compile(r"(?<=[0-9])[ ]+(kg|km|cm|mm|ft|mi|tb|gb|mb|kb|%)(?=[ ]|$|[),.;])", re.I)
_YEAR_PREFIX = re.compile(r"^((?:19|20)[0-9]{2})[ ]+(.+)$")
_PAREN_ALIAS = re.compile(r"\s*\(([^()]*)\)\s*$")
_GENERIC_TAIL = re.compile(r"[ ]+(expedition)$", re.I)
_MONTHS = {name.lower(): i for i, name in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}


def _strip_legal(text):
    return _LEGAL_SUFFIX.sub("", text)


def _normalise_words(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def canonicalize_answer(answer):
    """Conservative surface normalization; never changes the fact being stated."""
    text = " ".join(str(answer).strip().split())
    # Drop a trailing parenthetical only when it merely repeats the name.
    match = _PAREN_ALIAS.search(text)
    if match:
        base, alias = text[:match.start()], match.group(1)
        base_clean = _strip_legal(base)
        if _normalise_words(alias) and (
            _normalise_words(alias) == _normalise_words(base_clean)
            or _normalise_words(alias) in _normalise_words(base_clean)
        ):
            text = base_clean
    text = _strip_legal(text)
    text = _UNIT_SPACE.sub(lambda match: match.group(1), text)
    text = _GENERIC_TAIL.sub("", text)
    match = _YEAR_PREFIX.match(text)
    if match and len(match.group(2).split()) <= 6:
        text = f"{match.group(2)} {match.group(1)}"
    return " ".join(text.split())


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
    value["answer"] = canonicalize_answer(value["answer"])
    return value
