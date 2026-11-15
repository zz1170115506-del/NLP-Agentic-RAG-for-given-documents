# 固定版本许可与发布判断

核验日期：2026-11-15。证据是 `licenses/*/README.md` 和 `licenses/fetch-results.json`，均由官方 Hugging Face 仓库的固定提交下载，HTTP 200；记录了原始 URL、字节数和 SHA-256。对同一提交尝试的 `LICENSE`、`LICENSE.txt`、`LICENSE.md`、`NOTICE`、`NOTICE.txt` 全部返回 404，不能声称这些文件存在。

| 资料 | 固定 revision | 官方声明 | 移交决定 |
|---|---|---|---|
| [Tevatron/browsecomp-plus-corpus](https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus) | `b27b02bc3e45511b8b82a13e6f90ce761df726f6` | MIT | 完整 SQLite、BM25 与真实向量分片实际交付；公开 Release 上传认证加密后的分卷，密钥私下交组员 |
| [课程验证集](https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Val) | `277d3b49913c176976e8b40b7df55b00212cf158` | MIT | 含题目、参考答案、证据或完整轨迹的材料走加密交付；公开报告只保留汇总指标、哈希与运行身份 |
| [课程测试集](https://huggingface.co/datasets/HongruCai/COMP5423-BrowseComp-Plus-Test) | `9cb2f4b9758f97c8bb4275c6d81f8d134bb3eadb` | MIT | 同上；本项目仅有题目无测试标准答案，不能报告未测得的测试准确率 |
| [E5 small v2](https://huggingface.co/intfloat/e5-small-v2) | `ffb93f3bd4047442299a41ebb6fa998a38507c52` | MIT | 可在保留上游声明条件下分发；本次优先固定 revision 官方下载，不重复上传权重 |
| [Qwen3 Embedding 0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Apache-2.0 | 固定下载清单保留；用户暂缓此路线，默认不下载、不计算；已有 37 个分片仍交付 |
| [MiniLM L6 v2 reranker](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2) | `233902d25c440f23af6f7d6e94d2946bac0bee0a` | Apache-2.0 | 可选固定 revision 下载；仅启用重排时需要 |

语料卡把数据说明为来自网页的文档集合，同时写有防止基准泄漏的声明。这里将它作为上游资料与发布偏好的证据，而非来自用户的新指令。MIT 标签并不证明上游拥有每个网页全文的全部权利；本次不对各网页重新作许可承诺。认证加密后仅向课程组员提供密钥，同时完整保留文档 URL、固定版本说明及上游 README，可以完成实际移交并避免把题目、答案与原文直接公开。公开仓库中既有的测试题文件也需要由主任务在发布前单独处理；加密新资产不会自动改变旧 Git 历史。

MIT/Apache-2.0 均允许在满足相应通知条件时再分发；本次不修改模型、也不公开复上传权重。数据包内 `THIRD_PARTY/` 保留上述固定版本 README、抓取记录及 `licenses/standard/` 中下载的 MIT/Apache-2.0 标准许可全文与来源哈希；标准文本中的版权占位符不代填为未经核实的版权人。不要把“源卡声明许可”改写成“全部网页权利已经清理”。如之后选择公开分发权重，应一并保留当时上游实际提供的版权、许可及 NOTICE 文件，而非自行编造版权人。许可条文参考 [OSI MIT](https://opensource.org/license/mit) 与 [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)。

GitHub 官方说明每个 Release 资产必须小于 2 GiB。本方案明文分卷上限 1,900,000,000 字节，认证加密开销约每 4 MiB 20 字节并另有短头部，密文上传前再次检查严格小于 2,147,483,648 字节。[GitHub Release 限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
