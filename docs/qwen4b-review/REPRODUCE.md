# Qwen3-Embedding-4B 压缩检索与九题复测

从本次发布的代码提交建立工作目录，安装项目的 retrieval 与 dev 依赖。数据采用[此前的固定语料与 BM25 移交包](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)。恢复 `data/course-full/documents.sqlite` 与 `indexes/course-full/sparse.sqlite`。九题输入和 v2 运行元数据也可以从[上次九题发布](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/evidence-retention-fix-20261115)恢复。输入只包含题号与题目。

## 下载与本地模型自检

从[官方模型仓库](https://huggingface.co/Qwen/Qwen3-Embedding-4B/tree/5cf2132abc99cad020ac570b19d031efec650f2b)下载固定提交。在项目根目录执行下列命令。自检使用两条自拟常识查询，不使用百炼。

```sh
hf download Qwen/Qwen3-Embedding-4B \
  --revision 5cf2132abc99cad020ac570b19d031efec650f2b \
  --local-dir models/qwen4b --include '*.safetensors' '*.json' '*.txt'
PYTHONPATH=src:agent12 python scripts/check_qwen4b_snapshot.py \
  --snapshot models/qwen4b --device mps --output work/qwen4b-smoke.json
```

编码器逐文件核验权重与分词器，使用最后一个有效 token 的表示。只有查询带检索指令。每个文档片段先得到 2560 维向量，取前 256 维、归一化，再按行量化为带一个 float32 比例尺的 int8 向量。查询保留 256 维浮点数，按余弦相似度排序。需要换 CUDA 时，在运行配置和自检命令中将设备改为 `cuda`，另用新的输出目录记录实际设备及运行身份。

## 完整九题

配置文件为 `configs/qwen4b-compressed-nine.yaml`。将已授权的百炼北京凭据放在本地忽略的 `.env` 中，设为仅当前用户可读写。问答模型使用 `deepseek-v4-flash-0731`，工具查询只读取课程固定语料。每次查询先用全库 BM25 取前 32 个片段，由 4B 编码并排序，最终按工具请求深度返回原文。若 4B 路径失败，保留错误记录。候选池外的段落须由后续不同查询检回。

```sh
PYTHONPATH=src:agent12 python scripts/run_qwen4b_nine.py \
  --questions restored/inputs/nine-questions.jsonl \
  --baseline-metadata restored/v2/prediction.jsonl.meta.json \
  --output-dir outputs/qwen4b-nine-fresh
```

首轮使用全新输出目录，`--resume` 可续接同一源码、同一配置和同一输入的中断运行。九题各自从空状态开始，使用同一模型实例在内存中复用已经编码的原文。调试开关 `qwen4b_compare_floats` 为同一批候选另外计算原始浮点、截维浮点和压缩排名。额外保存的浮点参考向量只用于比较。关闭该开关后只缓存压缩文档向量。

九题结束后再读参考答案：

```sh
PYTHONPATH=src:agent12 python scripts/evaluate_validation_review.py \
  --questions restored/inputs/nine-questions.jsonl \
  --predictions outputs/qwen4b-nine-fresh/prediction.jsonl \
  --reference-source restored/v2/evaluation/selected-validation-reference-private.jsonl \
  --output outputs/qwen4b-nine-fresh/evaluation
```

逐次请求、模型回复、查询和排名保存在证据包的 `prediction.jsonl`、`events.jsonl`、`retrieval.jsonl` 和 `question-executions.jsonl` 中。判定模型是否看到证据时以实际发送的请求为准。回答条件核查需要对照原文的对象、时间和关系。只在所有运行结束后使用诊断坐标复核，不把事后坐标提供给搜索过程。

## 复核已发布结果

从本轮发布页下载密文、收据和 `SHA256SUMS`。在本地保存解密密钥，使用带 `cryptography` 的 Python。在源码检出目录执行：

```sh
python scripts/qwen4b_review/qwen4b_handoff.py verify \
  --repo . --crypto-python /path/to/crypto-venv/bin/python \
  --assets download --expected-receipt docs/qwen4b-review/QWEN4B_EVIDENCE_RECEIPT.json \
  --key /path/to/qwen4b-evidence.key --work work/new-restore
```

新包恢复后的 `restored/baseline-v2/` 和 `restored/run/` 分别保存上一轮及本轮运行。若从本包重新在线运行，上面的命令将 `restored/v2/` 换成 `work/new-restore/restored/baseline-v2/`，并使用恢复出的 `inputs/nine-questions.jsonl`。直接复核已完成的两组结果无需再次调用百炼：

```sh
python scripts/qwen4b_review/compare_qwen9.py --repo . \
  --baseline work/new-restore/restored/baseline-v2/prediction.jsonl \
  --candidate work/new-restore/restored/run/prediction.jsonl \
  --coordinates scripts/qwen4b_review/diagnostic-coordinates.json \
  --output work/new-qwen4b-audit
```

`vectors.npz` 保存本次运行中的实际压缩文档向量。以 `numpy.load(path, allow_pickle=False)` 读取，其中 `doc_ids` 与 `chunk_ids` 标记每行，`codes` 为 256 列 int8，`scales` 为每行一个 float32。文件还包含标识符和 NumPy 容器开销，因此报告分别给出净载荷和实际文件大小。

四档离线重放复用每次真实查询和当时的候选集，只需本机模型及恢复出的真实记录。可使用以下命令查看路径参数。

```sh
python scripts/qwen4b_review/compare_dimensions.py --help
```
