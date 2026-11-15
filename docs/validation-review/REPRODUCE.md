# 本轮复现与证据恢复

本轮固定九道官方验证题：960、1035、64、231、390、58、1155、1066、788。原始题目和标签在加密附件；模型输入仅含`id`及`question`。以下命令在项目根目录执行，使用Python3.11–3.13。所有`run/`、`restored/`路径均为可自选本地目录，不是公开数据地址。

## 1. 只读核对现成证据

从本轮Release下载`review-evidence.*.aead`、`ENCRYPTED_VOLUMES.json`及`SHA256SUMS`。从本地单独保管的密钥文件解密；不能把密钥放进公共上传目录。安装`cryptography==50.0.2`后执行：

```sh
python scripts/handoff/handoff_crypto.py decrypt \
  --manifest download/ENCRYPTED_VOLUMES.json \
  --key-file /your/local/review.key --output decrypted
python scripts/handoff/handoff_archive.py verify \
  --volumes decrypted/VOLUMES.json --extract extracted
python scripts/restore_validation_review_evidence.py \
  --extracted extracted --output restored
```

加密归档内部以`detailed/`存放文件，`PATH_MAP.json`给出归档路径→逻辑路径及每文件SHA-256。恢复命令核对路径和全部文件后恢复原相对结构，包括`drafts/group-b/private/`、`drafts/group-c/private/`等。归档没有`.env`或API key。`restored/run/`包含新基线、旧失败尝试、全部成对请求响应及评测；`restored/history/`包含旧预测、旧输入/参考、元数据与冻结源码包；`restored/drafts/`包含逐题原文和离线检查。

完整固定语料、BM25和旧运行基础从[program-acceptance-20261115](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)恢复，沿用其独立密钥和恢复说明。本轮不再复制6GB语料。核对语料指纹`ea8764233b0d4a76d050842e290805a0f154858084dfd0430ba8c0d9c555025f`和100,195文档/4,345,592片段。E5、Qwen部分索引不属于本轮检索器。

公共台账可从现成私有运行目录重新导出，不调用API：

```sh
python scripts/summarize_validation_review.py \
  --run-dir restored/run --out work/review-public-summary.json
```

## 2. 百炼九题基线

先把固定语料和BM25放在专用配置的`data/course-full/`及`indexes/course-full/`，安装项目依赖：`python -m pip install -e '.[retrieval,dev]'`。以`configs/validation-review-bailian.yaml`为准：`course_pinned`、30,000 token、24,000字符、12步、24工具。运行时核心身份见本目录`initial-identity.json`和原预测`.meta.json`；最终交付提交只有附加诊断/文档，不改变本轮核心运行源码。

在Git忽略的`.env`中填自己的Key，设置权限600；不要复制历史旧Key：

```dotenv
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=deepseek-v4-flash-0731
LLM_MODEL_VERIFIED=true
LLM_MODEL_VERIFICATION_NOTE="2026-11-15: Alibaba Cloud Model Studio Beijing GA 0731, https://help.aliyun.com/zh/model-studio/deepseek-api"
LLM_API_KEY=<本地填写，不提交>
```

清除当前shell中旧的`LLM_*`覆盖变量后运行；Settings载入本地`.env`，实际请求中的`enable_thinking`必须为false。`check-config`不会打印Key。需要重新付费实测时使用**全新**输出目录：

```sh
chmod 600 .env
PYTHONPATH=src:agent12 python -m rag_agent.cli check-config \
  --config configs/validation-review-bailian.yaml --live
PYTHONPATH=src:agent12 python -m rag_agent.cli predict \
  --config configs/validation-review-bailian.yaml \
  --input restored/inputs/validation-review-questions.jsonl \
  --output outputs/new-validation-review/prediction.jsonl
```

运行全部结束后才读取标签进行评测：

```sh
PYTHONPATH=src:agent12 python scripts/evaluate_validation_review.py \
  --questions restored/inputs/validation-review-questions.jsonl \
  --predictions outputs/new-validation-review/prediction.jsonl \
  --reference-source restored/history/data/validation.jsonl \
  --output outputs/new-validation-review/evaluation
```

九题诊断不是课程100题最终提交。这里保留逐记录formal、模型、用量、来源检查，同时按九题输入校验完整性；没有降低原课程批量100题数量要求。遇到API故障用`scripts/recover_predictions.py --dry-run`核查，再去掉`--dry-run`仅重试不合格条目；不要把有效弃答误当运行失败重刷。恢复时源码、配置、题目、语料、索引身份须全等，原失败会进入`.attempts.jsonl`。

## 3. 五组冻结请求成对诊断

恢复包中的`drafts/paired-run-plan.json`引用相邻group目录里的准备请求。先只检查输入不调用模型：

```sh
PYTHONPATH=src:agent12 python scripts/run_validation_review_pairs.py \
  --config configs/validation-review-bailian.yaml \
  --plan restored/drafts/paired-run-plan.json \
  --output outputs/new-validation-pairs --check-only
```

去掉`--check-only`才产生十次真实请求，输出必须是新目录。脚本不读标签；只准改变`messages`中状态快照的`evidence`数组，两臂用完全一致的提供商/模型/关闭thinking适配，且不提高上下文预算。为避免隐式重复，诊断运输配置单独设置max_retries=0并登记其ID。64是新百炼最终状态；其余是历史冻结状态在新百炼上重新调用。1066保留工具权限，所得search仅用于离线下一动作分析，不执行完整Agent回合。

实际响应已保存，可离线重验，**无需再次付费**。第二组验证器需在独立进程指向旧冻结源码repo，不能先导入新repo同名模块：

```sh
python scripts/validation_review/group_b/validate_paired_response.py \
  --repo /your/restored/historical-repo \
  --pairs restored/drafts/group-b/paired-final-diagnostics \
  --case 58 --arm treatment \
  --response restored/run/paired-diagnostics/58/treatment.api-attempt.json \
  --out work/58-treatment-validation.json
```

231、390及control臂使用对应参数；历史repo需同版本核心源码及固定`data/course-full/documents.sqlite`。64的`validate_e4_pair.py`核对实际请求与准备消息、生产final校验、当前请求可见引用和原文坐标。1066的`audit_retention_pair.py`核对两臂唯一变化并只读BM25执行真实返回的4个query；其输出没有终局EM。有命令行入口的脚本可用`--help`查看路径参数；B组部分渲染/覆盖检查器相对脚本自身目录定位，应先把完整`restored/drafts/group-b/`复制到独立的`work/`工作副本，再在副本内执行，恢复原件只读保留。

## 4. 离线历史重放和公开限制

`scripts/validation_review/group_a/`提供原query top5/top20、题意变体及事后定位重放；`group_b/`复现15次实际上下文及诊断保留hook；`group_c/`提供逐事件核查、14条条件查询、12次上下文重放及新基线追加。脚本需要恢复的精确标签/计划/原文；参考辅助只在离线阶段使用，计划文件保存在加密包中，不把答案常量写进公共脚本。

历史repo可从Git提交`dab7646158fef729c3bf3e0f37b7f302727fc568`恢复；冻结源码ZIP另附于加密证据。需要调用`git show`的B组重放脚本要求有该Git对象，单纯解压源码没有Git历史；从公开仓库fetch该提交即可，不需要新API调用。所有相对输出应指向独立目录，保留已交付证据原件。

实际执行时的逐组原始脚本字节保存在加密包`drafts/`。公开B组脚本另做了Ruff排版、拆分import及等价函数声明整理；因此脚本文件hash可能与当时manifest不同，冻结hook的权威字节以加密包为准。公共验证器已针对六条真实响应重新运行并与原验证结果逐项相等；不要用排版后的hook覆盖已冻结manifest再声称hash未变。

本轮源代码ZIP由最终交付commit的`git archive`生成。它保留仓库历史已跟踪的公开`data/test.jsonl`，因此不宣称ZIP完全没有题目；本轮新增的九题原题、参考、预测、长原文和真实请求全部只在加密证据中。`.env`、API key、解密key不在源码ZIP或公共Release。
