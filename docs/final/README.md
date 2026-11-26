# Group 18 — final technical snapshot (2026-11-22)

This directory records the final validated state of the Group 18 search agent.
It is a research snapshot, not the official course submission package.

## Validation result

- 100 labelled questions, 84 answered, 66 correct.
- Normalized EM 66/100 (0.66); precision among answers 78.6%.
- 16 abstentions; 18 answered incorrectly.
- Policy: `context64` single pass, thinking enabled for retrieval/reasoning and
  disabled for the final answer, safe answer canonicalisation at parse time.

## Submitted test batch

- 85 answered / 15 abstained (all normal `insufficient_evidence` finalisation).
- 991 tool calls, 7,040,451 tokens.
- 109,300,422 bytes, SHA-256
  `8d0d58984e384aa69414ef37600cded705f75a93ce64c001fe2bc9daad512a80`.
- One recorded config id (`af985bb241f6ca07`); `valid=true`, `formal=false`
  only because the official-compatible endpoint is not the verified original
  V4 weights.
- The prediction JSONL is not stored in Git because it exceeds GitHub's
  100 MB per-file limit; it is attached to the `final-group18-20261122`
  release and kept in the local submission/evidence bundle.

## Contents

- `Group-18-Report.md` — report source (Markdown; Overleaf-ready content).
- `Group-18-Report-preview.pdf` — 10-page local preview, not the official
  Overleaf PDF.
- `figures/` — architecture, validation outcomes, failure taxonomy, UI.
- `Video-script.md` — 4:45 demo shot list.
- `code-README.md` — submission-facing code README (environment, reproduction,
  API key handling, model identity, audit commands).
- `evidence/` — small audit JSONs and checksums; the large prediction JSONLs
  stay in the `final-group18-20261122` release and the local submission bundle.
- `VERIFY.md`, `CHECKLIST.md` — audit notes and submission checklist.

## Reproduction

```bash
pip install -e ".[retrieval]"
rag-agent predict --config configs/context64.yaml \
  --input data/test.jsonl --output outputs/test_prediction.jsonl
rag-agent validate --config configs/context64.yaml \
  --input data/test.jsonl --predictions outputs/test_prediction.jsonl \
  --official-compat
```

The answer canonicaliser is in
`agent12/search_agent/final_output.py`; it strips legal suffixes and duplicate
trailing parenthetical aliases, normalises unit spacing, and reorders a leading
year. It does not change the fact being stated.

## Limitations

- 28 of 42 validation failures are cases where the gold answer never
  appeared in any retrieval result.
- Dense routes (E5-small, E5-large, Qwen3-Embedding-0.6B), hybrid fusion,
  weighted RRF, query rewriting, document-level aggregation and reranking were
  all evaluated and did not beat BM25-only on the full split.
- The 90/90 target is not reachable with the current reader/retriever stack;
  an oracle run that feeds gold evidence directly scores 79/100.
