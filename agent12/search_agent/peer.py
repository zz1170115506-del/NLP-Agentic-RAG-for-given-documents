"""Connect the supplied section 1.1 project without modifying its source.

Retrieval settings resolve against the peer project, independently of CWD and
the agent's LLM credentials. Ranking remains entirely in the peer SearchService.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path


def import_peer(project_dir):
    project = Path(project_dir).expanduser().resolve()
    source = project / "src"
    expected = source / "rag_agent" / "peer_backend.py"
    if not expected.is_file():
        raise ValueError(f"Not a peer project root: {project}; expected src/rag_agent/peer_backend.py")
    loaded = sys.modules.get("rag_agent")
    if loaded and Path(loaded.__file__).resolve().parent != source / "rag_agent":
        raise ValueError("A different rag_agent project is already loaded. Start a new Python process to switch versions.")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        settings_class = importlib.import_module("rag_agent.config").Settings
        backend_class = importlib.import_module("rag_agent.peer_backend").PeerBackend
    except ImportError as exc:
        raise ImportError("Install requirements-peer.txt for the peer integration (pydantic, PyYAML, numpy).") from exc
    return project, settings_class, backend_class


def load_peer_settings(project_dir, config_path, method=None):
    project, settings_class, backend_class = import_peer(project_dir)
    config = Path(config_path).expanduser()
    if not config.is_absolute():
        config = project / config
    config = config.resolve()
    if config.suffix.lower() == ".json":
        raw = json.loads(config.read_text(encoding="utf-8-sig"))
    else:
        import yaml
        raw = yaml.safe_load(config.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("Peer configuration must be an object")
    raw = dict(raw)
    if method is not None:
        raw["method"] = method
    defaults = settings_class()
    for name in ("store_path", "index_dir", "skills_dir"):
        path = Path(raw.get(name, getattr(defaults, name))).expanduser()
        raw[name] = str((path if path.is_absolute() else project / path).resolve())
    # No peer Settings.load(): its dotenv/CWD behavior must not alter agent API settings.
    return settings_class(**raw), backend_class, config


class PeerRetrievalBackend:
    """Real peer ranking plus bounded source inspection for the agent."""
    def __init__(self, backend, settings, *, project_dir, config_path, max_matches=8,
                 page_chars=16384, max_scan_chars=2_000_000):
        if type(max_matches) is not int or max_matches < 1:
            raise ValueError("max_matches must be a positive integer")
        if type(page_chars) is not int or page_chars < 1 or max_scan_chars < page_chars:
            raise ValueError("Invalid source scan limits")
        self.backend, self.settings = backend, settings
        self.project_dir, self.config_path = str(project_dir), str(config_path)
        self.max_matches, self.page_chars, self.max_scan_chars = max_matches, page_chars, max_scan_chars
        self.closed = False
        store = backend._search.store
        self.fingerprint = store.fingerprint
        self.source = store.metadata.get("source", {})
        self.is_fixture = bool(self.source.get("synthetic")) or str(self.source.get("type", "")).startswith("synthetic")

    def describe(self):
        return {"kind": "peer-1.1", "project_dir": self.project_dir, "config_path": self.config_path,
                "method": self.settings.method, "store_path": self.settings.store_path,
                "index_dir": self.settings.index_dir, "corpus_fingerprint": self.fingerprint,
                "source": self.source, "synthetic": self.is_fixture,
                "top_k_unit": "passages", "find_max_matches": self.max_matches,
                "find_max_scan_chars": self.max_scan_chars}

    def search(self, query: str, top_k: int = 5):
        if self.closed:
            raise RuntimeError("Peer backend is closed")
        return self.backend.search(query, top_k=top_k)

    def open_document(self, doc_id: str, start: int = 0, length: int = 6000):
        if self.closed:
            raise RuntimeError("Peer backend is closed")
        row = self.backend.open_document(doc_id, start=start, length=length)
        if row.get("doc_id") != doc_id or row.get("start") != start or row.get("end") != start + len(row.get("text", "")):
            raise ValueError("Peer source tool returned inconsistent document coordinates")
        return row

    def find_in_document(self, doc_id: str, query: str, window: int = 250):
        """Scan via the public source API; bound matches before materializing them.

        Page overlap preserves literal matches across page boundaries. Internal
        page reads belong to this one tool call, not additional agent actions.
        """
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError("query must contain 1-2000 characters")
        if type(window) is not int or not 0 <= window <= 2000:
            raise ValueError("window must be between 0 and 2000")
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        matches, cursor, carry, next_allowed = [], 0, "", 0
        result = {"doc_id": doc_id, "query": query, "matches": matches,
                  "truncated": False, "scan_truncated": False, "next_start": None}
        while cursor < self.max_scan_chars:
            length = min(self.page_chars, self.max_scan_chars - cursor)
            page = self.open_document(doc_id, start=cursor, length=length)
            result["source_url"] = page.get("source_url", "")
            text = page["text"]
            combined, base = carry + text, cursor - len(carry)
            for match in pattern.finditer(combined, max(0, next_allowed-base)):
                start, end = base + match.start(), base + match.end()
                if start < next_allowed:
                    continue
                if len(matches) == self.max_matches:
                    result.update(truncated=True, next_start=start)
                    return result
                excerpt = self.open_document(doc_id, start=max(0, start-window), length=end-max(0, start-window)+window)
                matches.append({**excerpt, "match_start": start, "match_end": end})
                next_allowed = end
            cursor += len(text)
            if len(text) < length:
                result["scanned_chars"] = cursor
                return result
            carry = combined[-(len(query)-1):] if len(query) > 1 else ""
        result.update(scan_truncated=True, next_start=max(0, cursor-len(carry)), scanned_chars=cursor)
        return result

    def close(self):
        if not self.closed:
            self.closed = True
            self.backend.close()


def load_peer_backend(project_dir, config_path, *, method=None, max_matches=8):
    settings, backend_class, config = load_peer_settings(project_dir, config_path, method)
    backend = backend_class(settings)
    try:
        return PeerRetrievalBackend(backend, settings, project_dir=Path(project_dir).resolve(),
                                    config_path=config, max_matches=max_matches)
    except Exception:
        backend.close()
        raise
