# 全项目程序验收执行计划

起点：origin/main 1162703；执行分支 codex/course-program-validation。以本机 2026-11-13 开始执行，日期跨日按 Asia/Hong_Kong 记录。

1. 已完成：保留原检出，创建独立干净副本；fetch 最新 main；完整阅读 August 2026 v1.0 指南六页。
2. 安装隔离环境并记录两套原始测试；核查本机历史语料、模型与 API 额度、身份。
3. 先修正式链路：证据 ID 映射与可见范围；Agent 1.2 原始事件和 HTTP 请求/响应配对；课程有效性、证据质量、答案正确性分层；恢复身份与用量统计。
4. 在固定 revision 上尽早启动语料导入、三路索引；测吞吐和剩余时间，失败时修复或记录具体阻碍。
5. 离线回归、真实小样本基线/1.2 同题对照；API/数据可用时继续官方 100 题验证和关键机制对照。
6. CLI/网页/无标签批处理及中断恢复验收，干净安装和两套完整测试，脱敏自审，中文回传文档，提交推送并核对远端 SHA。

## 首轮缺口矩阵（持续更新，最终完整矩阵见回传文档）

| 要求/页码 | 代码入口 | 已有证据 | 本轮缺口与实施 | 验收 | 状态 |
|---|---|---|---|---|---|
| 固定语料与三类检索 p1-2 | data/prepare.py、retrieval/ | 历史 97 篇 | 核查缓存，固定版本，全量导入索引/吞吐与恢复 | 数量、指纹、坐标、标准 search | 执行中 |
| 工具与 Agent p2 | tools/registry.py、agent/ | 两套代码 | 真实模型、支持工具、多跳与错误路径 | 原始请求响应工具配对 | 待测 |
| 状态与上下文 p3 | agent/context.py、agent12/search_agent/agent.py | 离线测试 | ID 引用必须来自实际展示的原文范围 | 长证据/截断/坏 ID 回归 | 待修 |
| skills p3 | skills/、skills/runtime.py | 两个原创技能 | 核对候选自动选择及正文影响 | 不同题/停滞状态 | 待测 |
| UI p3 | web_app.py | 历史 demo | 两种 Agent 正常与失败入口实测 | AppTest 与浏览器 | 待测 |
| 六字段/真实轨迹 p4 | agent/agent12.py、evaluation/validate.py | 基线 validator | Agent12 eligible 固定 false、HTTP 包装事件、课程有效性与证据质量混用 | 正反向协议/证据/usage 测试 | 优先修复 |
| 批处理/恢复/EM p4-5 | evaluation/batch.py、metrics.py | 原有恢复实现 | 索引/代码身份绑定、用量账本与中断验证 | 输入投影、断点、重试保留成本 | 待核查 |
| 干净复现 p5 | pyproject.toml、README.md | 已有说明 | 本机干净安装及标准命令 | 两套测试+安装烟测 | 执行中 |
| 真实验证 100 题 p1/4 | scripts/fetch_validation.py | 尚无本轮结果 | 先确认模型可用额度与全量索引 | 覆盖、EM、工具、tokens | 待资源核查 |
| 报告/视频/测试集/最终课程包 p3-5 | 后续阶段 | 无 | 本轮明确排除 | 留待组员最终课程交付 | 本轮排除 |
