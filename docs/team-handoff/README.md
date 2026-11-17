# 小组项目资料与日志

查某道题时，先在逐题日志里选实验、找题号，再对照该轮报告。想追溯失败、重试或运行成本，可直接打开终端记录。需要阅读模型实际收到的消息、完整回答和原文段落时，使用对应 Release 的组内证据包。

| 想查什么 | 直接打开 |
|---|---|
| 某道题调用过哪些工具、用了多少 token、引用了哪些片段 | [逐题问答日志与运行目录](logs/README.md) |
| 哪些任务失败、重试、断点续跑，测试和上传是否成功 | [终端、测试与运行状态日志](operational/README.md) |
| 一个文件在哪个阶段产生，完整原件从哪里取 | [原件清点与补充包](artifacts.md) · [既有 5 个 Release、64 个附件与分支清单](previous-github-materials.json) |
| 本轮 2560 维为何还会漏掉第 58、788 题证据 | [九题逐题对照](../qwen4b-2560-review/comparison.md) · [两题的每步证据去向](../qwen4b-2560-review/evidence-review.md) |
| 系统如何运行，各模块由什么代码实现 | [总 README](../../README.md) · [检索设计](../RAG_设计思路.md) · [问答智能体设计](../Agent_设计思路.md) · [课程要求与实现](../requirements.md) |

日志库把同一文件的副本按内容指纹合并。逐题目录保留 483 条不同记录（473 条预测轨迹、10 次冻结请求），共 16,943 个事件；其中包含真实问答、失败尝试、合成和回放，各条记录保留其运行类型。运维目录从 1,172 个来源路径归并出 367 份文件，保留 10,948 个事件。两类目录有各自的计数单位。

**一个查阅例子**：在 [Qwen 两轮逐题目录](logs/qwen.md) 选择同一题号，再在[逐查询候选排名](logs/rankings/README.md)查看关键词初排、向量重排和实际返回。第 788 题还有[逐事件可见性核对](../qwen4b-2560-review/evidence-review.md)，可判断一段反证在何处离开了模型请求。

[下载可离线阅读与统计的公开日志 ZIP](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/download/team-project-materials-20261117/team-analysis-logs.zip)

## 实验时间线

| 阶段 | 报告、代码和完整记录 |
|---|---|
| 初版检索、Agent 1.2、重排实验 | [源码](../../src/) · [Agent 1.2](../../agent12/) · [重排实验及图表](../rerank-analysis/analysis-report.md) · [早期验证回传](../task_NLP-Agentic-RAG-for-given-documents_全项目程序验收与缺口补齐_prompt_1return.md) |
| 官方兼容 API 和全项目验收 | [模型接入记录](../deepseek_official_compat.md) · [验证 100 题、测试 100 题的结果与口径](../task_NLP-Agentic-RAG-for-given-documents_全项目程序验收与缺口补齐_prompt_2return.md) · [原始记录及数据包](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115) |
| 三类弃答的九题复盘 | [逐题复盘](../task_NLP-Agentic-RAG-for-given-documents_验证集三类弃答逐题复盘_prompt_1return.md) · [根因分析与解决方案](root-cause-analysis.md) · [原始记录](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/validation-failure-review-20261115) |
| 关键证据保留修复 | [两轮验收与失败点](../evidence-retention/acceptance-report.md) · [原始记录](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/evidence-retention-fix-20261115) |
| Qwen 256 维 int8 接入 | [检索、语义复核及开销](../task_NLP-Agentic-RAG-for-given-documents_Qwen3-Embedding-4B向量压缩与九题复测_prompt_1return.md) · [原始记录](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/qwen4b-compression-nine-20261117) |
| Qwen 2560 维 int8 接入 | [两轮九题实跑报告](../qwen4b-2560-review/task_NLP-Agentic-RAG-for-given-documents_Qwen3-Embedding-4B向量压缩与九题复测_prompt_1return.md) · [256 与 2560 两组原始记录](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/qwen4b-2560-int8-nine-20261117) |

两批 100 题使用当时的 DeepSeek 官方兼容接口。完整验证集的归一化精确匹配为 19/100，测试集缺少参考答案，故只报告输出与引文校验。更早因 HTTP 402 中断的运行单列。Qwen 的两次百炼九题实跑均命中 3/9，它们使用专门挑选的故障诊断题。

## 任务文档与配置

六份任务文档按阶段保存，基础框架文档中的个人电脑目录已替换为占位符。历次采用的模型、输入、预算和命令以对应回传报告及运行身份为准。

[基础框架](briefs/01-framework.md) · [重排实验](briefs/02-rerank.md) · [程序验收](briefs/03-program-validation.md) · [九题复盘](briefs/04-nine-diagnostics.md) · [三类根因](briefs/05-root-causes.md) · [向量压缩](briefs/06-qwen-compression.md) · [配置文件](../../configs/) · [数据与模型版本](../handoff/) · [Qwen 4B 复现](../qwen4b-review/REPRODUCE.md)

另可查看[组员文档分支](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/tree/54c8397fe59a85943bfcff0528c5ea7f507abb99)、[Agent 1.2 对接版本](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/tree/f196aed663e3b4c1d62be73210103c7c3cc04848)和[重排实验分支](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/tree/e4810d3f96509661be527932c0584c0e98f3ebe1)。历史发布清单保留了整理时可见的 11 个分支及其提交。

清点表列出 **3,071 条项目材料路径**，逐项指明已有的 Git 提交、历史 Release 或这次的补充包。补充包收纳历史发布尚未覆盖的 **608 条路径**；按内容去重后是 **579 个文件**，包含早期模型运行、终端记录、分析底稿及课程项目说明。课程数据、索引和可从固定版本取得的模型分别在历次移交中注明来源。

## 阅读完整日志

网页上的逐题记录保留题号、步骤顺序、工具动作、片段位置、状态与可用的用量统计。各家接口返回的字段随版本不同。完整问答请求、模型原话和课程原文在对应的加密附件内，以组内私下传递的解密文件打开。项目 API 凭据与归档解密文件分别管理；阅读历史记录无需购买 API 调用。

[补充原件与恢复说明](artifacts.md) · [全项目验收恢复说明](../handoff/README.md) · [证据保留轮恢复说明](../evidence-retention/HANDOFF.md) · [两轮 Qwen 复核步骤](../qwen4b-2560-review/REPRODUCE.md) · [本次资料发布与下载](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/team-project-materials-20261117)
