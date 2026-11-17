# 其他运行与检查

表中选取每份文件的关键读数。JSONL 保留所有已识别事件的源行号和完整 SHA-256。复制路径在同一条记录中列举。

[JSONL](other.jsonl) · [全部阶段](README.md)

| 代表来源 | SHA-256 前 12 位 | 源行 / 导出事件 | 关键读数 |
|---|---|---:|---|
| `early-course/bm25-sql-probe.json` | `d31f6d39e65b` | 23 / 0 | 仅有指纹与行数 |
| `early-course/bm25-sql-probe.log` | `32e6549491f7` | 1 / 0 | 仅有指纹与行数 |
| `early-course/course-paired-r2/agent12-audit.json` | `c896ac3a3cc6` | 33 / 1 | {"expected":5,"records":5,"citation_passed":5,"tool_calls":19,"total_tokens":49049,"archived_attempts":0,"all_attempts_total_tokens":49049,"all_attempts_tool_calls":19,"correct":5,"em":1.0} |
| `early-course/full-sparse-probe.json` | `cb555125c493` | 13 / 1 | {"samples":10} |
| `early-course/full-sparse-probe.log` | `53fc734c94fe` | 1 / 1 | {"samples":10} |
| `early-course/mechanism-ablations.log` | `11c8c75bc229` | 3 / 0 | 仅有指纹与行数 |
| `early-course/official-query-sample-command.log` | `57531033ea5f` | 3 / 0 | 仅有指纹与行数 |
| `early-course/paired-r1.log` | `02b55d30672f` | 2 / 0 | 仅有指纹与行数 |
| `early-course/paired-r2.log` | `3f81a56dc504` | 2 / 0 | 仅有指纹与行数 |
| `early-course/real-context.log` | `29b27e377b5e` | 1 / 1 | {"status":"completed","tool_calls":2} |
| `early-course/real-mechanisms-r2.log` | `ae08e471b66f` | 4 / 4 | {"seconds":16.705722625018097} |
| `early-course/real-mechanisms.log` | `636eac1af5f7` | 4 / 4 | {"seconds":9.615079040988348} |
| `early-course/web-server.log` | `b82814d620d4` | 10 / 0 | 仅有指纹与行数 |
