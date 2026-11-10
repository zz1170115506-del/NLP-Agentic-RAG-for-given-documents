# 检索实现依据与边界

核对日期：2026-11-10。以下来源只用于实现检索程序；agent 的回答证据只来自导入的固定语料，不使用在线网页搜索。

## 官方依据

- [固定语料数据卡](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus)：`train` 集合，100,195 条；字段为字符串 `docid`、`text`、`url`。`data/prepare.py` 先解析实际 Hugging Face commit SHA，再按该版本流式读取；导入记录字段、实际条数、限制和内容指纹。没有下载问答标签或其他数据集。全量导入仍需显式运行。
- [SQLite FTS5 官方说明](https://www.sqlite.org/fts5.html)：`retrieval/sparse.py` 使用真实 FTS5 BM25，`unicode61 remove_diacritics 2` 分词，不做词干提取或停用词移除。SQLite 的 BM25 越小越好，返回时取负数，使统一接口中分数越大越好。检索结果按最佳片段汇聚到文档级。选择此实现是为了增量磁盘写入和低依赖；大量语料不用一次装入 Python 内存。
- [E5-small-v2 官方模型卡](https://huggingface.co/intfloat/e5-small-v2)：encoder 使用 `intfloat/e5-small-v2`，查询添加 `query: `，文档添加 `passage: `；对非 padding token 做均值池化，再做 L2 归一化。默认 384 维。`retrieval/embedding.py` 使用 `AutoModel` 真实前向计算。
- [Qwen3-Embedding-0.6B 官方模型卡](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)：第三类检索使用 Qwen3 架构的 0.6B embedding 模型，默认 1024 维；查询格式为 `Instruct: {instruction}\nQuery:{query}`，文档不加 instruction；左侧 padding 后取最后一个真实 token，随后归一化。官方说明要求 Transformers 至少 4.51.0。本项目依赖约束在 `pyproject.toml`。该模型独立于第二类 encoder，不复用向量。

## 本地数据与索引格式

`DocumentStore` 保存原始文档和字符片段。所有 offset 都是 Python Unicode 字符下标，从 0 开始，终点不包含在范围内；**不是 UTF-8 字节下标**。导入时将 `docid` 明确适配成 `doc_id`，拒绝数值 ID，保留 `"001"` 的前导零。相同文档 ID/内容可重复导入以恢复任务，内容冲突报错；不同 chunk 设置或数据来源必须使用新路径。

分块先用可配置的字符窗口和重叠；两类 embedding 在编码前再次检查实际 tokenizer 长度，过长片段递归切分，并保留原文 offset 和重叠，避免只编码长文档开头。过长查询显式报错，供 agent 改写，不静默截断。

- Sparse：`index_dir/sparse.sqlite`，独立磁盘全文索引和完成标记；`sparse.manifest.json` 记录语料指纹、chunking、分词器和 SQLite 版本。
- Dense：`index_dir/{encoder,instruction}/manifest.json`，每 256 个输入片段形成一组可恢复分片；`.npy` 保存 float32 归一化向量，`.jsonl` 保存对应文档、片段、offset 和 URL。
- Manifest：保存模型 ID、请求版本、解析后的不可变版本、维度、归一化、池化、查询模板、instruction、语料指纹、分块参数、分片大小及 SHA256 校验和；配置不兼容就报错。
- 每个 embedding batch 的大小由 `batch_size` 控制；向量文件用内存映射写入/查询。恢复任务校验已完成分片并跳过其编码；未完成分片重建。
- 查询按分片进行精确点积（归一化后的余弦相似度），保留文档级最高分及对应片段。三方法融合按文档名次计算 RRF，每个方法中同一文档只计一次，不相加不同量纲的原始分数。

选择 NumPy 分片精确检索而非 FAISS 是可移植性和可检查性取舍：CPU、MPS、CUDA 都可用于 embedding，磁盘索引不依赖 GPU；查询每次扫描全部向量，**尚未验证在完整语料上的延迟与磁盘成本**。全量完成后可在同一 `SearchService` 接口后替换近似索引；这属于后续优化，并未宣称已实现。

## 验证口径

`tests/test_retrieval.py` 的合成数据验证字段/ID、原文 offset、导入恢复、真实 BM25 的保存/加载与文档去重、RRF、分片恢复和损坏检测、模型配置兼容性，以及 token 预算分割覆盖。

测试中 `SyntheticEmbedder` 是显式注入的测试替身，只验证向量索引接口；其 manifest 标记 `injected_test_stub`，生产入口拒绝将它作为真实模型索引。它的结果不能证明 E5 或 Qwen 的真实检索质量。真实 embedding smoke 的最终执行情况以 [`validation.md`](validation.md) 为准。
