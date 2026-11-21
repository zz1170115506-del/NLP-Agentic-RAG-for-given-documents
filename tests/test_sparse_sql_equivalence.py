"""Regression against the previous SQL, including exact boundary ties."""
import random
import re

import pytest

from rag_agent.data import DocumentStore
from rag_agent.retrieval.sparse import SparseRetriever, build_sparse
from rag_agent.schemas import Document, SearchHit


OLD_SQL = """SELECT r.doc_id,r.chunk_id,r.offset,r.text,r.url,bm25(fts) AS score
    FROM fts JOIN records r ON r.seq=fts.rowid WHERE fts MATCH ? ORDER BY score,r.seq LIMIT ?"""


def legacy_search(conn, query, top_k):
    tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE)))[:64]
    if not tokens:
        return []
    expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
    hits = []
    for row in conn.execute(OLD_SQL, (expression, top_k)):
        data = dict(row)
        data["score"] = -float(data["score"])
        hits.append(SearchHit(**data, method="sparse"))
    return hits


@pytest.fixture
def retriever(tmp_path):
    rng = random.Random(782019)
    vocabulary = ["circuit", "copper", "student", "campus", "signal", "sensor", "café", "校园"]
    docs = [Document(doc_id=f"tie-{i:03}", text="identical boundary token",
                     url=f"https://example.invalid/tie/{i}") for i in range(35)]
    docs += [Document(doc_id=f"random-{i:03}",
                      text=" ".join(rng.choices(vocabulary, k=rng.randrange(1, 45))),
                      url=f"https://example.invalid/random/{i}") for i in range(150)]
    store = DocumentStore(tmp_path / "store.sqlite")
    store.import_documents(docs, 512, 0, source={"type": "synthetic-equivalence-only"})
    build_sparse(store, tmp_path / "index")
    searcher = SparseRetriever(tmp_path / "index" / "sparse.sqlite", store.fingerprint)
    try:
        yield searcher, rng, vocabulary
    finally:
        searcher.conn.close()
        store.close()


def test_equal_scores_keep_original_rowid_order_at_limit(retriever):
    searcher, _, _ = retriever
    for top_k in (1, 5, 20, 35, 40):
        actual = searcher.search("identical", top_k)
        assert actual == legacy_search(searcher.conn, "identical", top_k)
        assert len({h.score for h in actual}) == 1
        assert [h.doc_id for h in actual] == [f"tie-{i:03}" for i in range(min(35, top_k))]


def test_random_queries_preserve_ids_scores_and_original_text(retriever):
    searcher, rng, vocabulary = retriever
    queries = ["", "___---", '" OR NOT ; copper', "café 校园", "notincorpus", "CIRCUIT circuit copper"]
    queries += [" ".join(rng.choices(vocabulary + ["absent"], k=rng.randrange(1, 14))) for _ in range(80)]
    queries += [" ".join(f"missing{i}" for i in range(64)) + " copper"]
    for query in queries:
        for top_k in (1, 5, 20):
            # Pydantic equality includes every field: IDs, exact float score,
            # source offsets/text/URL and method (no approximate comparison).
            assert searcher.search(query, top_k) == legacy_search(searcher.conn, query, top_k)
