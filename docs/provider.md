# 指定模型与服务映射

核对日期：2026-11-10。课程 PDF 指定 **DeepSeek-V4-Flash**；不能自动升级成 V4.1、改用其他推理模型，或把检索 embedding 模型当作 backbone。

## 本次核对

1. [DeepSeek 更新记录](https://api-docs.deepseek.com/updates/) 说明 2026-09-10 后旧 `deepseek-v4-flash` 请求被路由到 V4.1。
2. [DeepSeek 当前入口说明](https://api-docs.deepseek.com/quick_start/agent_integrations/) 明确旧别名现由 V4.1-Flash-1017 提供。因此 `Settings.check_model_identity()` 阻止在 `api.deepseek.com` 上声称运行原模型。
3. [OpenRouter V4 Flash 0731 页面](https://openrouter.ai/deepseek/deepseek-v4-flash-0731) 将其标为原 V4 Flash 的 GA 版本，并说明工具调用支持。
4. 实际请求 [OpenRouter 模型目录 API](https://openrouter.ai/api/v1/models) 得到 `deepseek/deepseek-v4-flash-0731`，显示名称 `DeepSeek: DeepSeek V4 Flash 0731`，`supported_parameters` 含 `tools`、`tool_choice`。

`configs/openrouter.yaml` 依据以上目录信息设置 endpoint/model/note。**这证明本次读取的目录映射，不证明已成功调用推理 API**。本轮环境没有 `LLM_API_KEY`，真实工具调用、usage、服务限流与回答质量均未实测。

## 接入方式

使用 Chat Completions HTTP 协议：`POST {LLM_BASE_URL}/chat/completions`，发送 `model/messages/tools/tool_choice/max_tokens/temperature/stream`。密钥只在 Authorization header 中使用。业务模块不引入其他厂商推理 SDK。不同服务需提供同一模型和兼容工具协议；若服务有额外专有字段，应扩展 `llm/provider.py`，不把条件散布到 Agent 或网页。

对 `openrouter.ai`，adapter 另发送 `reasoning: {enabled: false, exclude: true}`，采用同一 backbone 的关闭 thinking 基线。2026-11-10 的模型目录显示 V4 Flash 0731 的 reasoning 并非强制，默认开启，并支持 `none`；[OpenRouter reasoning 文档](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) 说明关闭开关和 Chat Completions 的返回内容排除选项。这里同时关闭 thinking 并排除其返回内容，避免请求隐藏思维链，也避免默认 thinking 产生需要跨工具轮次回传的额外块。`exclude: true` 单独使用仅隐藏返回内容，不等于关闭计算。该服务专用字段只在 provider adapter 设置，不发送给其他兼容服务。已用 MockTransport 核对请求字段；真实服务是否遵循及具体响应仍待 live smoke test。

提供自己的服务时，配置 `LLM_MODEL_VERIFIED` 与 `LLM_MODEL_VERIFICATION_NOTE`，并保留可复查的模型映射依据。未知 deployment ID 的实际权重无法靠本地代码验证；这部分依赖服务文档及组员核实。已知错误模型和可变 `latest` 别名会被拒绝。响应 model 与配置 ID 不一致也会停止，需先核对服务是否返回了等价的另一标识，而不是静默放行。

## 小样例验证

先仅对合成语料调用一次，避免直接运行 100 题。把 `configs/openrouter.yaml` 复制为本地配置，设 `method: sparse`、`store_path: data/demo.sqlite`、`index_dir: indexes/demo`，并保持原模型映射设置；给出本地密钥后执行：

```bash
rag-agent check-config --config configs/live-smoke.yaml --live
rag-agent ask --config configs/live-smoke.yaml 'When did the Copper Museum open?' \
  --output outputs/live_smoke_prediction.jsonl
```

检查输出的 run_start、api_attempt、assistant usage、工具配对、答案 evidence 和 run_end。真实失败保留轨迹，缺失 usage、超时后未知用量、错误模型或证据不足均不符合正式导出条件。网络重试会有限退避，每次返回的 usage 都要计入；不能以字符数估算替代服务账单。
