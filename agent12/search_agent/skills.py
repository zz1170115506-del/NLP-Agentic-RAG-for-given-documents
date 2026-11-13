"""Original runtime skills: advertise metadata, load instructions only on demand."""
from __future__ import annotations

from pathlib import Path


class SkillRegistry:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self._skills: dict[str, dict] = {}
        if not self.directory.exists():
            return
        for path in sorted(self.directory.glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            metadata, body = self._parse(text)
            name = metadata.get("name", "")
            if not name or name != path.parent.name:
                raise ValueError("Skill name must match its directory: " + str(path))
            if not metadata.get("description"):
                raise ValueError("Skill description required: " + str(path))
            if name in self._skills:
                raise ValueError("Duplicate skill: " + name)
            # Keep the path and metadata only. The body is re-read at load time.
            self._skills[name] = {"name": name, "description": metadata["description"],
                                  "path": path}

    @staticmethod
    def _parse(text: str) -> tuple[dict, str]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("SKILL.md must start with YAML front matter.")
        try:
            ending = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        except StopIteration as exc:
            raise ValueError("Unclosed skill front matter.") from exc
        meta = {}
        for line in lines[1:ending]:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition(":")
            if separator:
                meta[key.strip()] = value.strip().strip("\"'")
        return meta, "\n".join(lines[ending + 1:]).strip()

    def catalog(self) -> list[dict]:
        return [{"name": entry["name"], "description": entry["description"]}
                for entry in self._skills.values()]

    def load(self, name: str) -> dict:
        if name not in self._skills:
            raise ValueError("Unknown skill. Choose a name from the advertised catalog.")
        path = self._skills[name]["path"]
        text = path.read_text(encoding="utf-8")
        meta, body = self._parse(text)
        if meta.get("name") != name or not body:
            raise ValueError("Invalid skill contents.")
        return {"name": name, "description": meta["description"],
                "instructions": body, "path": str(path)}
