# Skill-Augmented Search Agent — Group 18

COMP5423 2026 Fall group project. The system answers questions over the fixed
BrowseComp-Plus corpus (100,195 documents) with a tool-using agent, explicit
evidence citations, two runtime-loaded skills, and a Streamlit UI.

This README documents the code snapshot that produced the submitted
`test_prediction.jsonl`, how to install it, how to rebuild the index, how to
reproduce the predictions, and how the API key is supplied. No credentials,
model weights, or full indexes are included in this archive.

## 1. Submitted artefact

| Item | Value |
| --- | --- |
| Code commit | `dab7646` plus the checked-in rerun prompt/config (2026-11-19/20) |
| Prediction configs | `configs/context64.yaml` (single pass) |
| Config ids | `af985bb241f6ca07` |
| Predictions | `../test_prediction.jsonl`, 109,300,422 bytes |
| Prediction SHA-256 | `8d0d58984e384aa69414ef37600cded705f75a93ce64c001fe2bc9daad512a80` |
| Records | 100 (exactly one per question, ids in `data/test.jsonl` order) |
| Answered / abstained | 85 / 15 (`insufficient_evidence`) |
| Tool calls | 991 |
| API tokens | 7,040,451 |
| Record fields | `id`, `question`, `answer`, `trajectory`, `tool_calls`, `total_tokens` |

The recorded validation run (100 labelled questions) with the frozen 2026-11-15
agent reached **normalized EM 19/100** (20 answered, 19 correct). A 2026-11-19
commit-prompt rerun reached 26/100 (EM 26%, 46 answered). On 2026-11-20 the
agent was run with thinking enabled and `context_chars: 64000`: 78 answered,
54 correct (**EM 54%**); a 96k fallback on the rows that still had no answer
added 6 answers and 2 correct; the extended answer canonicalisation then fixes
IDs 52 and 276, for a merged **84 answered / 66 correct (EM 66%, 78.6%
precision)**. The submitted
test predictions use the single 64k pass with final-answer thinking disabled,
answering 85 of 100; unlike validation, the test batch needs no 96k fallback.
Raw validation predictions and the audit reports used for the report are in
`../evidence/`.

## 2. What is in this directory

```
README.md                 this file
pyproject.toml            package definition; dependencies and extras
requirements*.txt         lock/constraints for macOS arm64, Python 3.12
src/rag_agent/            corpus store, retrieval, agent loop, batch, evaluation, UI
agent12/                  Agent 1.2 implementation (peer integration, 70 tests)
configs/                  YAML configs; acceptance-final.yaml is the submitted run
data/test.jsonl           course public test questions (100 rows, id + question)
skills/                   two SKILL.md packs with YAML metadata
scripts/                  prepare/index/predict/audit helpers
tests/                    core test suite
docs/                     design notes, tool schemas, validation records
```

`indexes/`, `outputs/`, `data/course-full/`, `data/course/`, and `.env` are
intentionally absent. They are large or secret, and are rebuilt or supplied
locally by the steps below.

## 3. Environment

Python 3.11–3.13 is supported. The reference environment is macOS arm64 /
Python 3.12.14; the code also runs on Windows and Linux.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

python -m pip install --cache-dir .cache/pip -e ".[dev]"
```

Add `retrieval` only when building dense indexes (it installs PyTorch,
Transformers, `datasets`, and `huggingface-hub`):

```bash
python -m pip install --cache-dir .cache/pip -e ".[retrieval,dev]"
```

`pyproject.toml` is the single source of dependency truth. The base install
needs no API key and no model weights: BM25, the web UI, the evaluation code,
and the test suite all work offline.

## 4. Corpus and index

The fixed corpus is
[`Tevatron/browsecomp-plus-corpus`](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus)
(`train`, 100,195 documents, fields `docid/text/url`). The submitted run uses
the revision recorded by the project:

```bash
# 100,195 documents -> about 4.35M chunks at 900/150, SQLite store
USE_TORCH=0 rag-agent prepare --config configs/official-final.yaml --hf \
  --revision b27b02bc3e45511b8b82a13e6f90ce761df726f6

# Full BM25 (SQLite FTS5); expect several hours and roughly 15 GB on disk
rag-agent index --config configs/official-final.yaml --methods sparse
```

The BM25 index is ready when `indexes/course-full/manifest.json` reports
4,345,592 source chunks, matching the corpus fingerprint. The store path is
`data/course-full/documents.sqlite`; both paths are configurable in the YAML.

The code also implements E5 and Qwen instruction encoders plus RRF hybrid
fusion (`configs/course-full-vectors.yaml`, `configs/demo.yaml`). The submitted
predictions use the fully built sparse index only; see Section 9.

### Small, no-download demo

```bash
rag-agent prepare --config configs/demo.yaml --source tests/fixtures/corpus.jsonl
rag-agent index --config configs/demo.yaml --methods sparse
rag-agent ask --config configs/demo.yaml \
  'Where is the university attended by the architect of Lumen Observatory located?'
```

`configs/demo.yaml` uses only fictional fixture data. The demo controller is
rule-based and makes no API calls; it exists to exercise the data flow and UI.

## 5. API key and model endpoint

Credentials are read from the environment (or a local `.env` that is never
committed):

```bash
cp .env.example .env
# edit .env:
# LLM_API_KEY=sk-...
# LLM_BASE_URL=https://api.deepseek.com
# LLM_MODEL=deepseek-v4-flash
```

`LLM_BASE_URL`, `LLM_MODEL`, `LLM_MODEL_VERIFIED`, and
`LLM_MODEL_VERIFICATION_NOTE` override the values in the YAML. The key is used
only for live model calls; it is never needed to inspect the submitted
predictions. Graders may supply their own key and endpoint.

### Model identity (recorded transparently)

The submitted predictions were produced on 2026-11-19 through DeepSeek's
official OpenAI-compatible endpoint at `https://api.deepseek.com` with the model
name `deepseek-v4-flash`. The official endpoint accepts the legacy alias but
routes it to **DeepSeek-V4.1-Flash-1017**; responses reported `deepseek-flash`.
The course instructor confirmed on 2026-11-18 that the current official V4
endpoint is acceptable. The run therefore records:

```yaml
llm_model: deepseek-v4-flash
model_policy: official_compat
model_verified: false
model_verification_note: "2026-11-19: official alias; instructor confirmed V4.1 is acceptable; original 2026-04 weights not verified."
```

We do not claim that the run used the original April 2026 V4-Flash checkpoint.
The system is endpoint-agnostic: to run on a provider that pins the original
V4-Flash, set `model_policy: course_pinned`, `llm_base_url:
https://openrouter.ai/api/v1`, `llm_model: deepseek/deepseek-v4-flash-0731`,
and `model_verified: true` (the checked-in
`configs/course-full-vectors.yaml` is an example). Nothing else in the pipeline
changes.

## 6. Reproducing the submitted predictions

With the corpus store and BM25 index in place and a key exported:

```bash
rag-agent predict --config configs/official-final.yaml \
  --input data/test.jsonl \
  --output outputs/test_prediction.jsonl

# structural + citation audit (no labels needed)
rag-agent validate --config configs/official-final.yaml \
  --input data/test.jsonl \
  --predictions outputs/test_prediction.jsonl \
  --official-compat

# or the standalone report generator used for the report
python scripts/audit_predictions.py \
  --input data/test.jsonl \
  --predictions outputs/test_prediction.jsonl \
  --output outputs/audit-test100.json
```

The expected `--official-compat` result is: 100 records, coverage 1.0,
85 answered, 15 empty answers, 100/100 citations resolvable, 991 tool
calls, and 7,040,451 tokens. The batch records a single config id
(`af985bb241f6ca07`), so `valid=true`; `formal=false` only because the
official-compatible model identity is not the verified original V4 weights. Exact
token counts can differ if the model version or prompt changes; the record
schema, id order, and citation rules must not.
`--formal` additionally demands a verified original-model identity and will
report the two model-identity errors per record for this official-compatible
batch; that is the audit trail used in the report, not a hidden failure.

## 7. Web UI

```bash
python -m streamlit run src/rag_agent/web_app.py \
  --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

Open `http://127.0.0.1:8501`, select a YAML in the sidebar, and ask a question.
The page shows the answer, cited evidence with document ids and offsets, the
selected/loaded skills, the tool trace, and token/tool counters. The UI calls
the same `agent.loop.run_question` used by the CLI and batch runner.

## 8. Tests

```bash
python -m pytest                       # core suite
cd agent12 && python -m unittest discover -s tests -v   # Agent 1.2 suite
```

The Agent 1.2 suite needs `agent12/requirements-peer.txt`. Both suites are
offline; they use synthetic corpora and a fake model client.

## 9. Scope and limitations

- **Retrieval.** All three categories are implemented: BM25 (sparse), E5
  (encoder), and Qwen3-Embedding-0.6B (instruction), plus RRF hybrid. The
  submitted batch uses the complete sparse index. The dense indexes were not
  complete at submission time: the E5 build reached 7.3% of 4,345,592 chunks
  and the Qwen build 0.2%, so they are excluded from the submitted run and
  from its numbers. Small-scale measurements (97 documents, 20 questions)
  gave Recall@5 1.00 for BM25 and 0.95 for E5, and 19.5 vs 2.4 chunks/s for E5
  vs Qwen on CPU.
- **Answering.** In the frozen 2026-11-15 run, 80 of 100 validation questions
  ended in an honest `insufficient_evidence` abstention; the dominant cause was
  that the evidence was never retrieved (64 questions), with 8 visible but
  excluded from the request, 8 in the request and still abstained, and 1
  name-alias error. The final 64k + 96k policy raises coverage to 84/100 and
  EM to 56%, but 28 answers are wrong: the remaining bottleneck is retrieval
  precision, not the answer format.
- **Index portability.** The full corpus store and BM25 index are not in this
  archive. They are rebuilt by Section 4, or restored from the group's
  `program-acceptance-20261115` release, which is encrypted and shared
  separately by the owner.

## 10. Data and licence notes

`data/test.jsonl` is the course's public test split
([`HongruCai/COMP5423-BrowseComp-Plus-Test`](https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Test)),
SHA-256 `2e9e3689de5901e0151995db91d0fa6525b2062cc116ddab88f59b9ccccd5d0b`.
The corpus is used only through the course benchmark; source URLs are retained
for provenance. No reference answers are read by the agent. No secrets,
credentials, model weights, or private keys are included.
