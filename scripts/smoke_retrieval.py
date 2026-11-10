"""Explicit real-model smoke test on synthetic documents; may download model weights."""
import argparse
import json
from pathlib import Path
from rag_agent.config import Settings
from rag_agent.data import DocumentStore, iter_jsonl
from rag_agent.retrieval import build_indexes, SearchService
from rag_agent.runtime import local_caches

p = argparse.ArgumentParser()
p.add_argument('--methods', nargs='+', choices=['sparse','encoder','instruction'], default=['sparse','encoder','instruction'])
p.add_argument('--device', default='cpu')
a = p.parse_args()
local_caches()
cfg = Settings(mode='demo',store_path='data/smoke.sqlite',index_dir='indexes/smoke',device=a.device,batch_size=2)
store = DocumentStore(cfg.store_path)
store.import_documents(iter_jsonl('tests/fixtures/corpus.jsonl'),cfg.chunk_size,cfg.chunk_overlap,source={'kind':'synthetic_smoke'})
manifest = build_indexes(cfg,a.methods,progress=print)
search = SearchService(cfg)
results = {}
for method in a.methods:
    hits = search.search('Where is Cedar University located?',3,method)
    assert hits, f'{method}: no results'
    assert hits[0].doc_id == 'd2', f'{method}: expected the direct university document to rank first'
    for hit in hits:
        doc = store.get(hit.doc_id)
        assert doc.text[hit.offset:hit.offset+len(hit.text)] == hit.text
    results[method] = {'hits': [hit.model_dump() for hit in hits], 'manifest':manifest[method]}
Path('outputs').mkdir(exist_ok=True)
Path('outputs/retrieval_smoke.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps({'passed':list(results),'data':'3 synthetic documents','device':a.device}))
