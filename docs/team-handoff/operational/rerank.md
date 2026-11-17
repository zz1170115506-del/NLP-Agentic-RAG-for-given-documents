# 早期重排实验

表中选取每份文件的关键读数。JSONL 保留所有已识别事件的源行号和完整 SHA-256。复制路径在同一条记录中列举。

[JSONL](rerank.jsonl) · [全部阶段](README.md)

| 代表来源 | SHA-256 前 12 位 | 源行 / 导出事件 | 关键读数 |
|---|---|---:|---|
| `early-rerank/corpus_close_smoke.json` | `46d49a3c998e` | 20 / 1 | {"skipped":0,"document_count":2,"chunk_count":7,"seconds":13.68} |
| `early-rerank/corpus_close_smoke.log` | `a75ed675cc9c` | 4 / 0 | 仅有指纹与行数 |
| `early-rerank/corpus_import_smoke.json` | `b9764ccdb7e0` | 20 / 1 | {"skipped":0,"document_count":5,"chunk_count":14,"seconds":16.36} |
| `early-rerank/rerank-analysis-deps.log` | `c79be1c6f602` | 33 / 0 | 仅有指纹与行数 |
| `early-rerank/rerank-corpus-import.log` | `588851d3d925` | 7 / 3 | {"skipped":0,"document_count":100,"chunk_count":3903,"seconds":33.7} |
| `early-rerank/rerank-eval/api-main.log` | `6084f2eb0825` | 8 / 8 | {"total_tokens":32597,"tool_calls":4,"usage_complete":true} |
| `early-rerank/rerank-eval/api-pilot.log` | `d0a39e8d5342` | 3 / 2 | {"total_tokens":32134,"tool_calls":3,"usage_complete":true} |
| `early-rerank/rerank-eval/baseline/pytest.log` | `5952b218382e` | 1 / 0 | 仅有指纹与行数 |
| `early-rerank/rerank-eval/depth10-dev.log` | `26fc82c54450` | 15 / 1 | {"samples":10,"failures":0} |
| `early-rerank/rerank-eval/final-experiment-audit.json` | `4b80122d327b` | 548 / 1 | {"status":"passed"} |
| `early-rerank/rerank-eval/final-pip-check.log` | `5acc2c67965b` | 2 / 1 | {"check":"pip_check_ok"} |
| `early-rerank/rerank-eval/final-pytest.log` | `973b3fd5ba8b` | 2 / 1 | {"passed":65,"check":"pytest","seconds":0.77} |
| `early-rerank/rerank-eval/final-ruff.log` | `82b3e6a6c090` | 1 / 1 | {"check":"ruff_ok"} |
| `early-rerank/rerank-eval/installed-factory-real.json` | `164be8dbb007` | 22 / 1 | {"status":"passed","count":5} |
| `early-rerank/rerank-eval/installed-factory-real.log` | `b8a681f300ac` | 1 / 1 | {"status":"passed","count":5} |
| `early-rerank/rerank-eval/latency-integrated.log` | `8518bb84f019` | 65 / 0 | 仅有指纹与行数 |
| `early-rerank/rerank-eval/minimum-clean-install.log` | `1bbea8921412` | 153 / 0 | 仅有指纹与行数 |
| `early-rerank/rerank-eval/minimum-clean-smoke.log` | `952045383818` | 38 / 1 | {"status":"passed"} |
| `early-rerank/rerank-eval/package-install.log` | `f430aab90090` | 18 / 0 | 仅有指纹与行数 |
| `early-rerank/rerank-eval/pilot.log` | `26f1ff93bf6b` | 7 / 1 | {"samples":1,"failures":0} |
| `early-rerank/rerank-eval/real-model-smoke.json` | `050ce17a8f5e` | 167 / 1 | {"status":"passed"} |
| `early-rerank/rerank-eval/real-model-smoke.log` | `6b478a680912` | 2 / 1 | {"status":"passed"} |
| `early-rerank/rerank-eval/round1.log` | `f52f7a421c2e` | 16 / 1 | {"samples":10,"failures":0} |
| `early-rerank/rerank-eval/round2-control.log` | `a630933dc1e2` | 15 / 1 | {"samples":10,"failures":0} |
| `early-rerank/rerank-eval/round2-depth10.log` | `5e07074cb535` | 15 / 1 | {"samples":10,"failures":0} |
| `early-rerank/retrieval_smoke.json` | `c7d5e7203e91` | 212 / 0 | 仅有指纹与行数 |
| `early-rerank/retrieval_smoke.log` | `c18705b99680` | 3 / 3 | {"device":"cpu"} |
| `early-rerank/web-server.log` | `da1c2b3a1c32` | 10 / 0 | 仅有指纹与行数 |
