# 本轮加密证据移交

公开Release：[validation-failure-review-20261115](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/validation-failure-review-20261115)。

| 资产 | 大小（bytes） | SHA-256 |
|---|---:|---|
| [review-evidence.course-data.tar.gz.part00001.aead](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/download/validation-failure-review-20261115/review-evidence.course-data.tar.gz.part00001.aead) | 39726109 | `ffccf889e01b462f75af4deb1dddb229fdc228596cd3e71255612b9b7655fa8a` |
| [ENCRYPTED_VOLUMES.json](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/download/validation-failure-review-20261115/ENCRYPTED_VOLUMES.json) | 1039 | `beba9a85f6e18d0fb0b648295d99cdfa7a5444dd3f05d6b6a776e543b12eb1f2` |

算法为分帧AES-256-GCM，package_id=`c291564fab6aee0b722f2d24f1b45962`；key_id=`8b90ab2763a2112804bb857d`仅用于本地配对，不是密钥。每帧和结尾均认证；恢复时核对密文、完整压缩流和每个文件SHA-256。加密明文归档SHA-256为`6d7676e2459907840e63a2f3349e98138fad06134e8694d067946b0dd529bae2`。

包内580个证据文件，另加PATH_MAP，共581项；证据文件总129,207,813 bytes。包含9题历史与百炼完整记录、真实题目/官方参考/答案/规范化评测、10条成对API记录、全部离线重放、原文片段、必要文档和两份冻结核心源码包。旧100题原预测也包含在加密包，用于按原SHA复核；不纳入新的9题成绩。详细逻辑路径与逐文件hash在解密后的PATH_MAP/HANDOFF中。

归档不包含环境文件、API key、解密key、完整语料数据库或计算缓存；原始预测字节保留。固定全量语料/BM25从[上轮Release](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)恢复。本轮密钥单独保存于本地交接目录`private/review.key`，权限600，未上传；其可见文件位置只在本地交接索引提供。

源码包`validation-review-source.zip`由发布提交的git archive产生；其SHA和交付commit见Release资产`RELEASE_FILES.json`。恢复/重验命令见[REPRODUCE.md](REPRODUCE.md)。不能仅凭下载成功认定内容可信：使用清单核验，再执行认证解密、逐文件校验和逻辑路径恢复。
