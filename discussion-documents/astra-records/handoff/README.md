> 资料快照，来源提交 `b55b8a6`。[原始文件](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/b55b8a6c5c8d3b9ad7f573c7c5ad22a415041869/docs/handoff/README.md)。采集于 2026-11-17（香港时间）。

# 语料、索引与运行证据的加密移交

`scripts/handoff/` 中的脚本已经用小型合成语料完成独立打包、分卷、加密、解密、解包与校验。本次真实大包已从分片边界冻结的独立快照生成并完成独立恢复验证；以后重新打包仍须先冻结快照。这里的路径都相对代码根目录；不读取 `.env`，不保存 API 密钥，不发模型 API 请求。

## 实际资料与体积

正式快照时间为 2026-11-15 14:48:03（香港时间）。完整实际验收记录见 `data-verification.json`；较早的 `inventory_observation.json` 仅保留为历史观察，不代表本次交付进度。

- 完整文档 SQLite：8,336,547,840 字节，100,195 文档、4,345,592 原始块。
- 完整 BM25：6,670,352,384 字节，4,345,592 记录；语料指纹 `ea8764233b0d4a76d050842e290805a0f154858084dfd0430ba8c0d9c555025f`。
- E5 冻结快照：313,344 原始块、316,662 向量、1,224 分片，`ready=false`。原索引已在独立快照生成后继续构建；本次包的进度固定为上述值。
- Qwen：9,472 原始块、9,722 向量、37 分片，`ready=false`、`user_deferred`；未启动新的 Qwen 计算。
- 模型快照有效文件合计约 1.434 GB，未重复打包。固定版本与精确文件大小见 `MODEL_DOWNLOADS.json`；默认下载 E5，Qwen 与重排模型由使用者显式选择。

本次明文压缩档实际为 **6,048,568,944 字节**；认证加密后实际 **6,048,600,182 字节，共 4 卷**。前三卷各 1,900,009,655 字节，第四卷 348,571,217 字节，全部严格小于 2 GiB。整份明文压缩档 SHA-256 为 `dd2d6c63721911ea2b5da21cbd179de3eb3dfd313fa234b092ac71f7a6cf005a`；每卷密文哈希见 `data.ENCRYPTED_VOLUMES.json` 和 `data.SHA256SUMS`。

实测打包 235.540 秒、加密 14.464 秒、独立解密 9.893 秒、完整解包及语义校验 454.731 秒。独立目录中的 2,540 个载荷条目逐一通过 SHA 校验，两份数据库 `quick_check` 与计数通过，全部 1,261 个向量分片及相对链接通过检查。完整轨迹另用 `run-evidence` 包认证加密交付，不与这份数据包混称。上传尚由发布步骤执行，这里不虚构下载链接。

建议额外预留至少 50 GB 以同时保存明文压缩卷、解密卷和完整恢复目录；仅直接恢复时所需空间可更少。原数据、打包中间文件与私钥不应放入公开 Release。

## 发布边界

公开资产只包含代码、脱敏汇总、许可证据、模型固定下载清单、恢复脚本、密文和密文校验清单。完整文档/问题/答案/运行轨迹放在加密资产内。密钥单独保存在本机新建的 `private/` 目录，权限 0600，由用户私下交组员；不要上传密钥、明文分卷、解密后的目录或完整原始日志。许可依据见 `LICENSE_AUDIT.md`。

加密用 `cryptography` 的 AES-256-GCM，每 4 MiB 一帧，完整头部、总卷数、整包 SHA/字节数、HANDOFF SHA、分卷序号、帧序号和长度都参与认证；每个包生成全新的 32 字节随机密钥。最后还有必需的认证结束帧，所以截断、换序和尾部追加都会失败。解密全部成功后才把临时目录改名为正式输出；失败会删除此次临时明文。实现依据为 [cryptography 官方 AEAD 文档](https://cryptography.io/en/latest/hazmat/primitives/aead/)。

## 制作者：冻结、打包与加密

先让 E5 写入者在分片边界停止。不要杀进程、删除锁文件或复制正在写入的数据库。把最终代码提交、源文件实际哈希和运行证据冻结；checkpoint 包不会把部分向量改成完整。下列命令在代码根目录执行；输出放在仓库外的 `../handoff-local/`。先创建该目录，并在专用 Python 3.12 环境安装 `cryptography==50.0.2` 和 `numpy==2.3.5`。

```bash
mkdir -p ../handoff-local
python scripts/handoff/handoff_archive.py inventory \
  --source . --output ../handoff-local/frozen-inventory.json

python scripts/handoff/handoff_archive.py pack \
  --source . --output ../handoff-local/data-package \
  --expected-inventory ../handoff-local/frozen-inventory.json \
  --license-evidence docs/handoff/licenses --writers-stopped --execute

python scripts/handoff/handoff_crypto.py encrypt \
  --volumes ../handoff-local/data-package/VOLUMES.json \
  --output ../handoff-local/data-encrypted --label data \
  --key-file ../handoff-local/private/data.key
```

`pack` 先取得两路构建锁，用 SQLite backup API 生成包含已提交 WAL 内容的一致副本；不把 `.backup.sqlite`、WAL、SHM、journal 或 build-lock 文件当作数据传递。仅复制 manifest 明确列出的分片并核验其 SHA-256。两条 BM25 链接恢复为 `../course-full/sparse.sqlite` 和 `../course-full/sparse.manifest.json`。数据库备份后的文件字节可能与原文件不同，交付哈希对应备份产物，不伪称是原文件哈希。

完整运行轨迹另包：先列出已完成文件的相对路径 JSON 数组，再执行 `pack_selected_files.py --source . --include-list ... --output ...`；随后用 `handoff_crypto.py encrypt --label run-evidence ...` 加密，使用另一枚新 key。仅显式列出的常规文件会进入包，`.env`、密钥与私有目录会被拒绝。上传时给两个 `ENCRYPTED_VOLUMES.json` 分别取唯一资产名，例如 `data.ENCRYPTED_VOLUMES.json` 和 `run-evidence.ENCRYPTED_VOLUMES.json`；其内部列出的密文文件名已由 label 区分。

## 接收者：校验、解密、恢复

需要 Python 3.12、`cryptography==50.0.2`、`numpy==2.3.5`。下载同一包的公开 manifest 和全部密文资产到同一目录；从用户私下获取对应 key 文件并设置 0600。下例假设脚本在当前目录，下载文件在 `downloads/`，key 在 `private/`。

```bash
chmod 600 private/data.key
python handoff_crypto.py decrypt --manifest downloads/data.ENCRYPTED_VOLUMES.json \
  --key-file private/data.key --output decrypted-data
python handoff_archive.py verify --volumes decrypted-data/VOLUMES.json \
  --extract restored-data --semantic
```

第一条命令检查密文 SHA、所有认证标签、分卷顺序、完整结束帧、明文 SHA 和合并档案 SHA。第二条流式解包到新目录，拒绝路径穿越与额外链接，逐文件校验，再做 SQLite `quick_check`、文档/块/索引计数、原文切片对应、BM25 FTS 读取、向量 shape/dtype/有限值/metadata 行数，以及相对链接检查。完整语义自检会读取数据库和向量，需要时间；过程不调用模型。

将 `restored-data/data/` 与 `restored-data/indexes/` 放到同版代码根目录下，保留相对结构。最稳妥是在恢复目录安装对应代码后运行，或使用保留链接的复制工具；不要用只复制链接而不复制目标的做法。源文件身份见解包后的 `HANDOFF.json`；Git SHA 可以为空，实际 Python 源文件 SHA 始终记录。

从代码根目录下载 E5，再只做索引状态检查：

```bash
python -m pip install '.[retrieval]'
python scripts/handoff/download_models.py --roles encoder --cache-dir indexes/model_cache
python scripts/index_in_shards.py --config configs/course-full-vectors-cpu.yaml --method encoder --status
python scripts/index_in_shards.py --config configs/course-full-vectors.yaml --method instruction --status
```

第二个状态命令只读 checkpoint，不恢复 Qwen 计算。`download_models.py` 默认只下载 encoder，instruction 必须显式选择。模型库固定 `revision`，文件清单与大小固定；下载器不使用用户 token，也不运行编码。之后恢复 E5 时可以使用 `--device cuda --shards-per-process 1`，但应先安装适合目标 GPU 的 PyTorch，并保持模型 revision、最大长度、切块与归一化设置不变。迁移到另一设备不意味着浮点结果逐位相同；已有分片必须保留原哈希，新增分片单独记录实际环境。

## 已做的小范围验收

`test_handoff.py` 的真实合成包测试覆盖 SQLite/BM25/两路分片、严格小分卷、相对链接、独立恢复、AES-GCM 往返与篡改拒绝。测试不打开项目真实语料，不启动 Qwen 或 API。安装后公开复验摘要见 `software_checks.json`；详细原始日志由制作者随验收证据保留；本次真实大包已完成完整独立恢复验收，见 `data-verification.json`；公开下载链接及上传后复验由最终发布步骤记录。
