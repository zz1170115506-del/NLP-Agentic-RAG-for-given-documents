# 语料、索引与检索

表中选取每份文件的关键读数。JSONL 保留所有已识别事件的源行号和完整 SHA-256。复制路径在同一条记录中列举。

[JSONL-01](retrieval-01.jsonl) · [JSONL-02](retrieval-02.jsonl) · [全部阶段](README.md)

| 代表来源 | SHA-256 前 12 位 | 源行 / 导出事件 | 关键读数 |
|---|---|---:|---|
| `early-course/corpus-full-import-resume.log` | `1f9918f9fe32` | 1024 / 1003 | {"skipped":46800,"document_count":100195,"chunk_count":4345592,"seconds":871.92} |
| `early-course/corpus-full-import.log` | `141013372957` | 470 / 468 | {"documents_read":46800,"seconds":466.25} |
| `early-course/extended-encoder-cpu-retry.log` | `32861bacf584` | 133 / 132 | {"check":"stage_completed","seconds":841.3659272909863,"method":"encoder"} |
| `early-course/extended-encoder.log` | `56be06792799` | 90 / 19 | {"exception":"RuntimeError"} |
| `early-course/extended-instruction-retry.log` | `588d9ceb8489` | 68 / 13 | {"exception":"RuntimeError"} |
| `early-course/extended-instruction.log` | `18d9794dee69` | 46 / 0 | 仅有指纹与行数 |
| `early-course/full-index-phase.log` | `7c51fb228e9f` | 450 / 449 | {"check":"stage_completed","seconds":137.53779095801292,"method":"sparse"}；{"check":"stage_completed","seconds":63.160392833000515}；{"check":"stage_completed","seconds":30.767176707973704} |
| `early-course/index-benchmark-resume.log` | `a5c127b47fe0` | 2 / 0 | 仅有指纹与行数 |
| `early-course/index-benchmark.log` | `aa3e2b6dc358` | 1 / 0 | 仅有指纹与行数 |
| `early-course/index-shards-verification.log` | `80d40278447d` | 9 / 2 | {"method":"instruction"} |
| `early-course/index-shards-verification/instruction-000035-1794586914888174000.log` | `e62b338523ef` | 37 / 37 | {"seconds":39.372} |
| `early-course/qwen-shard-0012.log` | `bea2a52efeab` | 14 / 14 | {"check":"stage_completed","seconds":44.26692595798522,"method":"instruction"} |
| `early-course/qwen-shard-0013.log` | `a051f35c32f8` | 15 / 15 | {"check":"stage_completed","seconds":43.00072679197183,"method":"instruction"} |
| `early-course/qwen-shard-0014.log` | `cd928851def5` | 16 / 16 | {"check":"stage_completed","seconds":37.17484770901501,"method":"instruction"} |
| `early-course/qwen-shard-0015.log` | `74f4708153e1` | 17 / 17 | {"check":"stage_completed","seconds":30.659454042033758,"method":"instruction"} |
| `early-course/qwen-shard-0016.log` | `869d2d277cbd` | 18 / 18 | {"check":"stage_completed","seconds":48.071995083009824,"method":"instruction"} |
| `early-course/qwen-shard-0017.log` | `836deca249ad` | 19 / 19 | {"check":"stage_completed","seconds":26.010903333022725,"method":"instruction"} |
| `early-course/qwen-shard-0018.log` | `36beacccec17` | 20 / 20 | {"check":"stage_completed","seconds":30.211279792012647,"method":"instruction"} |
| `early-course/qwen-shard-0019.log` | `b63d9611bdb9` | 21 / 21 | {"check":"stage_completed","seconds":26.190923833986744,"method":"instruction"} |
| `early-course/qwen-shard-0020.log` | `d3842f0a61ab` | 22 / 22 | {"check":"stage_completed","seconds":26.353327916993294,"method":"instruction"} |
| `early-course/qwen-shard-0021.log` | `8dc857127e03` | 23 / 23 | {"check":"stage_completed","seconds":33.19131320895394,"method":"instruction"} |
| `early-course/qwen-shard-0022.log` | `e6af3bd550ab` | 24 / 24 | {"check":"stage_completed","seconds":24.968926958041266,"method":"instruction"} |
| `early-course/qwen-shard-0023.log` | `679a4f1c3ff7` | 25 / 25 | {"check":"stage_completed","seconds":34.55997337499866,"method":"instruction"} |
| `early-course/qwen-shard-0024.log` | `bca88fc01bca` | 26 / 26 | {"check":"stage_completed","seconds":47.34274066705257,"method":"instruction"} |
| `early-course/qwen-shard-0025.log` | `2787ecb77d31` | 27 / 27 | {"check":"stage_completed","seconds":46.543569582980126,"method":"instruction"} |
| `early-course/qwen-shard-0026.log` | `afdbc401430a` | 28 / 28 | {"check":"stage_completed","seconds":44.28893350000726,"method":"instruction"} |
| `early-course/qwen-shard-0027.log` | `6eaab467d098` | 29 / 29 | {"check":"stage_completed","seconds":46.807272833015304,"method":"instruction"} |
| `early-course/qwen-shard-0028.log` | `9af4bdcd367e` | 30 / 30 | {"check":"stage_completed","seconds":45.52622933301609,"method":"instruction"} |
| `early-course/qwen-shard-0029.log` | `c0950e8de14a` | 31 / 31 | {"check":"stage_completed","seconds":42.81299379200209,"method":"instruction"} |
| `early-course/qwen-shard-0030.log` | `cce7a02169f1` | 32 / 32 | {"check":"stage_completed","seconds":42.72999995900318,"method":"instruction"} |
| `early-course/qwen-shard-0031.log` | `9745817b9d46` | 33 / 33 | {"check":"stage_completed","seconds":46.10555537499022,"method":"instruction"} |
| `early-course/qwen-shard-0032.log` | `77b09705e3f8` | 34 / 34 | {"check":"stage_completed","seconds":48.7752542909584,"method":"instruction"} |
| `early-course/qwen-shard-0033.log` | `aca64b1ec219` | 35 / 35 | {"check":"stage_completed","seconds":28.340302416007034,"method":"instruction"} |
| `early-course/qwen-shard-0034.log` | `15ce7956c178` | 36 / 36 | {"check":"stage_completed","seconds":35.4751094999956,"method":"instruction"} |
| `early-course/qwen-shard-supervisor.log` | `6be488622f29` | 24 / 23 | {"exit_code":0,"seconds":35.942374625010416} |
| `early-course/retrieval-comparison-resume.log` | `a586918ec558` | 1106 / 0 | 仅有指纹与行数 |
| `early-course/retrieval-comparison.json` | `8cc841456f37` | 1106 / 0 | 仅有指纹与行数 |
| `early-course/retrieval-comparison.log` | `e3b0c44298fc` | 0 / 0 | 仅有指纹与行数 |
| `work/acceptance/offline/08_retrieval_dependencies.json` | `506fea259f24` | 23 / 1 | {"started_at_hong_kong":"2026-11-15T12:49:26.945487+08:00","finished_at_hong_kong":"2026-11-15T12:49:27.212016+08:00","elapsed_seconds":0.266,"returncode":1} |
| `work/acceptance/offline/08_retrieval_dependencies.log` | `f3d3e5fe5614` | 13 / 0 | 仅有指纹与行数 |
| `work/acceptance/offline/10_isolated_index.json` | `61f274eeb6ad` | 21 / 1 | {"started_at_hong_kong":"2026-11-15T12:50:08.206732+08:00","finished_at_hong_kong":"2026-11-15T12:50:08.301725+08:00","elapsed_seconds":0.095,"returncode":0} |
| `work/acceptance/offline/10_isolated_index.log` | `c0742aba170e` | 21 / 2 | {"method":"sparse","chunks":3,"total":3} |
| `work/acceptance/offline/32_installed_index.json` | `b197ebf292cb` | 17 / 1 | {"started_at_hong_kong":"2026-11-15T13:14:10.836154+08:00","finished_at_hong_kong":"2026-11-15T13:14:11.458872+08:00","elapsed_seconds":0.623,"returncode":0} |
| `work/acceptance/offline/32_installed_index.log` | `86daa86a242d` | 21 / 2 | {"method":"sparse","chunks":3,"total":3} |
| `work/acceptance/offline/final_index.json` | `2c62ec0ed78a` | 17 / 1 | {"started_at_hong_kong":"2026-11-15T13:43:19.470523+08:00","finished_at_hong_kong":"2026-11-15T13:43:19.734748+08:00","elapsed_seconds":0.264,"returncode":0} |
| `work/acceptance/offline/final_index.log` | `164aa2b834af` | 21 / 2 | {"method":"sparse","chunks":3,"total":3} |
| `work/deepseek-official-compat/work/acceptance/evidence-stage/work/acceptance/indexes/e5-cpu-continuous-post-snapshot.log` | `3c4ebbefa3c8` | 117 / 116 | {"method":"encoder","chunks":343040,"total":4345592,"reused":false,"elapsed_seconds":662.9932901249849} |
| `work/deepseek-official-compat/work/acceptance/evidence-stage/work/acceptance/indexes/qwen-cpu-shard1.log` | `ec7d8645f565` | 50 / 0 | 仅有指纹与行数 |
| `work/deepseek-official-compat/work/acceptance/indexes/bounded-sparse-e5.json` | `e1b322606cc0` | 5093 / 1 | {"rows_items":20} |
| `work/deepseek-official-compat/work/acceptance/indexes/bounded-sparse-e5.log` | `e2f79103e8f7` | 130 / 20 | {"complete":true} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-batch-thread-benchmark.json` | `2b8b9f037956` | 112 / 1 | {"device":"cpu","runs_items":3,"vector_rows":264,"selected":{"batch_size":32,"seconds":4.6707463339553215}} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-batch-thread-benchmark.log` | `f62373256e4e` | 4 / 3 | {"batch_size":32,"seconds":4.6707463339553215} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-after-review-resume.log` | `63f648564486` | 2933 / 2932 | {"method":"encoder","chunks":1891840,"total":4345592,"reused":false,"elapsed_seconds":10852.29981562501} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-continuous-b32-t10.json` | `39e0a1960795` | 7175 / 1 | {"method":"encoder","device":"cpu","batch_size":32} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-continuous-b32-t10.log` | `d556d8cf04a8` | 8196 / 1021 | {"method":"encoder","device":"cpu","batch_size":32} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-continuous-post-snapshot.json` | `5108f99d8739` | 22673 / 1 | {"method":"encoder","device":"cpu","batch_size":32} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-continuous-post-snapshot.log` | `315a3d7c4e7c` | 25908 / 3235 | {"method":"encoder","device":"cpu","batch_size":32} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-continuous.json` | `86f21b3541e3` | 538 / 1 | {"method":"encoder","device":"cpu","batch_size":8} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-continuous.log` | `57a56b2747b6` | 611 / 73 | {"method":"encoder","device":"cpu","batch_size":8} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-shard1.json` | `9c5299b6c62d` | 34 / 1 | {"method":"encoder","device":"cpu","batch_size":8} |
| `work/deepseek-official-compat/work/acceptance/indexes/e5-cpu-shard1.log` | `f61a0a8961eb` | 35 / 2 | {"method":"encoder","device":"cpu","batch_size":8} |
| `work/deepseek-official-compat/work/acceptance/indexes/encoder-status-before.json` | `a7667cc1d486` | 8 / 1 | {"method":"encoder"} |
| `work/deepseek-official-compat/work/acceptance/indexes/full-bm25-quick-check.json` | `c270f03c7f77` | 23 / 1 | {"state":"passed","results_items":1,"elapsed_seconds":222.69445695803734} |
| `work/deepseek-official-compat/work/acceptance/indexes/full-bm25-quick-check.log` | `b9a2c20b2f90` | 19 / 19 | {"state":"passed","results_items":1,"elapsed_seconds":222.69445695803734} |
| `work/deepseek-official-compat/work/acceptance/indexes/full-corpus-quick-check.json` | `759666d1a5bf` | 23 / 1 | {"state":"passed","results_items":1,"elapsed_seconds":265.98188462498365} |
| `work/deepseek-official-compat/work/acceptance/indexes/full-corpus-quick-check.log` | `8f7ba2862646` | 17 / 17 | {"state":"passed","results_items":1,"elapsed_seconds":265.98188462498365} |
| `work/deepseek-official-compat/work/acceptance/indexes/full-route-readiness.json` | `7e4a7b0ae202` | 179 / 0 | 仅有指纹与行数 |
| `work/deepseek-official-compat/work/acceptance/indexes/index-acceptance-status.json` | `06e97595eb49` | 121 / 1 | {"checked_at_utc":"2026-11-15T06:50:54.329068+00:00","full_corpus_documents":100195,"full_corpus_source_chunks":4345592} |
| `work/deepseek-official-compat/work/acceptance/indexes/instruction-status-before.json` | `36fdf4b6205d` | 8 / 1 | {"method":"instruction"} |
| `work/deepseek-official-compat/work/acceptance/indexes/qwen-cpu-shard1-local-tokenizer.json` | `3bb982016538` | 34 / 1 | {"method":"instruction","device":"cpu","batch_size":1} |
| `work/deepseek-official-compat/work/acceptance/indexes/qwen-cpu-shard1-local-tokenizer.log` | `a3679ba60bc8` | 35 / 2 | {"method":"instruction","device":"cpu","batch_size":1} |
| `work/deepseek-official-compat/work/acceptance/indexes/qwen-cpu-shard1.log` | `7ce96417bfdd` | 50 / 0 | 仅有指纹与行数 |
| `work/deepseek-official-compat/work/acceptance/indexes/sparse-sql-benchmark.json` | `129ebfcc5021` | 281 / 0 | 仅有指纹与行数 |
| `work/deepseek-official-compat/work/acceptance/indexes/sparse-sql-benchmark.log` | `f550936d97dd` | 3 / 3 | {"seconds":13.53455333301099} |
