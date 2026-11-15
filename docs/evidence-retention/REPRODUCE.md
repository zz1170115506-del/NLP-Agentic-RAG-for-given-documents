# 证据保留修复：完整九题验收复现

本轮最终生产实现为 `a476ef7b062bb9a0deac0db54b5895daa5e30827`，运行源码SHA-256为`427d8f147b1084cdf54131797111ec03d1e699a3c3d37b7a35f0557854612559`。第一版`363d3f5f01dfebd048712becee0d9f58b6abd0ce`的九题完整运行也保留，未按题挑选不同版本合并成绩。

## 数据与配置

固定输入仍为原九题的仅`id/question`文件，SHA-256为`dd829d11a47ce9c4d7c150c0e75fbdbcf57341b5197f3221c162dfe00fb60ce9`。全量语料和BM25沿用[上轮语料移交](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)，路径为`data/course-full/documents.sqlite`及`indexes/course-full/`，不重新建立Qwen索引。

使用`configs/validation-review-bailian.yaml`，本地Git忽略的`.env`只需保留此前已经授权的百炼Key，不写入代码或命令行。模型为`deepseek-v4-flash-0731`，北京endpoint为`https://dashscope.aliyuncs.com/compatible-mode/v1`，实际请求`enable_thinking=false`；配置ID仍为`900fc3b95b775d2a`。源代码变更单独由runtime code hash绑定，不以同一config_id冒充同一实现。

每题限30,000个API已报告输入＋输出token、24,000个序列化消息字符、12步、24工具、每轮最多1,024输出token。检索器、top_k默认值、技能、系统提示、工具定义及停止规则均未改变。源码里没有题号/固定文档/目标答案选择规则；离线targets只用于运行结束后的审计。

## 从空状态完整运行

安装项目已有依赖后，在项目根目录执行：

```sh
PYTHONPATH=src:agent12 python scripts/run_retention_acceptance.py \
  --config configs/validation-review-bailian.yaml \
  --questions restored/inputs/nine-questions.jsonl \
  --baseline-metadata restored/baseline/prediction.jsonl.meta.json \
  --output outputs/new-retention-acceptance/prediction.jsonl
```

输出必须是全新路径。该脚本只读题目与原基线metadata，逐项核对输入、配置、语料、索引、技能；每题调用原生产`run_question`，从空state开始。它不读取旧答案、参考标签或事后坐标，不注入冻结上下文。每题真实结果先落盘，再检查身份/协议/来源；运行故障会停止后续调用，不能用有效弃答作为重刷理由。

九题全部结束后才评测：

```sh
PYTHONPATH=src:agent12 python scripts/evaluate_validation_review.py \
  --questions restored/inputs/nine-questions.jsonl \
  --predictions outputs/new-retention-acceptance/prediction.jsonl \
  --reference-source restored/v2/evaluation/selected-validation-reference-private.jsonl \
  --output outputs/new-retention-acceptance/evaluation
```

如仅复核现有结果，使用恢复包的`restored/v2/prediction.jsonl`即可，不需要再次调用API。九题验收不是课程100题正式提交；保持每条记录的严格校验，公开统计里的弃答数量不等同网络/程序失败数量。

## 独立检查实际可见证据

```sh
python scripts/audit_evidence_retention.py \
  --baseline restored/baseline/prediction.jsonl \
  --predictions restored/v2/prediction.jsonl \
  --targets restored/audit/targets-v2.json \
  --output work/new-retention-audit
```

`targets-v2.json`是事后诊断坐标；脚本不会把它送入模型。公共输出不含原题、答案和长原文；私有细节保留精确请求、工具文本和坐标。比较按实际`api_attempt.request.messages`，不把程序准备过但未发送的消息算成模型已见。片段ID消失与原文被其他较长原证据完整覆盖分别报告。

在保留Git历史及固定语料的checkout中，还可运行独立区间图检查；它不调用生产选择器、不读取标签，也不发API：

```sh
PYTHONPATH=src:agent12 python scripts/verify_retention_atomicity.py \
  --repo . --baseline-run restored/baseline --run-dir restored/v2 \
  --questions restored/inputs/nine-questions.jsonl \
  --output work/independent-retention-check
```

该完整身份检查使用Git比较核心文件与原提交，并核对本地语料指纹；只有源码ZIP而没有Git历史/语料时，应先恢复它们。已完成的公开检查结果可直接阅读，无需重复调用模型。

测试命令：

```sh
python -m pytest -o addopts='' -q
python -m ruff check src/rag_agent/agent/context.py \
  scripts/run_retention_acceptance.py scripts/audit_evidence_retention.py \
  tests/test_context_retention.py tests/test_context_overlap_tail.py \
  tests/test_context_evidence_groups.py tests/test_evidence_retention_audit.py
```

## 加密附件恢复

下载本轮Release资产，先核对`SHA256SUMS`，以本地单独保存的`retention.key`解密：

```sh
python scripts/handoff/handoff_crypto.py decrypt \
  --manifest download/ENCRYPTED_VOLUMES.json \
  --key-file /your/local/retention.key --output decrypted
python scripts/handoff/handoff_archive.py verify \
  --volumes decrypted/VOLUMES.json --extract extracted
python scripts/restore_validation_review_evidence.py \
  --extracted extracted --output restored
```

加密包逻辑目录：`baseline/`为未修改的原九题基线，`v1/`、`v2/`为两个完整九题运行及各自评测，`inputs/`为仅题号/问题输入，`audit/`为独立核查与事后坐标，`source/`为两版冻结核心源码包。所有原题、参考答案、非空预测和长原文均只在加密包中；API Key及解密Key不上传。完整大语料沿用之前的数据包，不重复发布。

公开源码ZIP保留仓库历史已有的公开`data/test.jsonl`；本轮没有使用隐藏测试标签，也不宣称整个源码ZIP完全不含任何题目。实际远端commit、密文及源码ZIP的SHA在Release移交清单中。
