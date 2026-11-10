# 四人协作建议与下一步

以下是建议边界，不是已确认的人员分工、贡献比例或签名。

| 工作方向 | 负责范围 | 与其他模块的接口 |
|---|---|---|
| 数据与检索 | data、retrieval、全量索引与检索对比 | Document、Chunk、SearchHit；SearchService.search |
| Agent 与上下文 | agent、llm、预算与错误恢复 | Question → RunResult；真实 request/response/usage |
| skills 与评测 | 原创 skills、触发策略、evaluation | SkillCatalog、Prediction、正式验收协议 |
| 网页与集成 | web_app、cli、runtime、打包与演示 | 调用相同 run_question，不复制推理代码 |

修改公共字段前一起确认 `schemas.py`；修改工具先更新注册表，并运行 `rag-agent tools` 更新工具文档。用合成 fixtures 做小范围测试，保持参考答案只在 evaluator 中加载。所有真实实验记录配置标识、数据版本、模型版本和失败情况。

结构优化已实施：资源构造集中到 runtime，数据协议集中到 schemas，模型通信集中到 llm/provider，工具 schema/分发/文档集中到同一注册表，评测与问答隔离。选择这些边界是为了让四人能分别修改、独立验证后再集成，而非追求更多目录层级。

建议依次完成：

1. 配置原 V4-Flash API，先做少量真实调用验证。
2. 评估磁盘、内存和速度，构建 100,195 文档全量索引。
3. 跑验证集，比较三类检索/融合、单步/迭代、有无 skills/上下文管理；只写实际产生的结果。
4. 确认教师发布的测试文件版本，生成并检查 100 题正式预测。
5. 使用课程 Overleaf 模板完成至少四页正文，填写真实贡献比例并各自签名；制作不超过五分钟的 MP4。
6. 在干净环境解压正式课程包，按 README 重现，再由小组成员提交 Canvas。

本轮不代填贡献比例、成员身份、实验排名或最终课程成绩。
