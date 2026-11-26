# Submission evidence

Small audit artifacts referenced by the report and `VERIFY.md`.

Included here:

- `audit-test100.json` — final v5 test-batch audit (85 answered / 15 abstained,
  991 calls, 7,040,451 tokens, citation 100/100, one config id).
- `audit-validation100.json`, `validation100-canon3.json` — validation audit
  and the 84-answer / 66-correct canonicalised result.
- `audit-test100-frozen-20261115.json` — frozen 2026-11-15 baseline audit.
- `SHA256SUMS.txt` — checksums for the prediction files and the audit files.

The prediction JSONL files are intentionally **not** committed to Git:

- `test_prediction.jsonl` is 109,300,422 bytes and exceeds GitHub's 100 MB
  per-file limit. It is attached to the `final-group18-20261122` release.
- The older prediction snapshots (`test_prediction-88-20261120.jsonl`,
  `test_prediction-v2-20261119.jsonl`, `test_prediction-frozen-20261115.jsonl`,
  `test_prediction-context64-96-20261120.jsonl`, `validation_prediction.jsonl`)
  are kept in the local submission/evidence bundle and in the release/backup
  assets; they are omitted here to keep the repository small.

Paths in `SHA256SUMS.txt` are relative to the submission layout
(`Group-18/test_prediction.jsonl`, etc.), not to this directory.
