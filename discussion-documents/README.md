# 项目讨论与 Astra 交接资料

2026-11-17，香港时间。Roman 接手当前主要问题的修复，Astra 移交原机的实验与运行产物，ddg 统筹，Lex 整理已有资料。

先读 [Roman 阅读指南](ROMAN-GUIDE.md)。需要转交给 Astra 的任务在 [Roman 资料移交提示词](astra-prompts/task_NLP-Agentic-RAG-for-given-documents_Roman问题复盘资料移交_prompt_1.md)。

| 目录／文件 | 用途 |
| --- | --- |
| [astra-prompts](astra-prompts/) | 本地此前交给 Astra 的任务提示词，包含历史完整骨架、两轮验收、九题复盘、自主修复、API 查找和 Qwen4B 实验。文件名里的 `prompt_1`、`prompt_2` 是同一任务的版本。 |
| [astra-records](astra-records/) | 已在仓库分支发布的回传和关键复盘的快照。各文件开头标有原提交和原始文件链接，便于对回运行的代码。 |
| [SOURCE-MANIFEST.json](SOURCE-MANIFEST.json) | 每份快照的来源、版本、SHA-256 和脱敏记录。 |
| [Roman 阅读指南](ROMAN-GUIDE.md) | 当前三类问题、模型和检索的分工，以及优先阅读的报告。 |

提示词记录当时交代的任务。完成情况以同批次的回传、实际轨迹和验收为准。已过期的分工、模型服务和执行范围应结合最新任务核对。上传副本中的真实凭据已替换为占位符。

Astra 接下来把本机尚未移交的有用记录和产物清单补到此目录。原始轨迹、数据库和索引从相应 Release 取得，对应解密文件由 ddg 私下交接。原有 `docs/` 中的报告继续可按快照链接追溯。
