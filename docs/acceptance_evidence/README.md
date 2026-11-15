# 本轮公开验收统计

这些文件随源码提交，只有配置/哈希、数量、状态、耗时、usage、费率估计和逐ID指标；不包含题目、参考答案、预测答案、语料原文、原始HTTP消息或凭据。完整证据另以授权的加密资产交付。发布状态及尚未完成项见[第二轮回传](../task_NLP-Agentic-RAG-for-given-documents_全项目程序验收与缺口补齐_prompt_2return.md)。

| 公开统计 | 范围 |
|---|---|
| [需求核验](requirements-verification.json)、[输入哈希](input-hashes.json) | 六页课程指南、43项矩阵分类、100/100输入结构与固定5题重叠 |
| [候选与身份](candidate-identity.json)、[验证运行绑定](validation-binding.json) | 固定配置、运行源码、语料与技能哈希；候选选择边界 |
| [功能探针](feature-probes.json)、[上下文缺陷修复](context-delivery.json) | 8题7通过及1条独立补充通过；原始未触发案例保留；实际请求与无API回放 |
| [诊断与三消融](diagnostic-comparison.json) | 固定5题六配置；失败/协议问题不改写通过 |
| [最终CLI/网页](final-cli-web.json) | 冻结后同配置同题实测；两字符串不同但表示同一日期 |
| [验证100统计](validation100-statistics.json)、[误差阶段分析](validation-stage-analysis.md) | EM/F1、开发重叠5与其余95、耗时/usage；字面证据代理的限制 |
| [验证100终验](validation100-completion-audit.json)、[测试100终验](test100-completion-audit.json) | 六字段/ID/题目顺序、raw HTTP usage、formal/compat分层、零调用恢复与SHA不变；测试无评分 |
| [API去重总账](api-usage-ledger.json) | 242条记录、1065HTTP、全任务费用范围与估算/余额区别 |
| [索引状态](index-status.json)、[短批/检索测量](index-benchmarks.json) | 全量BM25、E5固定部分快照、Qwen用户暂缓、SQLite quick_check与性能结论边界 |
| [较早独立安装](earlier-clean-install.json)、[冻结回归](frozen-regression.json) | 不同检查点分列；最终归档复现待发布验收补充 |

原始证据解包后的仓库相对位置如下。这些是归档内定位说明，不是声称已公开托管的网页链接：

- `outputs/acceptance-validation100-v1/`：验证聚合100条、四分片、元数据、审计、评分、恢复；`independent-analysis.json`含更完整逐题诊断计数。
- `outputs/acceptance-test100-v1/`：测试聚合100条、四分片、元数据与无标签审计/恢复。
- `outputs/acceptance-diagnostics/`：固定5题各候选/消融的原始真实轨迹和失败记录。
- `outputs/acceptance-features-v1/`、`outputs/acceptance-recovery-probe-v1/`：真实功能诊断输入和HTTP轨迹。
- `work/acceptance/web/`：实际网页观察、下载和最终CLI/网页记录。
- `work/acceptance/diagnostics/`：源缺陷复现、实际请求/观察分析与无API回放证据。
- `work/acceptance/indexes/snapshots/20261115T064803Z/`：冻结数据/索引快照清单；大文件在移交包中按清单恢复。

公开统计由`scripts/prepare_public_acceptance_evidence.py`按字段白名单整理，拒绝原始内容字段、常见密钥格式和本机绝对路径。验证评价脚本只读标签和已完成预测，不调用模型或检索器；最终无标签审计使用`scripts/acceptance_completion_audit.py`。这些文件是已完成运行的快照，后续持续E5构建不会自动改变它们。
