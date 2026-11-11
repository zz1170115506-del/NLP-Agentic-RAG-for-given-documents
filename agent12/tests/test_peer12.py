"""Boundary regressions and real supplied-1.1 BM25 integration; no API calls."""
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from search_agent.agent import SearchAgent
from search_agent.agent12 import main
from search_agent.peer import PeerRetrievalBackend, load_peer_backend, load_peer_settings
from search_agent.ports import FunctionBackend
from test_agent12 import QueueClient, config, create_agent, response

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PEER = ROOT.parent
if not (DEFAULT_PEER / "src/rag_agent/peer_backend.py").is_file():
    DEFAULT_PEER = ROOT.parent / "peer_review/20261111/NLP-Agentic-RAG-for-given-documents-main"
PEER = Path(os.environ.get("AGENT12_PEER_PROJECT", DEFAULT_PEER))


class Source:
    def __init__(self, text):
        self.text, self.reads, self.closes = text, [], 0
        self._search = SimpleNamespace(store=SimpleNamespace(fingerprint="test", metadata={"source": {}}))

    def open_document(self, doc_id, start=0, length=6000):
        self.reads.append((start, length))
        text = self.text[start:start+length]
        return {"doc_id": doc_id, "text": text, "start": start, "end": start+len(text), "source_url": "source"}

    def close(self):
        self.closes += 1


def bounded(source, **kwargs):
    return PeerRetrievalBackend(source, SimpleNamespace(method="sparse", store_path="test", index_dir="test"),
                                project_dir="test", config_path="test", **kwargs)


class SourceBoundaryTests(unittest.TestCase):
    def test_literal_unicode_phrase_crosses_pages_with_original_offsets(self):
        text = "1234567甲乙丙 padding 甲乙丙 end"
        result = bounded(Source(text), page_chars=8).find_in_document("d", "甲乙丙", window=2)
        self.assertEqual([row["match_start"] for row in result["matches"]], [7, 19])
        for row in result["matches"]:
            self.assertEqual(row["text"], text[row["start"]:row["end"]])
        self.assertFalse(result["truncated"])

    def test_adjacent_repeated_pattern_is_not_lost_at_page_boundaries(self):
        text = "a" * 30
        result = bounded(Source(text), page_chars=4, max_matches=20).find_in_document("d", "aaa", window=0)
        expected = [match.start() for match in re.finditer("aaa", text)]
        self.assertEqual([row["match_start"] for row in result["matches"]], expected)

    def test_query_longer_than_page_and_case_insensitivity(self):
        result = bounded(Source("x AbCdEfGh y"), page_chars=3).find_in_document("d", "abcdefgh", window=0)
        self.assertEqual([row["text"] for row in result["matches"]], ["AbCdEfGh"])

    def test_many_matches_stop_before_materializing_whole_document(self):
        source = Source("marker " * 50000)
        result = bounded(source, page_chars=64, max_matches=3).find_in_document("d", "marker", window=1)
        self.assertEqual(len(result["matches"]), 3)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_start"], 21)
        self.assertLessEqual(len(source.reads), 4)

    def test_scan_cap_distinguishes_unscanned_tail_from_no_match(self):
        result = bounded(Source("x" * 200 + "needle"), page_chars=16, max_scan_chars=64).find_in_document("d", "needle")
        self.assertEqual(result["matches"], [])
        self.assertTrue(result["scan_truncated"])
        self.assertEqual(result["next_start"], 59)

    def test_no_match_and_empty_source_return_no_evidence(self):
        for text in ("", "no matching word"):
            result = bounded(Source(text), page_chars=8).find_in_document("d", "needle")
            self.assertEqual(result["matches"], [])
            self.assertFalse(result["scan_truncated"])
            self.assertIsNone(result["next_start"])

    def test_close_is_idempotent_and_blocks_future_reads(self):
        source = Source("text")
        backend = FunctionBackend(lambda query, top_k=5: [], open_document_fn=bounded(source).open_document,
                                  close_fn=source.close)
        backend.close()
        backend.close()
        self.assertEqual(source.closes, 1)
        with self.assertRaises(RuntimeError):
            backend.open_document("d")

    def test_inconsistent_source_coordinates_are_rejected(self):
        source = Source("text")
        source.open_document = lambda *a, **k: {"doc_id": "d", "text": "text", "start": 0, "end": 99}
        with self.assertRaisesRegex(ValueError, "coordinates"):
            bounded(source).open_document("d")


class ProgressTests(unittest.TestCase):
    def test_large_read_keeps_compact_assistant_tool_pair_and_exact_raw_text(self):
        text = "Founder is Candidate. " + "x" * 11978
        client = QueueClient(response(call=("open_document", {"doc_id": "d", "length": 12000})),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1"]})))
        result = create_agent(lambda query, top_k=5: [],
                              open_document_fn=lambda *a, **k: {"doc_id": "d", "text": text, "start": 0, "end": len(text)},
                              config=config(context_chars=6000), client=client).run("Read d and identify its founder.")
        messages = client.requests[-1]["messages"]
        self.assertEqual([m["role"] for m in messages][-2:], ["assistant", "tool"])
        self.assertEqual(messages[-2]["tool_calls"][0]["id"], messages[-1]["tool_call_id"])
        compact = json.loads(messages[-1]["content"])
        self.assertTrue(compact["text_truncated"])
        self.assertEqual(compact["visible_text_end"], len(compact["text"]))
        self.assertEqual(compact["end"], len(text))
        self.assertEqual(result["evidence"][0]["text"], text)
        self.assertEqual(result["status"], "completed")
        self.assertLessEqual(result["context_stats"]["max_message_chars"], 6000)

    def test_empty_duplicate_and_new_searches_have_distinct_feedback(self):
        hit = {"doc_id": "d", "score": 1, "snippet": "Candidate"}
        searches = iter([[], [hit], [hit], [dict(hit, snippet="Another passage")]])
        client = QueueClient(*(response(call=("search", {"query": str(i)})) for i in range(4)),
                             response(json.dumps({"answer": "Candidate", "supporting_evidence": ["E1"]})))
        result = create_agent(lambda query, top_k=5: next(searches), config=config(), client=client).run("Who?")
        rows = [e["result"] for e in result["trajectory"] if e["type"] == "tool_result"]
        self.assertEqual([r["new_evidence"] for r in rows], [0, 1, 0, 1])
        self.assertEqual([r["stalled_searches"] for r in rows], [1, 0, 1, 0])
        self.assertIn("No matches", rows[0]["feedback"])
        self.assertIn("No new evidence", rows[2]["feedback"])
        self.assertEqual(result["state"]["stalled_searches"], 0)

    def test_empty_eof_read_does_not_create_a_citable_evidence_id(self):
        client = QueueClient(response(call=("open_document", {"doc_id": "d"})), response(""))
        result = create_agent(lambda query, top_k=5: [], open_document_fn=lambda *a, **k: {"text": ""},
                              config=config(), client=client).run("Who?")
        self.assertEqual(result["evidence"], [])

    def test_cli_closes_backend_when_run_fails(self):
        backend = FunctionBackend(lambda query, top_k=5: [])
        with tempfile.TemporaryDirectory() as directory, patch("search_agent.agent12._backend", return_value=backend), \
                patch("search_agent.agent12.load_config", return_value=config()), \
                patch("search_agent.agent12.SearchAgent", side_effect=ValueError("invalid agent")), \
                contextlib.redirect_stderr(io.StringIO()):
            code = main(["--backend", "test:factory", "--question", "Who?", "--output", str(Path(directory)/"out.json")])
        self.assertEqual(code, 2)
        self.assertTrue(backend.closed)

    def test_cli_preserves_existing_output_before_loading_or_calling_api(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.json"
            output.write_text("keep", encoding="utf-8")
            with patch("search_agent.agent12.load_config") as load, contextlib.redirect_stderr(io.StringIO()):
                code = main(["--fixture-backend", "--output", str(output)])
            load.assert_not_called()
            self.assertEqual(code, 2)
            self.assertEqual(output.read_text(), "keep")


@unittest.skipUnless((PEER / "src/rag_agent/peer_backend.py").is_file(), "Set AGENT12_PEER_PROJECT to the supplied 1.1 source")
class RealPeerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.prepare_peer12 import prepare
        cls.temporary = tempfile.TemporaryDirectory()
        try:
            cls.summary = prepare(PEER, cls.temporary.name)
        except ImportError as exc:
            cls.temporary.cleanup()
            raise unittest.SkipTest(str(exc))
        cls.config_path = cls.summary["config"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def backend(self):
        return FunctionBackend.from_backend(load_peer_backend(PEER, self.config_path))

    def test_real_bm25_passages_keep_source_ranges_and_distinct_chunk_ids(self):
        with self.backend() as backend:
            rows = backend.search("Helion", top_k=2)
            self.assertEqual([row["doc_id"] for row in rows], ["two-facts", "two-facts"])
            self.assertNotEqual(rows[0]["chunk_id"], rows[1]["chunk_id"])
            text = backend.open_document("two-facts")["text"]
            for row in rows:
                self.assertEqual(text[row["start"]:row["end"]], row["text"])

    def test_actual_retrieval_multi_hop_loop_and_method_provenance(self):
        client = QueueClient(response(call=("search", {"query": "Lumen", "top_k": 1})),
                             response(call=("search", {"query": "Cedar Northport", "top_k": 1})),
                             response(json.dumps({"answer": "Northport", "supporting_evidence": ["E1", "E2"]})))
        with self.backend() as backend:
            result = SearchAgent(backend, config=config(require_evidence=True), client=client).run("Which city?")
            self.assertTrue(backend.describe()["synthetic"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual([q["method"] for q in result["state"]["queries"]], ["sparse", "sparse"])
        self.assertEqual(len(result["supporting_evidence"]), 2)
        self.assertNotIn("method", client.requests[0]["tools"][0]["function"]["parameters"]["properties"])

    def test_same_document_multiple_passages_are_visible_and_citable(self):
        client = QueueClient(response(call=("search", {"query": "Helion", "top_k": 2})),
                             response(json.dumps({"answer": "Nara Vale; 1977", "supporting_evidence": ["E1", "E2"]})))
        with self.backend() as backend:
            result = SearchAgent(backend, config=config(require_evidence=True), client=client).run("Who founded Helion and when did it open?")
        self.assertEqual(result["status"], "completed")
        state = json.loads(client.requests[-1]["messages"][1]["content"])
        self.assertEqual(len(state["evidence"]), 2)
        self.assertEqual(result["visited_documents"], ["two-facts"])
        self.assertTrue(all(e["chunk_id"] is not None for e in state["evidence"]))

    def test_configuration_resolves_against_peer_root_and_never_loads_dotenv(self):
        config_path = PEER / "configs/demo.yaml"
        before = dict(os.environ)
        with patch.dict("sys.modules", {"dotenv": None}):
            settings, _, actual = load_peer_settings(PEER, "configs/demo.yaml", method="sparse")
        self.assertEqual(actual, config_path.resolve())
        self.assertEqual(dict(os.environ), before)
        self.assertTrue(Path(settings.store_path).is_absolute())
        self.assertTrue(Path(settings.store_path).is_relative_to(PEER.resolve()))

    def test_find_limits_real_repeated_document_and_keeps_offsets(self):
        with self.backend() as backend:
            result = backend.find_in_document("repeated-phrase", "marker", window=20)
            text = backend.open_document("repeated-phrase", length=12000)["text"]
        self.assertEqual(len(result["matches"]), 8)
        self.assertTrue(result["truncated"])
        for row in result["matches"]:
            self.assertEqual(text[row["start"]:row["end"]], row["text"])


if __name__ == "__main__":
    unittest.main()
