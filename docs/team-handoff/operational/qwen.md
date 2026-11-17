# Qwen 九题复测

表中选取每份文件的关键读数。JSONL 保留所有已识别事件的源行号和完整 SHA-256。复制路径在同一条记录中列举。

[JSONL](qwen.jsonl) · [全部阶段](README.md)

| 代表来源 | SHA-256 前 12 位 | 源行 / 导出事件 | 关键读数 |
|---|---|---:|---|
| `outputs/qwen4b_nine/qwen4b-review/QWEN4B_EVIDENCE_RECEIPT.json` | `394f1c576c2a` | 16 / 1 | {"plaintext_bytes":11422719} |
| `outputs/qwen4b_nine/qwen4b-review/source-verification.json` | `16e3217420c9` | 75 / 0 | 仅有指纹与行数 |
| `outputs/qwen4b_nine/发布核验.json` | `baceb45f5aa4` | 60 / 0 | 仅有指纹与行数 |
| `qwen2560/GitHub发布核验.json` | `eef5f0662917` | 14 / 1 | {"source_files_matched":408,"downloaded_assets_matched":6,"restored_evidence_files_matched":26} |
| `qwen2560/QWEN4B_EVIDENCE_RECEIPT.json` | `1caa769551d6` | 16 / 1 | {"plaintext_bytes":16391005} |
| `qwen2560/本机还原校验.json` | `9b2a0ea92a21` | 9 / 1 | {"status":"verified","authenticated_decryption":true,"logical_evidence_files_restored":26,"all_original_sha256_matched":true,"plaintext_bytes":16391005} |
| `work/q4-handoff-dev/fixture-15jezxtr/download/QWEN4B_EVIDENCE_RECEIPT.json` | `ffc9ff9c012b` | 16 / 1 | {"plaintext_bytes":200} |
| `work/q4-handoff-dev/fixture-npz-2mhhyxcy/out/release-assets/QWEN4B_EVIDENCE_RECEIPT.json` | `044856e343d4` | 16 / 1 | {"plaintext_bytes":1609} |
| `work/q4-project/work/pre-release-package-1/release-assets/QWEN4B_EVIDENCE_RECEIPT.json` | `423fc4a13976` | 16 / 1 | {"plaintext_bytes":11355145} |
