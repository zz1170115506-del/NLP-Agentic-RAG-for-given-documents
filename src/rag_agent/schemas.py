"""Shared contracts. Reference answers are intentionally absent from Question."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Question(Record):
    id: StrictStr
    question: StrictStr


class Document(Record):
    doc_id: StrictStr
    text: str
    url: str = ""


class Chunk(Record):
    doc_id: str
    chunk_id: str
    offset: int = Field(ge=0)
    text: str
    url: str = ""


class SearchHit(Chunk):
    score: float
    method: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(Record):
    doc_id: str
    offset: int = Field(ge=0)
    text: str
    url: str = ""


class AgentState(Record):
    question: Question
    visited_documents: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    active_queries: list[str] = Field(default_factory=list)
    candidate_answer: str = ""
    selected_skills: list[str] = Field(default_factory=list)
    steps: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    stalled_searches: int = 0
    stop_reason: str = "running"


class Prediction(Record):
    id: StrictStr
    question: StrictStr
    answer: StrictStr
    trajectory: list[dict[str, Any]]
    tool_calls: int = Field(ge=0, strict=True)
    total_tokens: int = Field(ge=0, strict=True)


class RunResult(Record):
    prediction: Prediction
    state: AgentState
    mode: Literal["live", "demo"]
    eligible: bool = False
