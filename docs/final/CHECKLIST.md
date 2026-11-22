# Group 18 提交清单与评分对照

更新：2026-11-22　截止：**2026-11-26 23:59（香港时间）**，还剩约 4 天。

## 1. 现在做到哪一步

| 交付物 | 状态 | 位置 / 说明 |
|---|---|---|
| `test_prediction.jsonl` | ✅ 已完成并独立复核 | `Group-18/test_prediction.jsonl`，100 条、六字段、85 答/15 空、991 工具、7,040,451 tokens；SHA `8d0d5898…`（单次 64k，最终作答关闭 thinking） |
| `code/` | ✅ 已完成 | `Group-18/code/`，冻结提交 `dab7646`，含 README、config、skills、tests；约 3.2 MB |
| 验证集预测与审计 | ✅ 已有 | `evidence/validation_prediction.jsonl`、`audit-test100.json`、`audit-validation100.json` |
| 报告 | 🟡 草稿完成，待排版 PDF | `Group-18/report/Report-draft.md`（英文，含 5 张图、6 张表）；需按 Overleaf 模板排版，≥4 页（不含参考文献/贡献声明）；`Report-preview.pdf` 仅供页数预览 |
| 视频 | 🟡 脚本完成，待录制 | `Group-18/Video-script.md`（4:45 分镜）；需 MP4、≤5 分钟 |
| 贡献表/签名 | ⬜ 待组员填写 | 报告末尾表格，四人各 25%，合计 100%，每人签名 |
| 最终 ZIP / Canvas | ⬜ 待组包 | `Group-18.zip` 结构见第 3 节；Canvas 提交后保留 API 配置到评分结束 |

## 2. 评分项对照（按课程 PDF）

| 评分项 | 分值 | 我们的证据 | 状态/风险 |
|---|---:|---|---|
| 1.1 检索方法（一类 4 / 两类 6 / 三类 8） | 8 | 代码实现 BM25、E5、Qwen、RRF；`configs/acceptance-final.yaml`（sparse 全量）、`configs/course-full-vectors.yaml`（dense/hybrid）、`docs/retrieval_sources.md`、小样本 Recall@5 1.00/0.95 | 🟡 提交批次只用 sparse；报告如实说明 dense 实现完整但索引未完成。若评分只看提交索引，可能只拿 4/8 |
| 1.1 统一检索工具 + 支撑工具 | 4 | `search` 唯一检索入口；`open_document`、`find_in_document`、`load_skill`；`docs/tool_schemas.json` | ✅ 4/4 |
| 1.2 基础 Agent | 4 | `src/rag_agent/agent/loop.py`，JSON 答案 + evidence ids + offset 校验；`tests/` | ✅ |
| 1.2 Feature A 迭代循环 | 5 | 12 步/24 调用；结果驱动下一轮；`trajectory` 完整 | ✅ |
| 1.2 Feature B 上下文管理 | 5 | `context_chars` 24k；证据保留、旧结果压缩；消融 1/5 有效 vs 5/5 | ✅ |
| 1.3 SKILL.md 结构 | 6 | `skills/multi-clue-decomposition/SKILL.md`、`skills/search-recovery/SKILL.md`（YAML 元数据 + 正文） | ✅ |
| 1.3 自动选择 bonus | 4 | `loop.py` 177–183 行按问题/停滞选择；两个技能均触发；报告/视频需展示不同问题 | 🟡 规则式选择（非模型自选），需在报告和视频中明确展示两个不同触发 |
| 1.4 UI | 4 | Streamlit "Evidence Desk"；`report/figures/ui-overview.png`、`ui-evidence.png` | ✅ 4/4 |
| 报告 | 20 | `Report-draft.md`；需 Overleaf 模板、≥4 页、系统设计/流程图/结果/UI 截图、贡献表签名 | 🟡 待 PDF + 签名 |
| 视频 | 20 | `Video-script.md`；需 MP4 ≤5 分钟，演示系统/功能/代码结构 | 🟡 待录制 |
| 性能：有效提交 | 10 | 100 条六字段、真实轨迹、citation 100/100、`ordinary_valid=true` | ✅ 模型身份为官方 V4.1 端点，老师已确认可接受 |
| 性能：EM 百分位 | 6 | 验证合并口径 EM 66/100（84 答中 66 对，64k+96k + 扩展规范化） | 🟡 覆盖率升到 84%，精度 78.6%，百分位中等偏上 |
| 性能：工具/Token 百分位 | 4 | 991 调用 / 7.04M tokens | 🟡 token 仍偏高（thinking + 64k 上下文），百分位不利 |

**粗略估分**：系统实现 32–36/40；报告 0→预计 16–19；视频 0→预计 16–19；性能 10–14/20（取决于模型身份是否被接受、百分位）。补齐后约 **74–88/100**；若模型身份被判无效，约 **64–78**。

## 3. 最终 ZIP 结构

```
Group-18.zip
└── Group-18/
    ├── test_prediction.jsonl      109,300,422 B（不要改字节）
    ├── code/                      冻结提交 + README
    ├── Group-18-Report.pdf        Overleaf 导出，≥4 页
    └── Group-18-Video.mp4         ≤5:00，H.264
```

不要放：`.env`、密钥、模型权重、完整 8–15 GB 索引。大索引可放公开只读链接，在 README/报告里说明。

## 4. 组包前检查（逐条打勾）

- [ ] `test_prediction.jsonl` 的 SHA-256 仍为 `8d0d58984e384aa69414ef37600cded705f75a93ce64c001fe2bc9daad512a80`（`Get-FileHash`）。
- [ ] 100 行；每行恰好六字段；id 顺序与 `code/data/test.jsonl` 完全一致。
- [ ] 抽查 85 条非空答案、15 条空答案；每条 `trajectory` 可读、含 `run_start`/`answer`/`run_end`。
- [ ] `citation` 100/100；`valid=true`。
- [ ] `code/` 里没有 `.env`、`sk-`、`/Users/`、`E:\` 等敏感或本机路径；README 中的命令可照抄执行。
- [ ] 报告 PDF：≥4 页（不含参考文献与贡献声明）；贡献表 4 人 × 25% = 100%；每人签名；含架构图、流程图、结果表、UI 截图。
- [ ] 视频：≤5:00；能听到讲解；画面不出现密钥、余额、私人聊天/文件路径。
- [ ] ZIP 解压后目录名是 `Group-18/`，四件套齐全；ZIP 总大小合理（预测 + 代码 + 报告 + 视频）。
- [ ] Canvas 提交成功；保留 API 配置到评分结束。

## 5. 最后 8 天的建议顺序

1. **今天**：把 `Report-draft.md` 粘进 Overleaf 模板，补 5 张图；先出一版 PDF，检查页数。
2. **第 1–2 天**：录视频（按 `Video-script.md`）；用 demo 配置录 UI，避免 API 依赖。
3. **第 3 天**：组员填贡献表、签名；确认组号 18、姓名、学号。
4. **第 4 天**：组 ZIP，跑第 4 节全部检查；换一台干净机器解压验证。
5. **第 5 天**：Canvas 提交；提交后不要再改预测文件。
6. **余下时间**：若还有余力，补 E5 全量索引并重跑验证集对比（不改已提交预测），把对比写进报告“未来工作”；不要为了提分临时改答案或手工编辑预测。

## 6. 需要组员确认的三件事

1. **模型身份**：提交的是官方 `deepseek-v4-flash` 别名（实际 V4.1-Flash-1017）；老师 2026-11-18 已确认该端点可接受，报告如实写明；`formal=false` 只是我们自己的严格审计，不再重跑原版。
2. **报告模板**：Overleaf 只读链接 `https://www.overleaf.com/read/wdbsnbtqwcrv`，需复制到自己的项目再编辑。
3. **贡献比例**：文档只给建议分工，不代填百分比；四人确认后各自签名。
