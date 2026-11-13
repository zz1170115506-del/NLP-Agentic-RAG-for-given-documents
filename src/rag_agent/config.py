"""Validated application settings; credentials never enter serialized configs."""
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)
    mode: Literal["live", "demo"] = "live"
    agent_engine: Literal["baseline", "agent12"] = "baseline"
    store_path: str = "data/documents.sqlite"
    index_dir: str = "indexes/default"
    skills_dir: str = "skills"
    method: Literal["sparse", "encoder", "instruction", "hybrid"] = "hybrid"
    chunk_size: int = Field(default=900, ge=64, le=100000)
    chunk_overlap: int = Field(default=150, ge=0)
    batch_size: int = Field(default=16, ge=1, le=1024)
    top_k: int = Field(default=5, ge=1, le=20)
    rrf_k: int = Field(default=60, ge=1)
    # None retains the original min(top_k * 3, 60) depth independently per route.
    candidate_depth: int | None = Field(default=None, ge=1, le=1000)
    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    rerank_revision: str = "main"
    rerank_device: Literal["cpu", "mps", "cuda", "auto"] = "cpu"
    rerank_depth: int = Field(default=30, ge=1, le=3000)
    rerank_batch_size: int = Field(default=8, ge=1, le=256)
    rerank_max_length: int = Field(default=512, ge=8, le=512)
    rerank_max_windows: int = Field(default=4, ge=1, le=32)
    rerank_on_error: Literal["raise", "rrf"] = "raise"
    encoder_model: str = "intfloat/e5-small-v2"
    encoder_revision: str = "main"
    instruction_model: str = "Qwen/Qwen3-Embedding-0.6B"
    instruction_revision: str = "main"
    retrieval_instruction: str = "Given a factual question, retrieve passages that contain evidence to answer it."
    device: str = "cpu"
    max_seq_length: int = Field(default=512, ge=64)
    max_steps: int = Field(default=12, ge=1, le=100)
    max_tool_calls: int = Field(default=24, ge=1, le=200)
    max_output_tokens: int = Field(default=1024, ge=64, le=16384)
    max_total_tokens: int = Field(default=30000, ge=128)
    context_chars: int = Field(default=24000, ge=4000)
    timeout_seconds: float = Field(default=60, gt=0)
    run_timeout_seconds: float = Field(default=300, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    repeat_limit: int = Field(default=3, ge=1)
    use_skills: bool = True
    manage_context: bool = True
    iterative: bool = True
    graceful_finalization: bool = False
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = ""
    model_verified: bool = False
    model_verification_note: str = ""

    @model_validator(mode="after")
    def validate_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.agent_engine == "agent12" and self.context_chars < 6000:
            raise ValueError("Agent 1.2 requires context_chars >= 6000")
        return self

    @property
    def config_id(self) -> str:
        config = self.model_dump()
        # Existing baseline predictions and resume manifests predate this setting.
        if self.agent_engine == "baseline":
            config.pop("agent_engine")
        if not self.graceful_finalization:
            config.pop("graceful_finalization")
        return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides):
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        raw = yaml.safe_load(Path(path).read_text()) if path else {}
        raw = raw or {}
        for env, key in [("LLM_BASE_URL", "llm_base_url"), ("LLM_MODEL", "llm_model"), ("LLM_MODEL_VERIFICATION_NOTE", "model_verification_note")]:
            if os.getenv(env):
                raw[key] = os.environ[env]
        if os.getenv("LLM_MODEL_VERIFIED"):
            raw["model_verified"] = os.environ["LLM_MODEL_VERIFIED"].lower() == "true"
        raw.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**raw)

    def check_model_identity(self):
        if urlparse(self.llm_base_url).hostname == "api.deepseek.com":
            raise ValueError("As checked 2026-11-10, api.deepseek.com routes legacy V4-Flash to V4.1. Select a provider explicitly serving the original DeepSeek-V4-Flash; see docs/provider.md.")
        if re.search(r"gpt|claude|gemini|qwen|llama|v4[._-]1|deepseek-v[23]|deepseek-chat|deepseek-reasoner|latest|vision", self.llm_model, re.I):
            raise ValueError("This model identifier is not a pinned text DeepSeek-V4-Flash deployment; verify the original course backbone mapping.")
        if not self.llm_model or not self.model_verified or not self.model_verification_note:
            raise ValueError("Verify the provider's DeepSeek-V4-Flash model ID; set LLM_MODEL, LLM_MODEL_VERIFIED=true and LLM_MODEL_VERIFICATION_NOTE (documentation URL/date).")
        parsed = urlparse(self.llm_base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("LLM_BASE_URL must be an HTTPS API endpoint without credentials, query strings or fragments.")

    def check_live(self):
        if self.mode != "live":
            return
        self.check_model_identity()
        if not os.getenv("LLM_API_KEY"):
            raise ValueError("Set LLM_API_KEY in your local .env; demo never substitutes for live mode.")
