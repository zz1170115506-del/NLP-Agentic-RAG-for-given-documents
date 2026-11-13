# 课程要求与实现位置

2026-11-14 的正式链路、真实实测与全量状态以[程序验收回传文档](task_NLP-Agentic-RAG-for-given-documents_全项目程序验收与缺口补齐_prompt_1return.md)为准。`--formal` 检查课程记录有效性，`--strict-grounding` 独立检查引用质量，Normalized EM 独立检查答案正确性；真实诚实弃答可通过单条有效性校验。完整语料及BM25已完成，完整两路神经索引未完成；官方验证86条单条合格、4条服务失败、10条缺失，未通过100题门槛。

依据用户提供的 `COMP5423_26Fall_Project.pdf`（August 2026 v1.0，共 6 页）及本轮明确选择的完整功能范围。课程最低要求与本项目目标分开列出；实现对应关系不是教师评分承诺。实际执行命令及验证结果统一见 [`validation.md`](validation.md)。

## 范围与后续交付

课程项目为 Skill-Augmented Search Agent，截止时间为 **2026-11-26 23:59，香港时间**。系统实现、书面报告、演示视频、系统表现的权重依次为 40%、20%、20%、20%。本轮建立系统及实验入口，不代替最终报告、视频和真实 100 题提交。

PDF 第 2 页允许至少一类检索；实现一、二、三类对应不同分档。本轮用户选择三类完整基线。PDF 第 3 页的基本 skill 要求至少一个；本轮实现两个功能不同的原创 skills，并实现自动选择和按需加载。

## 系统与证据映射

| 要求与来源 | 当前实现位置 | 验证入口与边界 |
|---|---|---|
| 固定 100,195 文档，字段 ID/text/URL；PDF 第 1 页 | `data/prepare.py`、`data/store.py`；限制为指定 Hugging Face corpus，记录不可变版本和实际数量 | `test_mapping_offsets_resume_and_mutation_guard`；100,195篇、4,345,592片段及全量BM25实测完成，完整神经索引仍待完成 |
| 三类检索；PDF 第 2 页加本轮用户范围 | `retrieval/sparse.py` 的 FTS5 BM25；`retrieval/embedding.py` 的 E5 与 Qwen3；`retrieval/dense.py` 的持久化向量分片 | `tests/test_retrieval.py`；真实神经检索以 `scripts/smoke_retrieval.py` 和验证记录为准 |
| 长文档完整覆盖与原文溯源；本轮用户范围 | `chunk_document`、`TransformerEmbedder.segments`；字符 offset，模型 token 长度检查 | `test_token_budget_segments_preserve_all_characters`，索引结果片段与原文一致性检查 |
| 索引持久化、兼容检查和恢复；本轮用户范围 | SQLite 完成标记；`dense.py` 的 manifest、SHA256、分片复用和内存映射 | `test_dense_shards_resume_compatibility_and_corruption`、`test_dense_merges_passages_across_shards_and_resumes` |
| 恰好一个检索工具；PDF 第 2 页 | `tools/registry.py` 仅暴露 `search`；method 在同一个工具中选择 | `test_registry_exactly_one_search_and_support_tools`、`test_configured_retrieval_method_and_defaults_are_enforced` |
| 至少一个支持工具；PDF 第 2 页 | `open_document`、`find_in_document`，另有 `load_skill`；默认共四种工具 | 同一注册表生成 API schema、输入/输出校验和工具协议文档；上述工具测试 |
| 指定 DeepSeek-V4-Flash API；PDF 第 1、2 页 | `llm/provider.py`、`config.py`；`configs/openrouter.yaml` 提供核对过的具体模型配置 | 服务商目录核对与真实 API 调用分开；密钥缺失时不会降级成 demo，真实调用状态见验证记录 |
| 基本工具调用及结果驱动迭代；PDF 第 2 页 | `agent/loop.py` 的 `run_question`，每轮模型读取实际结果后提出行动 | `test_result_dependent_demo_two_hop_and_state` 为确定性离线两跳流程，不能冒充真实 LLM 行为 |
| 独立状态与上下文控制；PDF 第 3 页 | `schemas.py` 的 `AgentState`；`agent/context.py` 的证据选择与完整工具组裁剪 | `test_context_pruning_keeps_pairs_and_audit_history`；完整轨迹与模型当轮上下文分别保存 |
| 证据真实性及终止预算；本轮用户范围 | `agent/loop.py` 检查引用为已查看原文子串；步数、调用数、token、时间与重复行动限制 | `test_unseen_or_fabricated_citations_rejected`、`test_budget_completes_all_tool_pairs_without_extra_execution`、`test_token_budget_stops_after_actual_usage_and_counts_it` |
| 两个原创 skills、运行时正文加载；PDF 第 3 页及本轮用户范围 | `skills/multi-clue-decomposition/SKILL.md`、`skills/search-recovery/SKILL.md`；`src/rag_agent/skills/runtime.py` | `test_metadata_only_discovery_dynamic_body_and_no_skill`、`test_error_recovery_skill_invalid_tool_counts_and_api_usage` |
| 自动选择、切换或无需 skill；PDF 第 3 页 | 当前是基于问题和停滞状态的确定性选择规则；模型也可主动调用 `load_skill` | 已选正文进入下一轮上下文；自动内部选择不计工具调用，模型主动调用计数；`test_no_skill_ablation_and_explicit_load_count` |
| 简单网页显示答案、证据、skills 与过程；PDF 第 3 页 | `web_app.py`；与 `cli.py` 共用 `runtime.py`、`run_question` | Streamlit 启动与主要交互检查见验证记录；demo 标签明确，不代表模型能力 |
| 每题一条记录，六个指定字段；PDF 第 4 页 | `schemas.py` 的 `Prediction`；`evaluation/batch.py` 逐题持久化 | `tests/test_evaluation.py` 覆盖格式、唯一 ID、覆盖率、失败与恢复 |
| 真实时间序列和调用统计；PDF 第 4 页 | `agent/loop.py` 记录实际请求/响应/工具结果；失败调用保留；内部融合只算一次工具 | `test_error_recovery_skill_invalid_tool_counts_and_api_usage`、`test_received_usage_on_retry_error_is_counted_without_fabricated_assistant` |
| 所有 API 调用的 `usage.total_tokens` 求和；PDF 第 4 页 | provider 和 loop 记录成功响应及有 usage 的重试；不使用本地字符估算作为正式 token | `test_missing_usage_rejected_and_tool_not_executed`、`test_http_retry_records_attempts_and_never_logs_credentials` |
| 验证集答案仅用于评测；PDF 第 5 页及本轮用户范围 | `evaluation/io.py` 将问题投影为 `Question(id, question)`；`metrics.py` 单独读取参考答案 | `test_labels_removed_and_id_preserved`、`test_reference_answer_rejected_at_question_boundary` |
| Normalized EM；PDF 第 4 页 | `evaluation/metrics.py`：小写、去标点、去英文冠词、空白归一后精确匹配 | `test_normalized_em_and_failures`；不虚构相对排名，排名需要其他组数据 |
| 正式 100 题全覆盖且来自真实指定模型；PDF 第 4 页 | `evaluation/validate.py` 的 formal 模式检查真实身份、模式、配对、usage、答案来源和覆盖；严格引用质量由`--strict-grounding`独立检查 | `test_pairing_usage_and_formal_gate`、`test_coverage_types_and_usage_missing`；离线demo、小样本不能通过正式批量门槛；错误答案和真实诚实弃答可单条合格，基础设施失败逐条报告 |
| 断点续跑、失败重跑不丢记录；本轮用户范围 | `evaluation/batch.py` 的输入/配置绑定、互斥锁、逐题落盘与失败历史存档 | `test_resume_and_failed_retry_are_durable_and_label_free`、`test_uncaught_failure_is_recorded_and_never_formal` |
| 可复现实验开关；PDF 报告要求加本轮用户范围 | `configs/ablation-*.yaml` 及共用 Settings，控制单步、context、skills、三方法 | 开关与边界有离线测试；尚未产生全量对比实验数据 |
| 安装、预测、校验、打包入口；PDF 第 5 页 | `pyproject.toml`、`requirements.txt`、`cli.py`、`scripts/package_course.py` | `test_package_rejects_incomplete_and_ignores_secrets`；正式包缺少预测/报告/视频时拒绝生成，draft 明确标注源码开发包 |

## 仍须完成的正式课程材料

1. 在明确预算下完成固定语料完整索引、验证集运行和参数对比，保存真实运行配置、调用统计和 EM。
2. 测试集发布并获得文件后，用相同批量入口生成 `test_prediction.jsonl`，通过 100 题正式校验。不能把合成题或验证样例改名充当测试集。
3. 按 PDF 第 3 页给出的[官方 Overleaf 模板](https://www.overleaf.com/read/wdbsnbtqwcrv#5382c5)完成报告，正文至少四页；参考文献和 Contribution and Declaration 不计入四页。实际贡献比例合计 100%，每位成员签名。
4. 录制不超过五分钟的 MP4，展示真实系统行为、所声称功能和代码结构。
5. 在干净环境复现源码包，再按 PDF 第 5 页要求形成包含正式预测、代码、报告、视频的完整压缩包并由小组提交 Canvas。

设计文档和建议模块边界不等于最终贡献声明；本仓库不虚构姓名、贡献比例、签名或实验成绩。
