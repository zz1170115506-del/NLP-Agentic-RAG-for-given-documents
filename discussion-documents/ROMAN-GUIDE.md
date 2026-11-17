# 给 Roman 的阅读指南

Roman，你负责接下来主要问题的修复。这个项目用 DeepSeek 问答模型调用工具，从固定的 **100,195 篇文档**里搜索证据，再回答多线索问题。百炼北京的 `deepseek-v4-flash-0731` 是目前已联调的问答 API。BM25 按词检索，E5 和 Qwen Embedding 负责把查询与文本编码成向量，Agent 通过一个 `search` 入口使用这些检索能力。API Key 由 ddg 私下提供。

当前集中处理三类问题。**检索阶段**会漏掉关键片段、反复搜相同查询或未继续核查候选；**上下文阶段**会把工具已经返回的关键证据排除在模型请求外；**作答阶段**会遗漏题目条件、错误处理年代或关系，甚至忽略反证。九道开发用验证题是 960、1035、64、231、390、58、1155、1066、788。19% 是早一轮完整验证集的成绩，后面的 3/9 是这组已经用于调试的失败题的成绩。

| 先看哪份资料 | 能了解什么 |
| --- | --- |
| [九题逐题复盘](astra-records/task_NLP-Agentic-RAG-for-given-documents_验证集三类弃答逐题复盘_prompt_1return.md) | 每题查询、证据、实际模型请求和停止原因。 |
| [证据保留修复](astra-records/evidence-retention/acceptance-report.md) | 上下文修复后的完整重跑，由百炼基线 0/9 到 3/9，仍有六题弃答。 |
| [条件与反证审查](astra-records/evidence-retention/v2-semantic-review-public.md) | 为什么匹配标准答案之后仍要核查原文是否支持全部条件，特别是 788 题。 |
| [Qwen4B 压缩复测](astra-records/task_NLP-Agentic-RAG-for-given-documents_Qwen3-Embedding-4B向量压缩与九题复测_prompt_1return.md) | 全库 BM25 先取 32 个候选，Qwen4B 对候选排序后返回 5 个，256 维 int8 九题结果为 3/9。58 题的资助段被排序降到返回范围之外。 |
| [Qwen4B 全维对照](astra-records/qwen4b-2560-review/task_NLP-Agentic-RAG-for-given-documents_Qwen3-Embedding-4B向量压缩与九题复测_prompt_1return.md) | 2560 维 int8 仍为 3/9，788 的医院反证进入工具返回后又在模型上下文中消失。 |
| [全量语料和索引移交](astra-records/handoff/README.md) | 数据库、完整 BM25、向量检查点、模型版本及恢复方法。目录里的进度是历史快照，Astra 会补最新状态。 |

`astra-prompts/` 保存我们交代过的任务；文件名带 `return` 的通常是 Astra 的执行回传。JSON 汇总便于核对计数和运行身份，`HANDOFF.md` 与 `REPRODUCE.md` 指向完整轨迹、下载与复现方法。快照中的链接绑定原提交，适合对照当时实现。

截至 2026-11-17，本次资料提交基于远端 `main` 的 `316c64a`。后续功能及实验分布在 `codex/evidence-retention-fix`（`b37c8fc`）、`codex/qwen4b-compression-nine`（`d2ad111`）和 `codex/qwen4b-2560-nine`（`0eee841`）。接手代码时请核对所选分支，实验结果要和对应版本一起看。Astra 的补充回传会说明原机最新状态。

你可以自行选择修复方案。用真实逐题轨迹确认问题发生在哪个环节，记录改动后的效果和开销，再用其他验证题检查能否推广。Roman 与 Astra 的并行工作请各自登记分支与配置，方便 ddg 最后整合。
