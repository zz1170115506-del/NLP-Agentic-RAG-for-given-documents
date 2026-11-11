# 验证记录

## 2026-11-11 片段检索与组内后端

完整测试 50 项通过，Ruff 检查通过。回归验证覆盖真实 SQLite BM25 返回同文档多片段，两条向量路径使用合成向量跨分片验证片段保留，RRF 合并同一片段，以及后端返回带 Unicode 原文坐标的结果。真实 embedding 质量、同僚 Agent 的上下文联调和全量测试不在这次验证范围内。接入方式见 [同步检索后端](peer_backend.md)。

重新安装构建后的包，从 CLI 导入合成语料并建立 BM25 索引，再以 `RAG_BACKEND_CONFIG` 加载工厂。确认能返回同文档的两段命中、分页读取原文和定位字面匹配。

## 2026-11-10 基线验证

日期：2026-11-10，香港时间。以下区分代码实现、离线测试、真实 embedding 和真实 LLM；没有把合成题结果当作课程成绩。

## 环境与安装

- macOS arm64，Python 3.12.14，SQLite 3.53.1。
- 直接依赖版本见 `pyproject.toml`；实际完整安装快照见 `requirements-lock-py312-macos.txt`。
- 已实际安装基础、检索、开发依赖；`pip check` 无损坏依赖。
- 本机 Python 会忽略带 macOS hidden 属性的 editable `.pth`，因此最终采用普通安装 `python -m pip install '.[retrieval,dev]'`；测试使用 `src` 路径。代码改动后需要重新安装。
- 无 `LLM_API_KEY`；没有调用付费推理 API，没有运行 100 题实验。

## 已执行与结果

| 检查 | 实际范围与结果 |
|---|---|
| `python -m pytest` | **48 passed**：检索 9、Agent 20、评测/打包 16、网页/配置 3 |
| `python -m ruff check src scripts tests` | 通过 |
| `python -m pip check` | 无损坏依赖 |
| BM25 导入/建索引/查询 | 3 篇合成文档通过，文档级去重与精确 offset 有测试 |
| E5 真实模型 | CPU 实际编码、持久化、重新加载、查询；3 篇合成文档，384 维 |
| Qwen3 真实模型 | CPU 实际 instruction 编码、持久化、重新加载、查询；3 篇合成文档，1024 维 |
| 真实课程语料 | 5 篇文档导入为 14 个片段，BM25 建索引通过；修复流式关闭后另用 2 篇文档（7 片段）确认进程正常退出 |
| CLI 单题 | 合成多跳题得到 Northport，5 轮、4 次工具调用、0 API tokens；模式明确为 demo |
| CLI 批量 | 3 题，2 题完成、1 题证据不足；9 次工具调用、0 API tokens |
| 断点续跑/失败重跑 | 重复运行跳过 3 条；失败重跑只处理 1 条，旧尝试保存至 archive；输入/配置变更会拒绝恢复 |
| 正式验收拒绝 | demo、3/100 覆盖、缺 usage、缺证据、错误模型、注入 provider、畸形轨迹等不被接受 |
| 网页 | Streamlit 8501 启动，AppTest 提交真实表单得到答案；浏览器实际点击后看到 Northport、5/4/0 统计和原文证据；切换配置清除旧结果 |
| 安装与源码草稿包 | 实际解压、构建 wheel、隔离安装项目代码，再运行 prepare/index/predict/validate；复用了现有锁定依赖，不等同于在空机器重新下载全部依赖 |

测试覆盖的重点包括：原始字符串 ID 与 URL 保留、长文档位置、持久化兼容性、损坏分片和断点恢复、三方法融合去重；一个检索工具与多个支持工具；前序结果驱动的后续搜索；状态与轨迹分离、证据去重、上下文预算和工具配对；两个 skills 与无需 skill 分支；失败工具/重试 usage/未知用量；严格字段、覆盖与恢复；normalized EM、参考答案隔离；打包排除密钥、语料、缓存与符号链接。

HTTP provider 测试使用 `httpx.MockTransport`，只能验证协议、计数和错误分支。离线 scripted provider 和 demo 一律不具有正式提交资格，即使测试替身把名称改成 http。

## 真实检索模型和数据版本

真实执行命令：

```bash
python scripts/smoke_retrieval.py --methods sparse encoder instruction --device cpu
```

| 模型 | 不可变 revision | 编码 |
|---|---|---|
| intfloat/e5-small-v2 | ffb93f3bd4047442299a41ebb6fa998a38507c52 | 384 维，query/passage 前缀、均值池化、L2 归一化 |
| Qwen/Qwen3-Embedding-0.6B | 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 | 1024 维，Instruct/Query、末 token 池化、L2 归一化 |

两种模型的 tokenizer 与权重均固定到相同 revision。查询 `Where is Cedar University located?` 时，三种检索均将直接包含地点的合成文档 d2 排在第一；返回片段与原文 offset 一致。这是最小功能检查，不是检索效果评测。

构建记录约 49.7 秒（E5）、424.7 秒（Qwen3），**包含首次下载/加载**，不能拿来比较纯检索速度。

真实课程语料记录：`Tevatron/browsecomp-plus-corpus`，train split，revision `b27b02bc3e45511b8b82a13e6f90ce761df726f6`，实际字段 `docid/text/url`。仅导入有限样本；没有把原文或课程题目提交到 Git。

```bash
USE_TORCH=0 rag-agent prepare --config configs/corpus-smoke.yaml --hf --limit 5
rag-agent index --config configs/corpus-smoke.yaml --methods sparse
```

本机受限环境默认启用 datasets 的 PyTorch 集成时无法创建共享内存；对单独的数据导入命令设 `USE_TORCH=0` 后可读取，真实 embedding 的独立命令仍使用 PyTorch。Arrow 对 CPU 信息探测有权限提示，但读取和索引成功。

首次有限流式读取完成后出现后台预读等待；现已显式关闭底层迭代器、关闭 Parquet 预读并使用小批次缓冲。修复后使用独立 store 的 2 篇文档导入以退出码 0 正常结束；两个新增离线测试验证成功和异常路径都释放迭代器。

## 预测格式与服务核对

实际读取课程数据集 README 与官方 `examples/test_prediction.jsonl` 的结构；其字段为 `id/question/answer/trajectory/tool_calls/total_tokens`，轨迹包含 system/user/assistant/tool，assistant 带 usage，tool 带对应 ID。该示例的模拟答案和用量未用于本系统结果。课程验证数据仓库核对 revision 为 `277d3b49913c176976e8b40b7df55b00212cf158`；未运行完整验证题。

OpenRouter 目录映射已核对；指定模型配置为 `deepseek/deepseek-v4-flash-0731`。OpenRouter 分支显式关闭 thinking 并排除其返回文本，模型 backbone 保持相同；其他服务不注入这些专用字段。模型目录支持情况不等于真实 API 行为验证，来源和操作入口见 [provider.md](provider.md)。

```bash
rag-agent check-config --config configs/openrouter.yaml --live
```

本机按预期因缺失 `LLM_API_KEY` 退出 2，没有静默降级。demo 配置搭配 `--live` 同样被拒绝，不能误报为已核验真实 API。

## 未运行与实际限制

- 未完成原 V4-Flash 的真实推理、真实多轮工具调用及 live usage smoke；需要组员提供本地密钥。
- 未构建全部 100,195 文档的三种索引，未测全量磁盘、内存、查询耗时和检索表现。
- 未产生课程验证/测试 100 题 EM 或与其他组的相对排名。
- NumPy 分片查询保持内存有界，但仍精确扫描所有分片；全量延迟需要测量，可能需要后续近似向量索引优化。
- 证据校验保证来源、原文与位置，不能机械保证语义蕴含或答案正确。
- 目前提供源码草稿包；最终报告、签名、视频、正式预测不存在，正式打包会拒绝缺失材料。

本地日志、截图和模型 smoke JSON 在项目 `outputs/`，均被 Git 忽略。GitHub 提交包含代码、合成测试、配置和本文汇总，不含 benchmark 原文、模型权重、索引、密钥或私人聊天。
