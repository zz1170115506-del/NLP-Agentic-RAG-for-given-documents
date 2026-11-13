# 1.2 Agent 与同学 1.1 检索的接入说明

本目录是接入本仓库 1.1 检索的 1.2 Agent 实现。运行时使用`SearchAgent`决策循环，检索排序使用`PeerBackend → SearchService`；`search_agent/peer.py`负责路径处理、来源记录和有界文档查词。

**2026-11-14集成入口：** 从仓库根目录安装项目后，使用`rag-agent ask/predict --config configs/course-synthetic-agent12.yaml ...`或网页选择Agent 1.2配置。此路径读取根目录`.env`，通过共同HTTP provider保留原始响应/用量和服务调用ID，自动选择skills、按实际可见证据ID生成六字段记录。两端同题诊断均5/5记录及引用通过；当前完整BM25可用，完整神经索引未完成。官方验证为基线运行90/100题，尚未完成。范围、正式校验、额度阻碍及复现入口见[最新回传](../docs/task_NLP-Agentic-RAG-for-given-documents_全项目程序验收与缺口补齐_prompt_1return.md)。

下列`python -m search_agent.agent12`为独立组件开发入口；其模型、`.env`位置和输出不同于根目录的课程集成入口。

仓库根目录的 `src/rag_agent/` 提供 1.1，`agent12/search_agent/` 提供本次 1.2。没有提交密钥、模型权重和课程全文索引。

## 先运行不花 API 的检查

需要 Python 3.11+。从仓库根目录进入本组件后运行：

```powershell
cd agent12
python -m pip install -r requirements-peer.txt
python -m unittest discover -s tests -v
python scripts/prepare_peer12.py --peer-project ..
```

核心 Agent 只用标准库；接入同学的 BM25 需要 Pydantic 2、PyYAML 和 NumPy。这里不安装同学完整的向量检索依赖，也不下载嵌入模型。测试中真实调用同学的 BM25，其决策模型使用 mock，不产生 API 费用。

准备脚本建立 **6 篇合成文档、134 个片段** 的测试库，输出 `outputs/peer12_sample/peer-config.json`。前三篇沿用同学测试中的虚构事实，另外三篇检查同文档多片段、长文和大量重复查词。它们不是课程数据。文档、分块与来源都有指纹，运行记录明确标为合成来源。

## 调用你的 DeepSeek 开发模型

复制 `.env.example` 为 `.env`，只在本地填写密钥。当前开发模型配置为 `deepseek-flash`，运行时显式添加 `--development-model`。

`--peer-config` 的相对路径以 **peer 项目根目录** 为基准。这里先把刚才输出的配置解析为绝对路径：

```powershell
$peerConfig = (Resolve-Path ./outputs/peer12_sample/peer-config.json).Path
python -m search_agent.agent12 --peer-project .. --peer-config $peerConfig --development-model --question "In which city is the university attended by the designer of the Lumen Observatory?" --output ./outputs/my_peer_run.json
```

Agent 密钥读取位置是 `agent12/.env`，也可用环境变量覆盖；不会读取同学项目中的 `.env`，不会改变当前工作目录。结果文件已存在时会在调用 API 之前拒绝覆盖。结束后自动关闭检索数据库。

`deepseek-flash` 在这里仅用于开发联调，结果标记 `development_only=true`。正式课程实验仍需确认指定主模型；合成案例和开发模型结果不能作为正式准确率。

## 后续换成同学的真实课程索引

同学交付以下内容后，直接更换 `--peer-config`：

- `documents.sqlite` 原文库；
- 与它的 corpus fingerprint、chunk_size、chunk_overlap 匹配的索引目录；
- 指向这两处的配置文件。

配置示例：

```json
{
  "store_path": "E:/course-data/documents.sqlite",
  "index_dir": "E:/course-data/indexes/default",
  "method": "sparse",
  "chunk_size": 900,
  "chunk_overlap": 150
}
```

相对的 `store_path/index_dir/skills_dir` 都以peer项目为基准。配置中的分块参数必须填建库时的实际值。语料/索引不提交Git；本轮执行机忽略目录已完成全语料BM25，完整神经索引和正式100题验收状态见顶部更新。

可用 `--retrieval-method sparse|encoder|instruction|hybrid` 覆盖配置中的检索方式。模型只看到一个 `search(query, top_k)`，方法由后端配置决定。**同学的 hybrid 要求 sparse、encoder、instruction 三套索引均已建好**；缺失时不会自动降级。当前合成库只建 sparse，切换向量方式前需由 1.1 提供相应依赖、权重和索引。

## 证据与上下文规则

- `top_k` 计片段，允许相同 `doc_id`；检索排名原样保留。
- 同一文档不同片段分别保存 `chunk_id/start/end` 并分配 E1、E2 等证据编号，模型可分别引用。仅完全重复的同一原文范围合并。
- `visited_documents` 按文档记录；`evidence` 按片段记录；`supporting_evidence` 与 `state.selected_evidence_ids` 引用证据编号。
- 空结果和没有新增证据的搜索会提供不同反馈，并更新 `stalled_searches`，供模型改写查询。
- 文档查词默认最多返回 8 个命中，最多扫描前 2,000,000 个字符。返回 `truncated/scan_truncated/next_start`；需要继续阅读时使用 `open_document`。内部扫描不增加 Agent 对外的工具调用计数。
- 模型上下文优先保留最近的完整 assistant/tool 配对；长工具结果压缩为原文前缀，并标注 `text_truncated/visible_text_end`。`start/end` 始终是完整观测范围，`visible_text_end` 是本轮展示到的位置。
- 更早轮次可裁剪，独立证据与完整 `trajectory` 保留全部原文、调用和 API 返回。程序不把模型进度笔记当作原文。

## 本次验证

原开发工作区全项目 **103 项测试通过**；本目录包含其中 **70 项 Agent 与接入测试**，可按上述命令独立执行。最终版本使用真实 DeepSeek API 和同学的真实 BM25，以下四个受控案例均完成：

| 案例 | 实际行为 | 答案 | 工具次数 | API token |
|---|---|---|---:|---:|
| 多跳检索 | top_k=1，读到学校后再查询学校 | Northport | 2 | 4,438 |
| 空结果恢复 | 首次无结果，随后改写并命中 | Northport | 2 | 4,375 |
| 同文档多片段 | top_k=2 返回同文档两个片段，两条均被引用 | Nara Vale; 1977 | 1 | 2,874 |
| 长文上下文 | 保留 12,000 字符完整原文；请求最大 5,095 字符 | Elara Venn | 1 | 2,708 |

最终四次案例共 10 次 API 请求、14,395 token。修复前后的开发尝试也保留在验证目录中，总计 49,276 token。早期长文案例曾达到轮次上限；保留压缩工具配对后，同题只读一次便完成。完整记录见 `verification/peer/`，摘要见 `verification/peer-summary.json`。

这四个案例是接口与控制流程检查，包含为触发边界情况而指定的操作要求，不是自然问题上的准确率测量。

可重新核对记录，不会访问模型：

```powershell
python scripts/verify_peer12_runs.py --peer-project .. --runs-dir ./verification/peer --output ./outputs/rechecked-summary.json
```

组内主程序仍可用 `create_agent(search, open_document_fn=..., find_in_document_fn=...)` 注入接口，具体字段见 [INTERFACE.md](INTERFACE.md)。本次独立入口默认关闭 1.3 技能，保留后续启用技能和 1.4 接收事件、展示证据的接口。
