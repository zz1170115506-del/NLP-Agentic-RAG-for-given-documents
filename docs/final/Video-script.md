# Group 18 — Demo Video Script (≤ 5:00, MP4)

Target length 4:45. Record at 1080p, 16:9, one continuous screen capture with
voice-over. The demo below uses `configs/demo.yaml` (fictional fixtures, no API
call) so recording never depends on a key or network; a real validation
trajectory is shown as a second window for the benchmark evidence. If a key is
available, replace Scene 4 with a live question (see the note at the end).

## Shot list

| Time | Visual | Narration / action |
| --- | --- | --- |
| 0:00–0:25 | Title slide: "Group 18 — Skill-Augmented Search Agent", course, names. | "This is Group 18's skill-augmented search agent for the fixed BrowseComp-Plus corpus: 100,195 documents, four tools, two skills, and auditable evidence for every answer." |
| 0:25–0:55 | Architecture slide (`report/figures/architecture.png`). Highlight corpus → BM25/dense → RRF → agent → skills → UI. | "The pipeline imports the corpus into 4.35 million overlapping chunks, indexes it with SQLite FTS5 BM25, E5, and Qwen3-Embedding, fuses the routes with RRF, and lets a four-tool agent decide when to stop." |
| 0:55–1:35 | Terminal: `rag-agent search --config configs/corpus-smoke.yaml "<question>" --method sparse`, then `--method encoder`, then `--method instruction`. Show top-5 fragments with doc ids. | "All three retrieval categories share one query interface. Sparse is sub-millisecond; E5 and Qwen use the documented prefixes, pooling, and L2 normalisation. Results are fragments, not documents, so citations can point at exact spans." |
| 1:35–2:05 | Open `configs/acceptance-final.yaml` and `skills/multi-clue-decomposition/SKILL.md`; scroll the metadata and body. | "The run is fully configured: 900/150 chunking, top-5, 12 steps, 24 calls, 30k tokens, 24k context. Skills are Markdown files: only metadata loads at start; the body enters the request when the selector or the model chooses it." |
| 2:05–3:05 | Streamlit UI (`configs/demo.yaml`). Ask "Where is the university attended by the architect of Lumen Observatory located?" Show answer `Northport`, 5 steps, 4 tool calls, both skills selected, evidence cards E1/E2 with offsets. | "The Evidence Desk shows the full reasoning surface: the answer, the step and tool counters, which skills were selected, and the cited spans with document ids and character offsets. This is the same `run_question` path used by the CLI and the batch runner." |
| 3:05–3:35 | Switch the question to a single-clue question (e.g. "When did the Copper Museum open?"). Show that only the recovery/decomposition skill set changes; the trace shows the tool sequence. | "Skill selection is driven by the question and the search state. Multi-clue questions trigger decomposition; stalled or empty searches trigger recovery, which changes the next query instead of repeating it." |
| 3:35–4:05 | Split screen: `submission/Group-18/test_prediction.jsonl` first record (six fields) and `evidence/audit-test100.json` summary: 100 records, 20 answered, 80 insufficient evidence, 689 calls, 1,576,143 tokens. | "The submitted predictions are six-field records with a complete trajectory, tool calls, and real usage. The audit reports 100 records, 20 answers, 80 honest abstentions, and 689 tool calls." |
| 4:05–4:25 | Validation chart (`report/figures/validation-outcomes.png`): 19 correct, 1 wrong, 80 abstained; then failure chart (`failure-taxonomy.png`). | "On the labelled validation set, 19 of the 20 answers are correct, so precision is 95%. The bottleneck is coverage: 64 of the 80 abstentions never retrieved the answer evidence at all." |
| 4:25–4:45 | Code tree: `src/rag_agent/{retrieval,agent,tools,evaluation}`, `skills/`, `configs/`, `tests/`; then closing slide with repo layout and "thank you". | "The code is separated into retrieval, agent, tools, evaluation, and UI, with frozen configs and tests. The README explains installation, index rebuild, key provisioning, and reproduction of the predictions. Thank you." |

## Recording checklist

- Close notifications, chat apps, and personal browser tabs; use a clean
  desktop or a dedicated browser profile.
- Terminal font at least 16 pt; light theme; hide the command prompt path if it
  contains personal folders.
- Do not show `.env`, API keys, account balance, or personal file paths. The
  demo config makes zero API calls, so no key appears in Scenes 3–5.
- The UI screenshot in the report uses the fictional demo corpus; say so on
  screen or in narration, so the demo is not mistaken for a benchmark run.
- Export H.264 MP4, 1920×1080, 30 fps, stereo audio; check the duration is
  under 5:00 and the file plays on a clean machine.

## Optional live-benchmark variant (Scene 4)

If a key and the full BM25 index are available, replace the demo question with
a validation question whose evidence is known, for example a question from the
validation set that the agent answered correctly. Run:

```bash
export LLM_API_KEY=...
rag-agent ask --config configs/acceptance-final.yaml \
  "When did the Copper Museum open?"
```

Then show the real trajectory, the model response, and the cited evidence. Do
not show the key or the `.env` file. Keep the runtime under 90 seconds; if the
call stalls, fall back to the recorded demo and the archived trajectory.
