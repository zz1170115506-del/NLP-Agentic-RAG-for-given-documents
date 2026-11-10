"""One registry supplies API schemas, dispatch, validation, and documentation."""
import json
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchInput(Input):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    method: Literal["sparse", "encoder", "instruction", "hybrid"] = "hybrid"


class OpenInput(Input):
    doc_id: str = Field(min_length=1)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=1600, ge=1, le=2400)


class FindInput(Input):
    doc_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=500)
    offset: int = Field(default=0, ge=0)
    max_matches: int = Field(default=3, ge=1, le=5)


class SkillInput(Input):
    name: str = Field(min_length=1, max_length=64)


class ToolOutput(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None


class PassageOutput(BaseModel):
    doc_id: str
    offset: int
    text: str
    url: str


class HitOutput(PassageOutput):
    chunk_id: str
    score: float
    method: str
    snippet: str
    metadata: dict[str, Any]


class SearchOutput(BaseModel):
    query: str
    results: list[HitOutput]


class OpenOutput(PassageOutput):
    next_offset: int | None
    document_length: int


class MatchOutput(PassageOutput):
    match_offset: int


class FindOutput(BaseModel):
    matches: list[MatchOutput]


class SkillOutput(BaseModel):
    name: str
    instructions: str


class ToolRegistry:
    outputs = {"search": SearchOutput, "open_document": OpenOutput, "find_in_document": FindOutput, "load_skill": SkillOutput}
    specs = {
        "search": (SearchInput, "Search only the supplied fixed document collection. This is the sole retrieval tool. Returns ranked exact passages with doc_id, score, offset, URL, method and metadata."),
        "open_document": (OpenInput, "Open a bounded page of one corpus document using Python Unicode-character offsets. Returns text and next_offset."),
        "find_in_document": (FindInput, "Find a literal phrase within one corpus document, case-insensitively, returning bounded exact windows and offsets."),
        "load_skill": (SkillInput, "Load one discovered procedure on demand. Use its returned instructions on subsequent actions; already active skills cannot be loaded twice."),
    }

    def __init__(self, store, search, skills, use_skills=True, method="hybrid", top_k=5):
        self.store, self.search, self.skills = store, search, skills
        self.use_skills = use_skills
        self.method, self.top_k = method, top_k

    def schemas(self):
        tools = []
        for name, (cls, description) in self.specs.items():
            if name == "load_skill" and not self.use_skills:
                continue
            parameters = cls.model_json_schema()
            if name == "search":
                parameters["properties"]["method"]["default"] = self.method
                parameters["properties"]["top_k"]["default"] = self.top_k
                if self.method != "hybrid":
                    parameters["properties"]["method"]["enum"] = [self.method]
            tools.append({"type": "function", "function": {"name": name, "description": description, "parameters": parameters}})
        return tools

    @classmethod
    def documentation(cls):
        return {name: {"description": description, "input": model.model_json_schema(), "envelope": ToolOutput.model_json_schema(), "data": cls.outputs[name].model_json_schema()}
                for name, (model, description) in cls.specs.items()}

    def execute(self, name: str, arguments: str | dict) -> dict:
        if name not in self.specs or (name == "load_skill" and not self.use_skills):
            return self.error("unknown_tool", "Use a registered tool name.")
        try:
            raw = json.loads(arguments) if isinstance(arguments, str) else arguments
            if name == "search" and isinstance(raw, dict):
                raw = {"method": self.method, "top_k": self.top_k, **raw}
            args = self.specs[name][0].model_validate(raw)
            if name == "search":
                if self.method != "hybrid" and args.method != self.method:
                    return self.error("invalid_arguments", f"This comparison configuration permits only method={self.method}")
                if not args.query.strip():
                    return self.error("invalid_arguments", "query cannot contain only whitespace")
                hits = self.search.search(args.query, args.top_k, args.method)
                results = []
                for hit in hits:
                    item = hit.model_dump() if hasattr(hit, "model_dump") else dict(hit)
                    item["text"] = item["text"][:1600]
                    item["snippet"] = item["text"]
                    results.append(item)
                data = {"query": args.query, "results": results}
            elif name == "load_skill":
                data = {"name": args.name, "instructions": self.skills.load(args.name)}
            else:
                doc = self.store.get(args.doc_id)
                if doc is None:
                    return self.error("not_found", f"No document with ID {args.doc_id} exists in the loaded corpus.")
                if args.offset > len(doc.text):
                    return self.error("out_of_range", f"offset exceeds document length {len(doc.text)}")
                if name == "open_document":
                    end = min(len(doc.text), args.offset + args.limit)
                    data = {"doc_id": doc.doc_id, "text": doc.text[args.offset:end], "offset": args.offset, "url": doc.url,
                            "next_offset": end if end < len(doc.text) else None, "document_length": len(doc.text)}
                else:
                    windows = []
                    for match in re.finditer(re.escape(args.text), doc.text[args.offset:], re.I):
                        position = args.offset + match.start()
                        start, end = max(0, position - 160), min(len(doc.text), args.offset + match.end() + 240)
                        windows.append({"doc_id": doc.doc_id, "offset": start, "match_offset": position, "text": doc.text[start:end], "url": doc.url})
                        if len(windows) >= args.max_matches:
                            break
                    data = {"matches": windows}
            data = self.outputs[name].model_validate(data).model_dump()
            return ToolOutput(ok=True, data=data).model_dump(exclude_none=True)
        except (ValidationError, json.JSONDecodeError, TypeError) as exc:
            return self.error("invalid_arguments", str(exc)[:1200])
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            return self.error("execution_error", str(exc)[:1200])

    @staticmethod
    def error(code: str, message: str):
        return ToolOutput(ok=False, error={"code": code, "message": message}).model_dump(exclude_none=True)
