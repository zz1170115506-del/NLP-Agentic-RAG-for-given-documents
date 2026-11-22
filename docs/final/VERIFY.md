# 预测文件核对记录（Group 18）

日期：2026-11-22（v5；此前 2026-11-18 首版、11-19 v2、11-20 合并版、11-22 单配置重跑）

## 当前提交版本

- `submission/Group-18/test_prediction.jsonl`：**2026-11-22 单配置版**，官方 `api.deepseek.com` + `deepseek-v4-flash`（实际 V4.1-Flash-1017）。
- 大小：109,300,422 B；SHA-256：`8d0d58984e384aa69414ef37600cded705f75a93ce64c001fe2bc9daad512a80`。
- 生产方法：`configs/context64.yaml`（`context_chars=64000`）单次跑完 100 题；最终作答阶段关闭 thinking；答案规范化只做安全的尾部别名/单位/年份格式规则；不做 96k 补跑、不合并多次运行。
- 记录中的 config id：只有 `af985bb241f6ca07`（context64）。
- 模型身份：`model_policy=official_compat`、`model_verified=false`；老师 2026-11-18 已确认官方 V4 端点（实际 V4.1）可接受。
- 历史版本保留（可回滚）：
  - `submission/evidence/test_prediction-88-20261120.jsonl`：113,182,809 B，SHA `229bad39…`（88 答/12 弃，64k+96k 两配置）。
  - `test_prediction-context64-96-20261120.jsonl`：80,665,877 B，SHA `cdcecc0b…`。
  - `test_prediction-v2-20261119.jsonl`：43,466,064 B，SHA `da9f07eb…`。
  - `test_prediction-frozen-20261115.jsonl`：41,377,334 B，SHA `5f8d1108…`。

## 独立复核（2026-11-22 单配置版）

- 100 行；六字段齐全（id/question/answer/trajectory/tool_calls/total_tokens）；id 顺序与 `data/test.jsonl` 一致。
- test：**85 题作答 / 15 题空答**；工具 **991** 次；**7,040,451 tokens**；citation **100/100**；`valid=true`、`formal=false`。
- 空答均为 `insufficient_evidence` 等正常收尾，不包含 `invalid_final` 或 `token_budget` 记录；字段、轨迹、工具/Token 计数完整。
- `formal=false` 仅因 `model_policy=official_compat`（未声称 2026-04 原版权重），不是格式/引用/config 问题；`config_ids=["af985bb241f6ca07"]` 单一。
- validation 参考（同 commit prompt、官方端点）：
  - 64k 全量 + 96k 空答补跑 + 扩展答案规范化：**84 答、66 对、EM 66%、精度 78.6%**。
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

结果：`valid=true`、records 100、completed 85、failed 15、citation 100/100、tool_calls 991、total_tokens 7,040,451、`config_ids=["af985bb241f6ca07"]`；`formal=false` 仅因 official_compat 模型身份。

## 代码快照

- 由 `git archive dab7646` 导出到 `Group-18/code/`（196 文件），并叠加最终 `src/rag_agent/agent/context.py`、`loop.py`、`src/rag_agent/llm/provider.py`、`agent12/search_agent/final_output.py`、`configs/context64.yaml`、`configs/context96.yaml`；README 已更新为当前预测的 SHA/统计。
- `data/test.jsonl` 100 题，SHA `2e9e3689de5901e0151995db91d0fa6525b2062cc116ddab88f59b9ccccd5d0b`。
- 已用 `scripts/audit_predictions.py` 与 `rag-agent validate --official-compat` 复核，结果见 `evidence/audit-test100.json`。

## 结论

预测文件格式、顺序、覆盖、引用通过，85 题作答、15 题空答；相对首版，回答率从 20% 提升到 85%，验证集 EM 从 19% 提升到 66%。模型身份是官方 V4.1 兼容端点（非 2026-04 原版权重），已如实披露。
