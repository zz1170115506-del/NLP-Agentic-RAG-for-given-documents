# 组内 Agent 检索后端接入

在仓库根目录安装本项目，使用同一份配置准备语料和索引，然后通过 `rag_agent.peer_backend:create_backend` 接入。配置指定语料库、索引目录和检索方法。配置与索引匹配时，可直接使用已有索引。

用合成语料和 BM25 先确认接口。索引建好后，在装有同僚 Agent 的同一 Python 环境中执行最后一条命令。

```bash
python -m pip install .
rag-agent prepare --config configs/demo.yaml --source tests/fixtures/corpus.jsonl
rag-agent index --config configs/demo.yaml --methods sparse
RAG_BACKEND_CONFIG=configs/demo.yaml python -m search_agent.agent12 \
  --backend rag_agent.peer_backend:create_backend --question "Where is Cedar University located?"
```

向同僚的 `create_agent` 直接注入函数时，可用以下入口。

```python
from rag_agent.peer_backend import create_backend
from search_agent.agent12 import create_agent

backend = create_backend("configs/demo.yaml")
try:
    agent = create_agent(
        backend.search,
        open_document_fn=backend.open_document,
        find_in_document_fn=backend.find_in_document,
    )
    result = agent.run("Where is Cedar University located?", question_id="q001")
finally:
    backend.close()
```

上面的 demo 配置只控制检索侧使用哪套本地索引。Agent 的模型和 API 配置由同僚的入口读取。

| 函数 | 返回行为 |
|---|---|
| `search(query, top_k=5)` | 返回按相关性排序的 `list[dict]`。每项提供 `doc_id`、`chunk_id`、`score`、`snippet`、`source_url`、`start`、`end`。`top_k` 支持 1–20，按片段计数。同文档不同片段可分别出现。无匹配时返回空列表。 |
| `open_document(doc_id, start=0, length=6000)` | 返回文档 ID、来源 URL、原文以及实际 `start/end`。若范围跨越文档末尾，`end` 为实际末尾位置。 |
| `find_in_document(doc_id, query, window=250)` | 对指定文档做不区分大小写的字面匹配，返回包含原文和 `start/end` 的 `matches`。`window` 指每侧保留的字符数。无匹配时 `matches` 为空。 |

坐标是 Python 字符下标，范围为左闭右开。每条搜索结果都校验 `document.text[start:end] == snippet`。缺失文档、无效参数和索引错误以异常交给 Agent。两路向量检索为模型长度限制额外切出的窗口各有自己的位置和片段 ID。RRF 只合并具有相同片段 ID 的命中。

联调时可用同一篇文档中的两段证据，检查两段均保留为独立结果，并确认选入模型上下文时仍携带 `chunk_id/start/end`。本仓库测试覆盖检索侧返回，模型上下文需与同僚的实际 Agent 一起核验。

## 可选本地重排

工厂、CLI 和仓库 Agent 继续共用 `SearchService.search`。`rerank_enabled` 默认关闭，
`candidate_depth: null` 保持每路 `min(top_k * 3, 60)`。开启后，仅 hybrid 路径在片段 RRF
之后重排候选，不改变三个同步接口。单路检索保持原行为；仓库 Agent 在 hybrid 配置下
仍可选择单路方法，因此真实轨迹必须核对实际方法。

- `rerank_depth`：RRF 前缀评分数量；实际为 `min(候选数, max(rerank_depth, top_k))`。
- `rerank_batch_size`、`rerank_max_length`、`rerank_max_windows`：分别限制批大小、完整
  query–passage 对的 token 数、每候选窗口数。连续窗口的最大 logit 用于排序，等分保留 RRF 顺序。
- 模型和 tokenizer 使用同一不可变 revision，首次非空重排才加载。超过窗口上限会显式记录
  `omitted_windows`；上限至少 2 时包含首尾，上限为 1 时只取尾部。
- 返回原始完整 chunk，`chunk_id/start/end/snippet` 不变；评分窗口的绝对坐标另存诊断。
- 关闭时公共 `score` 仍为 RRF 分数；开启且成功时是 `1 / 最终名次`，用于比较本次结果顺序，
  不是概率。已评分前缀在前，未评分尾部保持原 RRF 顺序；原 RRF 分数、模型 logit 分开保存。
- `rerank_on_error: raise` 为默认失败策略。显式选择 `rrf` 才回退，并记录 `fallback_rrf`；
  不将回退算成重排成功。`SearchService.last_diagnostics` 提供逐路候选、计时及评分状态，
  不向同步平面列表增加字段。

固定真实小样本配置见 `configs/rerank-eval-{a,b,c,d}.yaml`；数据/索引需按
[两轮评估报告](2026-11-11--local-rerank--r02--round-review.md) 准备，不能直接指向不同语料。
默认设置仍关闭重排。低依赖接口检查：`python scripts/smoke_rerank.py`；此检查明确使用
神经检索与评分测试替身，真实模型结果另见报告。
