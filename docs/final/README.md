# Group 18 — final technical snapshot (2026-11-21)

This directory records the final validated state of the Group 18 search agent.
It is a research snapshot, not the official course submission package.

## Validation result

- 100 labelled questions, 84 answered, 66 correct.
- Normalized EM 66/100 (0.66); precision among answers 78.6%.
- 16 abstentions; 18 answered incorrectly.
- Policy: `context64` first pass, `context96` fallback for unanswered rows,
  thinking enabled for retrieval/reasoning and disabled for the final answer,
  extended answer canonicalisation at parse time.

## Submitted test batch

- 88 answered / 12 abstained.
- 1,004 tool calls, 7,612,685 tokens.
- 113,182,809 bytes, SHA-256
  `229bad39d7cd474f9b2cb9d9da1bea45775d349535ce3787e95c05c8f3650c08`.
- The prediction JSONL is not stored in Git because it exceeds GitHub's
  100 MB per-file limit; it is kept in the local submission/evidence bundle
  and should be distributed as a release asset or private handoff.

## Contents

- `Group-18-Report.md` — report source (Markdown; Overleaf-ready content).
- `Group-18-Report-preview.pdf` — 10-page local preview, not the official
  Overleaf PDF.
- `figures/` — architecture, validation outcomes, failure taxonomy, UI.
- `Video-script.md` — 4:45 demo shot list.
- `VERIFY.md`, `CHECKLIST.md` — audit notes and submission checklist.

## Reproduction

```bash
pip install -e ".[retrieval]"
rag-agent predict --config configs/context64.yaml \
  --input data/course/validation.jsonl --output outputs/val64.jsonl
rag-agent predict --config configs/context96.yaml \
  --input <unanswered-rows.jsonl> --output outputs/val96.jsonl
```

The answer canonicaliser is in
`agent12/search_agent/final_output.py`; it strips legal suffixes and duplicate
trailing parenthetical aliases, normalises unit spacing, and reorders a leading
year. It does not change the fact being stated.

## Limitations

- 25 of 36 validation failures (69%) are cases where the gold answer never
  appeared in any retrieval result.
- Dense routes (E5-small, E5-large, Qwen3-Embedding-0.6B), hybrid fusion,
  weighted RRF, query rewriting, document-level aggregation and reranking were
  all evaluated and did not beat BM25-only on the full split.
- The 90/90 target is not reachable with the current reader/retriever stack;
  an oracle run that feeds gold evidence directly scores 79/100.
