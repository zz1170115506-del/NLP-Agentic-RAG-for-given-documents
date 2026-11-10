"""Progressive skill discovery: only YAML metadata is read until selection."""
from pathlib import Path
import re
import yaml


class SkillCatalog:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.metadata: dict[str, dict[str, str]] = {}
        self.loaded: dict[str, str] = {}
        for path in sorted(self.root.glob("*/SKILL.md")):
            with path.open(encoding="utf-8") as stream:
                if stream.readline().strip() != "---":
                    raise ValueError(f"Missing YAML frontmatter: {path.name}")
                lines = []
                for line in stream:
                    if line.strip() == "---":
                        break
                    lines.append(line)
                    if len(lines) > 100:
                        raise ValueError("Skill metadata is too long")
                else:
                    raise ValueError("Unterminated skill frontmatter")
            meta = yaml.safe_load("".join(lines))
            if not isinstance(meta, dict):
                raise ValueError("Skill metadata must be a mapping")
            name, description = meta.get("name"), meta.get("description")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64 or name != path.parent.name:
                raise ValueError("Skill name must match its directory and the Agent Skills specification")
            if not isinstance(description, str) or not 0 < len(description) <= 1024:
                raise ValueError("Skill description must have 1–1024 characters")
            self.metadata[name] = {"name": name, "description": description}

    def load(self, name: str) -> str:
        if name not in self.metadata:
            raise ValueError(f"Unknown skill: {name}")
        if name in self.loaded:
            raise ValueError(f"Skill already active: {name}")
        path = (self.root / name / "SKILL.md").resolve()
        if self.root not in path.parents:
            raise ValueError("Skill path outside configured directory")
        text = path.read_text(encoding="utf-8")
        body = text.split("---", 2)[2].strip()
        if not body or len(body) > 12000:
            raise ValueError("Skill body must contain 1–12000 characters")
        self.loaded[name] = body
        return body

    def select(self, question: str, stalled_searches: int = 0) -> str | None:
        """Small deterministic routing policy; the LLM can additionally call load_skill."""
        if stalled_searches and "search-recovery" not in self.loaded:
            name = "search-recovery"
        elif re.search(r"\b(and|whose|who.*(?:studied|designed)|where.*(?:designer|architect)|both|before|after)\b|同时|并且|哪所|设计者", question, re.I) and "multi-clue-decomposition" not in self.loaded:
            name = "multi-clue-decomposition"
        else:
            return None
        return name if name in self.metadata else None
