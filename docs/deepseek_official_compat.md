# DeepSeek 官方接口兼容运行

使用 `model_policy: official_compat`，可以继续通过官方接口请求 `deepseek-v4-flash`，运行检索、工具调用和多轮问答。服务返回的模型名与请求名不同，不再成为开发测试的停止条件；请求名和实际响应名分别保留在轨迹中。

## 配置选择

| 配置 | 用途 |
| --- | --- |
| `configs/deepseek-official-smoke.yaml` | baseline 的官方接口短测试 |
| `configs/deepseek-official-agent12-smoke.yaml` | Agent 1.2 的同题短测试 |

两份配置共用三篇合成文档及 BM25 词语检索索引，关闭技能自动选择，每题最多 8 轮、8 次工具调用，token 预算为 12,000。它们采用同一请求模型与服务地址，仅 Agent 实现不同。

`official_compat` 的规则是：

- 地址只能是 `https://api.deepseek.com` 或其 `/v1` 入口；请求名固定为 `deepseek-v4-flash`。
- 接受官方服务返回的任意非空模型名，并原样记录；例如返回 `deepseek-flash` 时继续执行工具和后续请求。
- `model_verified` 必须为 `false`，并提供模型映射说明。这表示未核验原版课程模型身份，不表示接口不能用于开发。
- provider 显式发送 `thinking: {type: disabled}`，两种 Agent 使用相同的非思考模式工具协议。

未指定 `model_policy` 的配置仍默认使用 `course_pinned`，保留原有的课程模型严格检查。切换到官方兼容模式后使用新的预测输出目录，避免与旧运行身份混合。

## 本地凭据

在项目根目录的 `.env` 中填写以下内容，密钥仅保存在本机：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=填写本地密钥
LLM_MODEL_VERIFIED=false
LLM_MODEL_VERIFICATION_NOTE="Official legacy alias; record the actual response model separately."
```

项目的 `.gitignore` 已忽略 `.env`。在 macOS 或 Linux 下限制文件权限并检查忽略规则：

```bash
chmod 600 .env
git check-ignore .env
```

从项目根目录运行。项目自动读取 `.env`，但终端中已存在的同名环境变量优先；若此前使用另一服务，先清除旧值，再运行下面的命令：

```bash
unset LLM_BASE_URL LLM_MODEL LLM_API_KEY LLM_MODEL_VERIFIED LLM_MODEL_VERIFICATION_NOTE
```

不在 YAML、日志或提交文件中填写真实密钥。`model_policy` 在 YAML 中设置，不是环境变量。

## 准备合成语料并运行真实工具测试

先激活已安装项目依赖的 Python 环境。若复用其他 checkout 的环境，以下 `PYTHONPATH` 可确保导入当前源码，而非旧安装目录：

```bash
export PYTHONPATH=src:agent12

python -m rag_agent.cli check-config \
  --config configs/deepseek-official-smoke.yaml --live

python -m rag_agent.cli prepare \
  --config configs/deepseek-official-smoke.yaml \
  --source tests/fixtures/corpus.jsonl

python -m rag_agent.cli index \
  --config configs/deepseek-official-smoke.yaml --methods sparse
```

这三条命令不调用 LLM API。`check-config --live` 只检查本地配置与密钥是否存在，不验证密钥有效性。语料为项目自写的三篇虚构文档，不是官方验证集或测试集。

创建一题输入，明确要求搜索后打开原文：

```bash
cat > data/deepseek-official-smoke-questions.jsonl <<'JSONL'
{"id":"official-smoke-copper","question":"When did the Copper Museum open? Verify by calling search and then open_document before answering."}
JSONL
```

以下两条命令会真实调用官方 API，并分别保存两种 Agent 的回答、完整轨迹和用量：

```bash
python -m rag_agent.cli predict \
  --config configs/deepseek-official-smoke.yaml \
  --input data/deepseek-official-smoke-questions.jsonl \
  --output outputs/deepseek-official-smoke/baseline.jsonl

python -m rag_agent.cli predict \
  --config configs/deepseek-official-agent12-smoke.yaml \
  --input data/deepseek-official-smoke-questions.jsonl \
  --output outputs/deepseek-official-smoke/agent12.jsonl
```

预期答案为 `1984`，来源是文档 `d3`。实际验收还需查看模型确实发出了 `search`、`open_document`，工具结果的 `tool_call_id` 与调用相匹配，且后续模型请求包含这些工具结果。仅出现正确答案不能代替工具协议检查。

请求中的 `model`、响应中的 `model` 以及各响应的 `usage` 均应原样保留。累计 token 以实际响应的 `usage.total_tokens` 为准，同一个响应不能因同时出现在原始 HTTP 记录和 assistant 事件中而重复计数。缺失用量应标为未知。

## 三种校验分别回答什么问题

| 校验 | 检查范围 | 能否证明课程正式合格 |
| --- | --- | --- |
| 普通 `validate` | 六字段格式、题号与题目对应、工具配对、已记录用量与汇总一致 | 不能 |
| 加 `--strict-grounding` | 额外检查引用能否对应已展示的原文证据 | 不能；证据正确也不等于答案正确 |
| 加 `--formal` | 课程模型身份、真实 HTTP 记录、完整用量等正式要求；批次还要求恰好 100 题 | 官方兼容模式不能据此声明原版模型合格 |

例如检查 baseline 的开发记录与引用：

```bash
python -m rag_agent.cli validate \
  --config configs/deepseek-official-smoke.yaml \
  --input data/deepseek-official-smoke-questions.jsonl \
  --predictions outputs/deepseek-official-smoke/baseline.jsonl

python -m rag_agent.cli validate \
  --config configs/deepseek-official-smoke.yaml \
  --input data/deepseek-official-smoke-questions.jsonl \
  --predictions outputs/deepseek-official-smoke/baseline.jsonl \
  --strict-grounding
```

检查 Agent 1.2 时，替换为对应配置和 `agent12.jsonl`。若对上述一题记录加 `--formal`，会因官方兼容模型身份及不足 100 题而不通过；应保留该结果，同时继续正常的开发、工具与接口测试。

## 2026 年 11 月 15 日真实测试结果

使用用户提供的官方 API 密钥，两种 Agent 已分别完成上述一题测试。运行代码提交为 `0503ca571b3df3db9f963b865107d40473ac30c8`。

| 引擎 | HTTP 请求 | 实际工具 | 答案 | 总 tokens |
| --- | --- | --- | --- | --- |
| baseline | 3 次，均为 200 | search → open_document | 1984 | 4,444 |
| Agent 1.2 | 3 次，均为 200 | search → open_document | 1984 | 4,318 |

全部请求名为 `deepseek-v4-flash`，实际响应名均为 `deepseek-flash`。每个工具结果均在后续请求中回传；六字段记录、原文引用、原始 HTTP 与轨迹一致性以及 token 加总检查均通过。累计 6 次请求、8,762 tokens，未包含此前单独的 10-token 接口探测。

离线检查通过：主项目 124 项测试、Agent 1.2 独立套件 70 项测试及 4 项子测试，整个仓库 Ruff 检查通过。完整统计见 [实测摘要](official_api_smoke_result.json)。这些结果验证合成小样本上的接口和工具流程，不代表全量检索或课程 100 题评测完成；原版模型的正式身份检查仍独立保留。
