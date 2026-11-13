"""Load local configuration without exposing credentials to the browser."""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

from .agent import AgentConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def read_dotenv(path: str | Path | None = None) -> dict[str, str]:
    """Read literal KEY=value entries. Never execute shell substitutions."""
    target = Path(path) if path else PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if not target.is_file():
        return values
    for line in target.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load_config(**overrides) -> AgentConfig:
    env = {**read_dotenv(), **os.environ}
    mapping = {
        "api_key": ("DEEPSEEK_API_KEY", str),
        "base_url": ("DEEPSEEK_BASE_URL", str),
        "model": ("DEEPSEEK_MODEL", str),
        "max_steps": ("AGENT_MAX_STEPS", int),
        "max_tool_calls": ("AGENT_MAX_TOOL_CALLS", int),
        "max_tokens": ("AGENT_MAX_TOKENS", int),
        "context_chars": ("AGENT_CONTEXT_CHARS", int),
        "top_k": ("SEARCH_TOP_K", int),
        "search_method": ("SEARCH_METHOD", str),
        "strict_model_identity": ("LLM_STRICT_MODEL_IDENTITY", lambda v: v.lower() in ("1", "true", "yes")),
    }
    values = {key: cast(env[name]) for key, (name, cast) in mapping.items() if env.get(name)}
    values["skills_dir"] = PROJECT_ROOT / "skills"
    values.setdefault("strict_model_identity", True)
    # Generic names support the service selected from the assignment's providers.
    for field_name, variable in (("api_key", "LLM_API_KEY"), ("base_url", "LLM_BASE_URL"), ("model", "LLM_MODEL")):
        if env.get(variable):
            values[field_name] = env[variable]
    allowed = {field.name for field in fields(AgentConfig)}
    unknown = set(overrides) - allowed
    if unknown:
        raise ValueError(f"Unknown agent settings: {', '.join(sorted(unknown))}")
    values.update({key: value for key, value in overrides.items() if value is not None})
    if values.get("demo"):
        values["provider"] = "demo"
    return AgentConfig(**values)
