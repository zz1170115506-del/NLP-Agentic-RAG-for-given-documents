# 组内 Agent 检索后端接入

仓库内已提供 [1.2 Agent 运行入口与联调说明](../agent12/PEER_INTEGRATION.md)。无需复制检索源码，进入 `agent12/` 后用 `--peer-project ..` 即可接入本项目。

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
