# 预测文件核对记录（Group 18）

日期：2026-11-20（首版核对 2026-11-18；2026-11-19 重跑 v2；2026-11-20 合并 context64 + context96）

## 当前提交版本

- `submission/Group-18/test_prediction.jsonl`：**2026-11-20 合并版**，官方 `api.deepseek.com` + `deepseek-v4-flash`（实际 V4.1-Flash-1017）。
- 大小：113,182,809 B；SHA-256：`229bad39d7cd474f9b2cb9d9da1bea45775d349535ce3787e95c05c8f3650c08`。
- 生产方法：先用 `configs/context64.yaml`（`context_chars=64000`）跑 100 题；其中 40 题空答，再用 `configs/context96.yaml`（`context_chars=96000`）补跑这 40 题；按 `data/test.jsonl` 顺序合并。
- 记录中的 config id：`af985bb241f6ca07`（context64）、`d0fbc7a5a8337f78`（context96）。
- 模型身份：`model_policy=official_compat`、`model_verified=false`；老师 2026-11-18 已确认官方 V4 端点（实际 V4.1）可接受。
- 历史版本保留：`submission/evidence/test_prediction-v2-20261119.jsonl`（43,466,064 B，SHA `da9f07eb…`）与 `test_prediction-frozen-20261115.jsonl`（41,377,334 B，SHA `5f8d1108…`），可回滚。

## 独立复核（2026-11-20 合并版）

- 100 行；六字段齐全（id/question/answer/trajectory/tool_calls/total_tokens）；id 顺序与 `data/test.jsonl` 一致。
- test：**88 题作答 / 12 题弃答**；工具 **1,004** 次；**7,612,685 tokens**；citation **92/100**；`ordinary_valid=true`、`formal=false`。
- `formal_batch_valid=false`：`validate --official-compat` 只报 “formal batch must use one consistent recorded config_id”（合并版用了两个实验配置）；模型身份仍按 `official_compat` 记录，未声称 2026-04 原版权重。
- validation 参考（同 commit prompt、官方端点）：
  - `context64` 全量 100 题：**40 对、EM 40%**、58 答、已答精度 69%。
  - 开启 thinking 后 64k 全量：**78 答、54 对、EM 54%、精度 69.2%**；对空答再用 96k 补跑，加上扩展答案规范化（修复 52、276）后，合并 **84 答、66 对、EM 66%、精度 78.6%**。
  - 旧 commit 全量：26 对、EM 26%、46 答；旧冻结版：19 对、EM 19%、20 答。
- trajectory 为完整事件列表（run_start / request / api_attempt / assistant / tool / context / finalization / answer / run_end），可读。
- 未发现真实密钥或用户绝对路径（`sk-` 命中均为语料正文中的 `task-force`；`Authorization` 为文档正文）。

## 本机/服务器复跑校验

```bash
rag-agent validate --config configs/context64.yaml \
  --input data/test.jsonl \
  --predictions ../test_prediction.jsonl \
  --official-compat
```

结果：`ordinary_valid=true`、records 100、completed 88、failed 12、citation 92/100、tool_calls 1,004、total_tokens 7,612,685、`config_ids=["af985bb241f6ca07","d0fbc7a5a8337f78"]`；`formal=false` 因合并版使用两个配置 id，且模型身份仍按 official_compat 记录。

## 代码快照

- 由 `git archive dab7646` 导出到 `Group-18/code/`（196 文件），并叠加 2026-11-19/20 使用的 `src/rag_agent/agent/context.py`、`loop.py`、`src/rag_agent/llm/provider.py`（thinking 开启）、`configs/official-final.yaml`、`configs/context64.yaml`、`configs/context96.yaml`；README 已更新为当前预测的 SHA/统计。
- `data/test.jsonl` 100 题，SHA `2e9e3689de5901e0151995db91d0fa6525b2062cc116ddab88f59b9ccccd5d0b`。
- 已用 `scripts/audit_predictions.py` 在服务器复核，结果见 `evidence/audit-test100.json`。

## 结论

预测文件格式、顺序、覆盖通过，88 题作答；相对首版，回答率从 20% 提升到 88%，验证集 EM 从 19% 提升到 64%。模型身份是官方 V4.1 兼容端点（非 2026-04 原版权重），已如实披露。

## 提交清单（待补齐）

- [x] `test_prediction.jsonl`（100 条、六字段、SHA 已核）
- [x] `code/`（冻结提交 + 重跑 prompt/config、README）
- [x] 验证集预测与审计报告
- [ ] `Group-18-Report.pdf`（已有 `Report-draft.md` + 图，待 Overleaf 排版/PDF）
- [ ] `Group-18-Video.mp4`（已有 `Video-script.md`，待录制 ≤5 分钟）
- [ ] 贡献表 100% 与四人签名
- [ ] 最终 `Group-18.zip` 组包与 Canvas 提交
