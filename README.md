# NLP-Agentic-RAG-for-given-documents

COMP5423 2026 Fall **Skill-Augmented Search Agent**：从指定固定文档集合检索证据，由 DeepSeek-V4-Flash 通过工具进行多轮问答。现有代码包含三类真实检索实现、独立状态和上下文管理、两个原创 skills、Streamlit 网页、批处理、评测与打包入口。

这是一份可继续协作的功能基线。离线演示可直接运行；真实模型调用需要密钥。完整语料索引、100 题真实验证、最终报告和视频尚未完成，不能把本仓库等同于已完成课程最终提交。

- [RAG 设计思路（中文，可分享给组员）](docs/RAG_设计思路.md)
- [Agent 设计思路（中文，可分享给组员）](docs/Agent_设计思路.md)
- [实际验证记录](docs/validation.md) · [要求与代码映射](docs/requirements.md)
- [模型服务配置与核对依据](docs/provider.md) · [协作边界](docs/collaboration.md)
- [本地重排与真实语料两轮评估](docs/2026-11-11--local-rerank--r02--round-review.md)：97 篇真实文档、20 道冻结诊断题；默认仍关闭重排。

可选本地重排由 `rerank_enabled` 控制，在 hybrid 的片段 RRF 之后执行。`candidate_depth: null`
保持旧候选深度；`configs/rerank-eval-b.yaml` 是本次小样本建议配置（每路 50，关闭重排），
`configs/rerank-eval-d.yaml` 是每路 50、重排前 10 的可选配置。它们指向独立的小样本索引，
不能代替全量配置。安装后可先执行 `python scripts/smoke_rerank.py` 验证接口与排序逻辑，
该入口无需模型或 API，并明确标记神经检索/评分测试替身。

## 1.2 Agent 接入版

负责 1.2 的实现位于 [`agent12/`](agent12/)，通过统一 `search(query, top_k)` 调用本仓库的 1.1 检索。支持结果驱动的多轮搜索、空结果恢复、片段级引用和保留工具配对的上下文压缩。`top_k` 按片段计数，同文档不同片段分别保留。

从仓库根目录运行无需 API 的 70 项 Agent/接入测试，并建立合成 BM25 样例：

```bash
cd agent12
python -m pip install -r requirements-peer.txt
python -m unittest discover -s tests -v
python scripts/prepare_peer12.py --peer-project ..
```

真实模型开发入口、索引配置与完整步骤见 [1.2 运行说明](agent12/PEER_INTEGRATION.md)。已使用真实 DeepSeek Flash API 和本仓库 BM25 验证四类合成案例，记录见 [验证摘要](agent12/verification/peer-summary.json)。这些是开发联调，正式课程模型与全量语料的评测仍待完成。

## 1. 安装

在项目根目录执行。支持 Python **3.11–3.13**，本次验证环境是 macOS arm64 / Python 3.12.14。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --cache-dir .cache/pip '.[dev]'
python -m pytest
```

基础安装无需推理密钥或模型权重，包含网页、BM25、评测及测试。需要两类神经检索时再安装：

```bash
python -m pip install --cache-dir .cache/pip '.[retrieval,dev]'
```

`pyproject.toml` 是依赖的唯一直接定义；`requirements.txt` 引用它。`requirements-lock-py312-macos.txt` 记录本机实际安装的完整版本，适合同平台复现，不保证其他系统完全通用。修改源码后重新执行安装命令；测试直接读取 src。Windows 使用 `.venv\Scripts\activate` 激活。

主要版本：Pydantic 2.12.5、Streamlit 1.51.0、NumPy 2.3.5、httpx 0.28.1、Transformers 4.57.3、PyTorch 2.9.1。所有下载缓存、文档、索引和运行输出均放在项目内部且不提交 Git。

## 2. 无密钥快速启动

以下语料和问题均为自写虚构测试数据，不包含课程 benchmark 内容。

```bash
rag-agent prepare --config configs/demo.yaml --source tests/fixtures/corpus.jsonl
rag-agent index --config configs/demo.yaml --methods sparse
rag-agent ask --config configs/demo.yaml \
  'Where is the university attended by the architect of Lumen Observatory located?'
python -m streamlit run src/rag_agent/web_app.py \
  --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
```

打开 **http://127.0.0.1:8501**，选择 `configs/demo.yaml`，提交默认问题。应看到 `Northport`、文档片段、所选 skills、工具操作及计数。网页使用 `agent.loop.run_question`，与 CLI 共用推理流程；资源缓存避免每题重新加载模型/索引。更换或重建索引后重启网页以清除资源缓存。

离线 demo 是读取实际工具返回的规则控制器，目的是检查数据流和界面；它不是 LLM，也不能代表真实 Agent 表现。`001` 展示前序结果驱动的两跳检索，`002` 展示无需 skill 的简单题，`003` 展示空结果恢复和诚实失败。demo 的 API tokens 为 0，因为未发生 API 调用。

```bash
rag-agent predict --config configs/demo.yaml \
  --input tests/fixtures/questions.jsonl --output outputs/demo_prediction.jsonl
rag-agent validate --config configs/demo.yaml \
  --input tests/fixtures/questions.jsonl --predictions outputs/demo_prediction.jsonl
```

重复执行 predict 会跳过已保存题目；加 `--rerun-failed` 仅重跑失败题并保存旧尝试。旧输出与输入/配置不一致时会拒绝恢复，应使用新的输出路径。

## 3. 正式模型配置

**不要直接把 `api.deepseek.com` 的 `deepseek-v4-flash` 旧别名当成原 V4-Flash。** 2026-11-10 核对的官方文档说明它已转至 V4.1。本项目会拒绝这个已知不符合课程 backbone 的服务地址。

本次核对 OpenRouter 目录后，提供 `configs/openrouter.yaml`：

- endpoint：`https://openrouter.ai/api/v1`
- model ID：`deepseek/deepseek-v4-flash-0731`
- 目录显示 GA DeepSeek V4 Flash 0731，并提供 `tools` / `tool_choice`。

2026-11-11 已完成真实小语料上的 5 题 B/C 配对，共 74 次 HTTP 200，响应模型 ID 匹配；最终答案仍受 JSON/引用坐标校验失败影响。API 与检索实际范围见 [provider.md](docs/provider.md) 和[两轮实验报告](docs/2026-11-11--local-rerank--r02--round-review.md)。

```bash
cp .env.example .env
# 在本地编辑 .env，仅填写自己的 LLM_API_KEY；不要提交或在截图中展示。
rag-agent check-config --config configs/openrouter.yaml --live
```

也可通过 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_MODEL_VERIFIED=true`、`LLM_MODEL_VERIFICATION_NOTE` 覆盖配置；后者记录当前服务文档 URL、日期和原模型映射。不同厂商的 deployment ID 可以是不同名称，但必须确认实际是同一 backbone。密钥缺失或模型不符会明确失败，不会切换成 demo。

## 4. 真实课程数据与索引

固定语料：[Tevatron/browsecomp-plus-corpus](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus)，`train` split，数据卡列出 100,195 文档，原字段 `docid/text/url`。导入记录实际 revision、字段、数量和语料指纹。检索只使用导入文档，来源 URL 仅供溯源。

先做少量测试，不会在启动网页时自动下载全语料：

```bash
rag-agent prepare --config configs/corpus-smoke.yaml --hf --limit 5
rag-agent index --config configs/corpus-smoke.yaml --methods sparse
# 也可以导入本地语料
# rag-agent prepare --config configs/openrouter.yaml --source data/corpus.jsonl
```

全量导入是明确操作（可能需要较长时间和大量磁盘空间）：

```bash
rag-agent prepare --config configs/openrouter.yaml --hf
rag-agent index --config configs/openrouter.yaml --methods sparse encoder instruction
rag-agent search --config configs/openrouter.yaml 'your factual question' --method hybrid
```

若 macOS 受限环境在流式导入时报告共享内存权限错误，可单独运行 `USE_TORCH=0 rag-agent prepare --config configs/corpus-smoke.yaml --hf --limit 5`。这只关闭数据读取进程不需要的 PyTorch 集成；另一次索引命令仍使用真实 PyTorch 模型。

小样本使用独立的 corpus-smoke 配置，全量使用 openrouter 配置，避免相互覆盖。导入是流式的，同一来源与范围的中断任务可恢复；改变来源、limit 或分块设置时应创建新的 store_path 和 index_dir。不能把有限样本原地改成全量后继续使用旧索引。向量构建分批写入持久化分片并支持中断恢复；只有与 manifest 完全兼容的已有分片才会重用。

| 方法 | 实际实现 | 编码约定 |
|---|---|---|
| sparse | SQLite FTS5 BM25，磁盘倒排索引 | unicode61；查询词用 OR 匹配，分数取负后越大越好 |
| encoder | intfloat/e5-small-v2 | query/passage 前缀，attention-mask 均值池化，L2 归一化 |
| instruction | Qwen/Qwen3-Embedding-0.6B | Instruct + Query 查询模板，左侧 padding，最后有效 token 池化，L2 归一化 |
| hybrid | 片段级 RRF 排名融合 | 每路同一片段只计一次，同一文档的不同片段可分别返回 |

E5 文档前缀的实际字符串是 `passage: `。向量索引采用 NumPy 分片与内存映射，避免一次加载所有向量。代价是查询仍需精确扫描全部分片；本轮未测全量延迟，后续可在保留相同协议的基础上换成近似向量索引。

长文档先按 Unicode 字符分块，保留 `doc_id/chunk_id/offset/url`；超出模型 token 长度的片段继续拆开，保留精确原文位置，不静默丢弃尾部。默认 E5/Qwen 模型约 33M/0.6B 参数；Qwen 的 CPU float32 权重内存约 2.4 GB，另需激活和框架内存。全语料索引可能占用数十 GB，应先评估存储空间。`device` 支持 cpu/mps/cuda/auto。

显式运行真实 embedding smoke（会下载两种模型）：

```bash
python scripts/smoke_retrieval.py --methods sparse encoder instruction --device cpu
```

组内 Agent 可使用 [同步检索后端接入说明](docs/peer_backend.md)。检索的 `top_k` 按原文片段计数，结果可以包含相同的 `doc_id`。

## 5. 从原始题目生成预测与评测

课程验证文件可单独下载，参考答案仅由 evaluator 读取：

```bash
python scripts/fetch_validation.py
rag-agent predict --config configs/openrouter.yaml \
  --input data/validation.jsonl --output outputs/validation_prediction.jsonl
rag-agent evaluate --config configs/openrouter.yaml \
  --input data/validation.jsonl --predictions outputs/validation_prediction.jsonl
```

题目读取边界只构建 `Question(id, question)`，不会将参考 `answer` 交给 Agent。下载脚本默认固定已核对的数据 commit；不会下载上游隐藏答案。课程测试文件由老师另行发布，本仓库不假定其已可用。

获得原始 `data/test.jsonl` 且完成索引和模型配置后，同一程序无需逐题改代码：

```bash
rag-agent predict --config configs/openrouter.yaml \
  --input data/test.jsonl --output outputs/test_prediction.jsonl
rag-agent validate --config configs/openrouter.yaml \
  --input data/test.jsonl --predictions outputs/test_prediction.jsonl --formal
# 如有失败，检查错误、修复配置后选择新输出，或在配置不变时重试：
rag-agent predict --config configs/openrouter.yaml \
  --input data/test.jsonl --output outputs/test_prediction.jsonl --rerun-failed
```

正式验收要求输入恰好 100 题、ID/题目全覆盖、唯一性、真实模式与模型元数据、完整调用与返回配对、API usage 及实际计数一致，并拒绝 demo/脚本/失败或统计不完整的结果。验收通过仅表示通过项目内检查，不替代教师验收，也不能保证答案正确。

输出每条记录仅含课程六字段。附加运行状态、配置、选择事件和裁剪信息放在 `trajectory` 内；每次请求保留精简上下文，完整历史不被删除。`tool_calls` 统计每个模型发出的调用（含失败）；混合检索内部的三路操作只算一次。自动内部 skill 选择/加载不计作模型工具调用，模型显式 `load_skill` 则计数。API tokens 仅累计服务返回的 `usage.total_tokens`；未知用量使运行不具备正式资格。

Normalized EM 依次转小写、去英文标点、移除英文冠词 a/an/the、合并空白，再完全比较。报告显示完成/失败数、EM、工具调用、API tokens 和配置标识；没有其他组数据，不计算课程相对排名。

## 6. 工具、skills 与实验开关

默认 **4 种实际可调用工具**：`search`、`open_document`、`find_in_document`、`load_skill`。恰好一个检索工具。每个工具都有参数、输出和错误 schema，注册表同时生成模型协议和 [工具 schema 文档](docs/tool_schemas.json)。`rag-agent tools` 可重新查看。

两个原创技能：多线索拆解 `multi-clue-decomposition` 和检索恢复 `search-recovery`。启动只读 YAML 元信息；自动路由依据问题/停滞状态选中后加载正文，模型也可通过 `load_skill` 加载未活动技能。正文真正进入后续请求，不是只显示标签。关闭 skills 时只暴露 3 种工具。

配置包含 top-k、RRF、分块、批次、模型及版本、设备、上下文字符上限、轮数、工具数、API tokens 与超时预算。字符预算用于控制上下文大小，不冒充 API token 数。

`configs/ablation-*.yaml` 提供单步、无上下文管理、无 skills、单类检索六种对比。所有配置使用同一 pipeline；真实服务设置用 `.env` 提供。单检索配置会限制模型使用该方法。无上下文管理是专供对比的消融选项，正式默认开启管理。单步限制一次检索；若模型仍要求第二次，则明确失败而不伪造答案。尚未填入任何虚构实验结果。

## 7. 结构与协作

```text
src/rag_agent/
  schemas.py / config.py      公共数据协议与配置
  data/ / retrieval/          固定语料、分块、索引和融合
  tools/ / llm/               工具注册和服务适配边界
  agent/ / skills/            状态、上下文、迭代和动态技能
  evaluation/                批处理、格式验收和独立 EM
  runtime.py                 网页/CLI 共用资源构造
  cli.py / web_app.py         两种交互入口
skills/                      两个原创 SKILL.md
configs/ tests/ scripts/     实验设置、合成测试、smoke/打包
```

结构复核后保留上述边界，将资源构造集中到 `runtime.py`、协议集中到 `schemas.py`、工具 schema 与分发集中到注册表，减少网页与 CLI 分叉。详细数据流见两份设计文档；建议分工见 [collaboration.md](docs/collaboration.md)。

## 8. 课程打包与下一阶段

先生成明确标记的源码草稿包：

```bash
python scripts/package_course.py --draft --group Group-X --output outputs/Group-X-source-draft.zip
```

正式包必须包含真实预测、至少四页的正式报告 PDF、五分钟以内的 MP4；缺一项则拒绝生成：

```bash
python scripts/package_course.py --group Group-X --output outputs/Group-X.zip \
  --questions data/test.jsonl --predictions outputs/test_prediction.jsonl \
  --report outputs/Group-X-Report.pdf --video outputs/Group-X-Video.mp4
```

包内包含 `Group-X/test_prediction.jsonl`、可安装的 `code/`、报告及视频。打包检查文件存在、扩展名及预测完整性；页数、视频时长、内容质量和个人签名需组员最终核对。不会制造缺失报告、视频或预测。不要把源码草稿包当正式作业上传。

下一阶段：先修复真实轨迹中的 Agent 最终 JSON/引用 offset 正确性，再做更完整语料与官方验证集对照 → 测试集预测 → 官方 [Overleaf 模板](https://www.overleaf.com/read/wdbsnbtqwcrv#5382c5) 报告 → 演示视频。报告至少四页（不含参考文献及声明），真实贡献合计 100%，各人签名；截止为 2026-11-26 23:59 香港时间。
