> 资料快照，来源提交 `0eee841`。[原始文件](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/0eee841fa128cef160f7fde8f8ab483ff28b6428/docs/qwen4b-2560-review/REPRODUCE.md)。采集于 2026-11-17（香港时间）。

# 2560 维 int8 九题复测与复核

本轮以 `codex/qwen4b-compression-nine` 已发布提交 `d2ad11129cca59217b4593aae2c5b37103451ab6` 为起点。两轮都先从完整语料做 BM25 关键词搜索，再让本机 Qwen 对每次搜索的 32 个候选片段打分，最后由百炼北京的问答模型根据实际工具结果继续提问或作答。

## 检查已发布的运行记录

从[本轮 GitHub Release](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/qwen4b-2560-int8-nine-20261117)下载签收文件、密文分片和 `SHA256SUMS` 至 `download/`。在本轮的代码检出目录操作。下面的 `CRYPTO_PYTHON` 指向安装了 `cryptography` 的 Python，`LOCAL_KEY` 指向单独保存在本机的解密文件。解密后的逐题原文、模型请求和参考答案都保存在本地。

```sh
python scripts/qwen4b_review/qwen4b_handoff.py verify \
  --repo . --assets download \
  --expected-receipt docs/qwen4b-2560-review/QWEN4B_EVIDENCE_RECEIPT.json \
  --crypto-python "$CRYPTO_PYTHON" --key "$LOCAL_KEY" --work work/verify-2560
```

还原目录 `work/verify-2560/restored/` 下的 `baseline-int8-256/` 和 `run/` 分别对应两次真实问答。准备同一份课程语料库 `data/course-full/documents.sqlite`，就能把所有检索排名、实际工具回包和最后请求与原文坐标重新对齐。此步骤在本地执行。

```sh
RESTORED=work/verify-2560/restored
export PYTHONPATH=src:agent12
python scripts/qwen4b_review/compare_dimension_runs.py \
  --baseline "$RESTORED/baseline-int8-256" --candidate "$RESTORED/run" \
  --output work/comparison.json --markdown work/comparison.md
python scripts/qwen4b_review/compare_dimension_evidence.py \
  --baseline "$RESTORED/baseline-int8-256" --candidate "$RESTORED/run" \
  --documents data/course-full/documents.sqlite --output work/evidence-trace.json
```

## 再发起一次真实问答

需准备两轮共用的完整文档库和 BM25 索引、配置内指定版本的 Qwen 权重、本机可用的 MPS 设备，以及此前配置的百炼凭据。环境和目录布局见[前轮安装说明](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/0eee841fa128cef160f7fde8f8ab483ff28b6428/docs/qwen4b-review/REPRODUCE.md)。新运行会产生 API 用量，其后续搜索及输出可能随服务端回复变化。

```sh
RESTORED=work/verify-2560/restored
export PYTHONPATH=src:agent12
python scripts/run_qwen4b_nine.py \
  --config configs/qwen4b-2560-int8-nine.yaml \
  --questions "$RESTORED/inputs/nine-questions.jsonl" \
  --baseline-metadata "$RESTORED/baseline-int8-256/prediction.jsonl.meta.json" \
  --output-dir outputs/qwen4b-2560-fresh
python scripts/evaluate_validation_review.py \
  --questions "$RESTORED/inputs/nine-questions.jsonl" \
  --predictions outputs/qwen4b-2560-fresh/prediction.jsonl \
  --reference-source "$VALIDATION_JSONL" \
  --output outputs/qwen4b-2560-fresh/evaluation
```

`VALIDATION_JSONL` 指向课程原始验证集。运行器只读题号与题干；评测命令在九题全部结束后单独读标准答案。每组的 `retrieval.jsonl` 记录排序及返回片段，`events.jsonl` 记录实际 HTTP 请求与应答，`vectors.npz` 保存参与实际检索的候选片段向量及缩放因子。
