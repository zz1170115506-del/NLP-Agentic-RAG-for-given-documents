# 1.1 接口约定

Agent 不依赖检索器内部算法、向量模型、索引路径或框架，只接收可调用函数。Python 3.11+，同步接口；异步检索请在你们的包装层转为同步调用。

## 必需：一个统一检索函数

```python
def search(query: str, top_k: int = 5) -> list[dict]:
    ...
```

返回有序结果，第一条相关性最高：

**`top_k` 按片段（检索结果条目）计数，不按不同文档计数。** 例如排名为 `A片段1、A片段2、B片段1、C片段1`，`top_k=3` 返回前三项，允许重复 `doc_id`。适配器保留排序，不自行按文档合并。检索层若内部限制单篇文档的片段数量，应说明该排序策略。

证据处理约定：

- 同一文档的不同片段分别保留，分配各自的 `evidence_id`；不会用 `doc_id` 作唯一键覆盖。
- 去重优先使用 `doc_id + start/end + 原文哈希`；无完整范围时使用 `doc_id + chunk_id + 原文哈希`；这些位置标识都没有时退回 `doc_id + 原文哈希`。
- 相同文字出现在不同位置或不同 `chunk_id` 时分别保留；同一范围、相同文字的重复命中复用已有 `evidence_id`。
- `visited_documents` 是文档集合，按 `doc_id` 去重；`evidence` 是证据列表，保留多个片段；`supporting_evidence` 和最终 `state.selected_evidence_ids` 引用片段级 `evidence_id`，例如 `["E1", "E2"]`。
- `chunk_id/start/end` 会保存在证据和完整轨迹中，并随被选入当前上下文的证据提供给模型。上下文可裁剪旧条目或截短文字，完整证据和轨迹仍保留；不保证所有历史片段每一轮都进入模型。

为保证来源可区分，建议每条片段返回稳定的 `chunk_id` 和完整 `start/end`。范围是原始文档的 Python 字符位置，左闭右开；不能使用 token 序号或 UTF-8 字节偏移代替。

```json
[
  {
    "doc_id": "原始文档编号",
    "score": 0.85,
    "snippet": "实际原文片段",
    "source_url": "https://原始来源"
  }
]
```

- `doc_id`：非空字符串，必须能定位原文。
- `score`：有限数值，不允许 NaN、Infinity 或布尔值。排序由检索层决定，Agent 保留其顺序。
- `snippet` 或 `text`：至少提供一个非空的实际原文字符串。请不要返回模型编写的“证据”。
- `source_url`：可选字符串；有来源时应保留。
- `chunk_id`、`title`、`start`、`end`：可选；范围采用原始 Python 字符串的字符位置，左闭右开。
- 无结果：返回 `[]`。失败：抛异常，由 Agent 记录并反馈给模型。
- 同样接受 `{"results": [...]}` 外层封装。

如需检索方式选择，可以增加 `method="hybrid"` 参数。适配器会根据函数签名决定是否向模型展示该参数。Agent 始终只看到一个 `search` 工具，不给不同检索器分别注册工具。

## 可选：文档读取与查词

```python
def open_document(doc_id: str, start: int = 0, length: int = 6000) -> dict:
    return {
        "doc_id": doc_id,
        "text": "实际原文范围",
        "source_url": "https://原始来源",
        "start": start,
        "end": start + len("实际原文范围")
    }

def find_in_document(doc_id: str, query: str, window: int = 250) -> dict:
    return {
        "doc_id": doc_id,
        "source_url": "https://原始来源",
        "matches": [{"text": "命中及附近原文", "start": 0, "end": 8}]
    }
```

未提供的辅助函数不会向模型注册，也不会因为模拟同名工具而虚报实现。若返回不同的文档编号，适配器会报错。

## 接入方式一：在组内主程序中调用

```python
from search_agent.agent12 import create_agent
from search_agent.config import load_config
from your_retrieval_module import search, open_document, find_in_document

config = load_config(enable_skills=False, require_evidence=True)
agent = create_agent(
    search,
    open_document_fn=open_document,
    find_in_document_fn=find_in_document,
    config=config,
)
result = agent.run("用户问题", question_id="q001")
```

上例默认检查课程指定模型家族。使用其他模型开发时，需要显式配置 `development_only=True` 和与实际模型一致的 `expected_model_family`；不要把这类运行当作正式课程主模型结果。

## 接入方式二：命令行工厂

对本仓库的 `rag_agent` 项目，使用专用 `--peer-project/--peer-config` 入口，见 [PEER_INTEGRATION.md](PEER_INTEGRATION.md)。它负责路径解析、来源记录和有界查词。以下工厂入口用于其他后端。

创建你们自己的 `peer_backend.py`：

```python
from search_agent.ports import FunctionBackend
from your_retrieval_module import search, open_document, find_in_document

def create_backend():
    return FunctionBackend(
        search,
        open_document_fn=open_document,
        find_in_document_fn=find_in_document,
    )
```

运行：

```powershell
python -m search_agent.agent12 --backend peer_backend:create_backend --question "用户问题"
```

已有对象实现这些方法时，工厂直接返回该对象也可以。工厂负责加载自己的索引与配置，Agent 不猜测文件位置。API 密钥由 Agent 自己读取本地 `.env`，不要传入检索函数。

对象可另外提供 `close()` 和 `describe()`：命令行运行结束会关闭后端，`describe()` 返回的检索来源元数据写入结果 `backend`。库调用时由主程序在全部问题处理完后关闭共享后端，可使用 `with FunctionBackend.from_backend(backend) as port:`。

## 1.3 与 1.4 对接

- 1.3：核心 Agent 保留 `enable_skills` 和 `skills_dir`，由同学提供合法技能目录后启用；独立 1.2 入口默认关闭技能，不依赖技能文件。
- 1.4：调用同一个 `agent.run`。通过 `on_event` 接收按时间顺序的字典事件；最后使用 `answer`、`evidence`、`supporting_evidence`、`state`、`tool_calls` 和 `total_tokens` 展示结果。
- 原始轨迹中的检索结果是未经证实的观测；`supporting_evidence` 是模型选择的引用，不意味着程序已自动证明事实正确。
