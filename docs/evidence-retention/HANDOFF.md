# 修复交付与加密证据

完整结论见[验收报告](acceptance-report.md)，重跑和离线复核命令见[REPRODUCE.md](REPRODUCE.md)。

- 工作分支：`codex/evidence-retention-fix`，未合并主分支。
- 新发布页：[evidence-retention-fix-20261115](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/evidence-retention-fix-20261115)。旧复盘发布保持不变。
- 最终运行源码提交：`a476ef7b062bb9a0deac0db54b5895daa5e30827`；包含本报告和辅助审计工具的最终交付提交记录在Release的`RELEASE_FILES.json`中。
- 两轮各九题真实调用均保留；最终v2为3/9匹配，6题弃答。九题均完成运行和检查，不能解释为九题全部答对或完整语义通过。

## 附件

`evidence-retention-source.zip`为最终交付提交的完整已跟踪源码；`ENCRYPTED_VOLUMES.json`和`.aead`为独立加密证据包。`SHA256SUMS`列出全部下载资产校验值，`RELEASE_FILES.json`绑定分支、提交及资产SHA。公开报告、恢复脚本一并提供。

密文：`retention-evidence.course-data.tar.gz.part00001.aead`，9,633,941字节，SHA-256：

```text
94af228ef53c21ce7b1fcaeaf7813d907220383bb8235ef83f0a67af919b248c
```

包内有76份原始/审计文件，加路径映射共77项归档有效载荷。本地已完整解密、展开、恢复逻辑目录，并校验全部文件SHA。明细见[encrypted-evidence-manifest.json](encrypted-evidence-manifest.json)。发布后另外从远端重新下载并恢复；最终远端验收记录放在用户本地交付目录，避免修改已经发布的冻结源码。

逻辑目录包括原九题基线、v1/v2全部预测与评分、输入、真实请求审计、独立条件核查、两版冻结运行源码及测试记录。完整语料与BM25沿用[前次移交](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)，本包不重复收录。

解密Key为本地交付目录下`private/retention.key`，权限0600，父目录0700。新证据包采用独立随机Key，不复用旧交付Key。API Key与解密Key均不上传；需要交接密钥时由用户使用自己的安全渠道处理。

本轮验收只运行sparse BM25；Qwen继续搁置，E5后台任务与本轮成绩分开记录。
