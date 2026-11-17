# 已归档材料与原始日志

公开可读的逐题记录和终端摘要适合快速比对。需要完整问答轨迹、原始模型消息、课程题面、工作底稿或早期脚本时，可按 [逐文件目录](artifacts-inventory.json) 的路径查找对应代码版本、历史发布包或本次补充包。

## 本次清点

核对了 3,071 个项目文件路径，包括早期两处项目工作副本、官方接口和百炼的开发验收、百题验证和测试、九题修复及两轮向量对照、报告和工作底稿。相同内容跨目录复用，文件路径计数可以大于独有文件数。补充包保存 579 份去重内容，按原目录可还原 608 个文件。其余 2,463 个路径对应已提交源码或既有发布材料。

| 文件目录分类 | 核对路径 | 从补充包还原的路径 |
|---|---:|---:|
| `acceptance` | 182 | 37 |
| `course-validation` | 199 | 198 |
| `deliveries` | 145 | 26 |
| `early-reranking` | 215 | 201 |
| `review-support` | 88 | 34 |
| `review-work` | 619 | 72 |
| `runs` | 225 | 0 |
| `runtime-support` | 1,370 | 13 |
| `task-briefs` | 8 | 7 |
| `transport` | 20 | 20 |

本目录按文件内容核对了五次已发布运行记录的映射清单，项目总验收、验证失败复盘、证据保留修复、256 维 Qwen、256 与 2560 维 Qwen 清单分别有 346、580、76、34 和 26 条原始文件记录。另与首轮数据包独立还原的 2,540 项清单核对；目录中的 `program-acceptance-20261115:data` 指向该版本的数据分卷。多个版本共同引用同份文件时，目录选择其中一个可恢复位置。对于早期提交的相同文件，`git:` 值指明可直接浏览的固定提交。各版本的向量文件、冻结数据库、已有语料分卷和模型下载入口仍可从对应发布获取。[既有发布和代码入口](previous-github-materials.json)

清点涵盖工作区实际存盘的项目文件。工作区外的个人聊天、终端滚屏历史、凭据、构建缓存、虚拟环境和可再生的临时副本不在交付目录内。团体版归档对识别出的真实 API 凭据、签名参数和本机账户路径作了替换。有此处理的补包路径会标记 `redacted: true`。部分历史软件 ZIP 经成员文件逐一检查，环境文件和密钥文件不会写入新归档。课程原始资料和模型原始回复随密文交付，组员需通过项目负责人私下取得对应资料密钥。

## 解密并还原补充包

在本次 Git 源码根目录操作。从本次 Release 下载文件名以 `team-supplement` 开头的三个附件至 `download/`。把环境变量 `TEAM_SUPPLEMENT_KEY` 指向本机收到的密钥文件；Python 环境需要安装 `cryptography`。

```sh
(cd download && shasum -a 256 -c team-supplement.SHA256SUMS)
python scripts/handoff/handoff_crypto.py decrypt \
  --manifest download/team-supplement.ENCRYPTED_VOLUMES.json \
  --key-file "$TEAM_SUPPLEMENT_KEY" --output work/team-plain
python scripts/handoff/handoff_archive.py verify \
  --volumes work/team-plain/VOLUMES.json --extract work/team-archive
python scripts/handoff/restore_team_supplement.py \
  --source work/team-archive --output work/team-files
```

在 `work/team-files/` 内可按可读路径打开补充材料。私有的运行原始记录中包含题干、模型收到的证据和完整回复，请通过小组内部渠道分析。解密后还原程序会重新核验每个内容文件的 SHA-256、长度和映射路径。[补包签收记录](artifacts-receipt.json)
