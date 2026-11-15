# 全项目程序验收与缺口补齐：第二轮回传

更新日期：2026-11-15，香港时间。已用用户提供的暂选API完成后续修复、真实功能验收、候选对比、三组机制消融，以及验证集和无标签测试集各100题；两批记录与引用审计均为100/100，验证EM为19%。冻结源码已在独立环境重新安装并复现；完整数据/索引与运行证据均完成加密和独立恢复验收。**尚未满足的范围是E5全量索引（仍持续构建）、用户暂缓的Qwen及依赖它的混合检索、后续原版模型身份和最终课程材料。** 本回传不把这些未完成项写成全量就绪。

用户已明确授权用暂选官方 API 继续开发、测试和完整验收，并将在后续另行提供符合原版模型要求的接口。本轮请求 `deepseek-v4-flash`，实际响应保留 `deepseek-flash`，使用 `official_compat`、`model_verified=false`。返回别名不阻塞工作；课程指定原版模型身份单列待后续复核，不将兼容成功改称原版身份已验证。用户已暂缓当前环境的 Qwen 计算；E5 继续构建，Qwen 与依赖它的全量混合路线保持未完成。

所有代码和证据路径均按仓库相对位置书写；原始 API 凭据没有写入本文件。公开的小型脱敏统计随仓库提交到[acceptance_evidence](acceptance_evidence/README.md)。原始题目/答案/轨迹、语料和索引按授权方式进入加密证据包；模型以固定修订及文件清单提供可重复下载方式；本文出现的 `outputs/...`、`work/...` 文字路径均指解包后的相对位置，不冒充GitHub可点击公开资产。

## 1. 当前锁定身份与输入

| 项目 | 当前记录 |
|---|---|
| 工作分支 | `codex/course-final-acceptance` |
| 预测运行源码锁定提交 | `dab7646`；`316c64ad6f6afda727d33b7d7ac2e97d4f6641e5` 已核验为祖先 |
| 预测所用运行源码 SHA-256 | `bdf0d95892e14fb49103f76d768542379812abf620b85962d97553957a3c10d9` |
| 最终候选 | [acceptance-final.yaml](../configs/acceptance-final.yaml)：baseline、全量 sparse/BM25、skills/context/iterative 均启用 |
| 配置 ID | `61d7cc3701b2a42a` |
| 预算 | 每题最多 12 步、24 个工具调用、配置总预算 30,000 tokens；输出上限 1,024，最大重试 2 |
| 固定语料 | `Tevatron/browsecomp-plus-corpus`，revision `b27b02bc3e45511b8b82a13e6f90ce761df726f6`；100,195 文档、4,345,592 源片段 |
| 语料指纹 | `ea8764233b0d4a76d050842e290805a0f154858084dfd0430ba8c0d9c555025f`；片段 900 Unicode 字符、重叠 150 |
| 技能身份 | `runtime_identity.skills` 绑定两份 SKILL.md 的内容哈希，正文变化后不得混用旧输出恢复 |

锁定证据：[候选选择](acceptance_evidence/candidate-identity.json)、[验证批次执行绑定](acceptance_evidence/validation-binding.json)。E5 构建配置和日志会继续变化；BM25 候选的运行身份只绑定实际使用的检索路线，不把未使用的向量检查点更新误判为主预测身份变更。

输入结构、唯一 ID 和哈希已重新核验，未分析测试题内容或检索测试答案。见 [input-audit.json](acceptance_evidence/input-hashes.json)。

| 文件 | 数量与字段 | SHA-256 |
|---|---|---|
| `data/test.jsonl` | 100 唯一 ID；仅 id/question | `2e9e3689de5901e0151995db91d0fa6525b2062cc116ddab88f59b9ccccd5d0b` |
| `data/validation.jsonl` | 100 唯一 ID；id/question/answer；仅评测器读取标签 | `5efedfaa2dd4cf58ee0c38be59d68be1fe7eb5a19beb9d3c45bfe91afda4a4da` |
| `data/validation-questions.jsonl` | 同 100 题，移除 answer 后送入 runner | `6317237123a44b18c0781e1e198b863deabd33efea0065a52af1d158ddd04e35` |
| `data/acceptance-diagnostic-questions.jsonl` | 固定 5 题，只有 id/question | `f1d2182def7286f0795a103e5404a4cc9d2257d7fb2e94eb82799ac009e2b2aa` |

验证与测试 ID 交集为零。固定诊断 ID 为 1005、121、253、445、720；它们属于验证集，已用于问题诊断与候选选择。因此完整验证结果必须同时说明这 5 题的使用，并另外汇总其余 95 题，不能把全部 100 题描述为完全未参与开发的留出集。

## 2. 课程要求与本次额外任务：43 项矩阵

已通读并逐页视觉核对课程指南 6 页（August 2026 v1.0）；公开[需求核验索引](acceptance_evidence/requirements-verification.json)记录43项分类；原始 PDF SHA-256 为 `1826731f2cba92f0c03a13888e2b2938174342bab468f68a1e3ac3eb6d54f13a`。课程基本要求、加分项、桌面任务额外要求及留给后续的最终材料分开列示。p6 是参考文献，没有增设独立评分项。下表的“通过”仅指注明规模内有证据；不代替教师评分。

### 2.1 课程程序要求（C01–C22）

| ID / 出处 | 要求及类别 | 本轮状态 | 实现/证据与剩余边界 |
|---|---|---|---|
| C01 / p1 | 固定 100,195 文档、ID/text/URL；基本 | 全量语料与 BM25 已核验 | `data/course-full/documents.sqlite`；索引状态与指纹见 §3。语料与BM25两库只读全库quick_check均返回ok；未将其写作更强的integrity_check。 |
| C02 / p1–2 | 验证与测试同一实现，不逐题编辑答案；基本 | 两套100题同实现，已核验 | `runtime.py`、`evaluation/batch.py`、`acceptance_batch.py`；100+100精确六字段/ID/题目/usage独立审计通过。 |
| C03 / p1–2 | 指定 DeepSeek-V4-Flash；基本 | 暂选官方兼容实测通过；原版身份待用户后续接口 | `config.py`、`llm/provider.py`；实际请求/响应名保留，formal 身份规则未放宽。 |
| C04 / p2 | 至少一类检索；一/二/三类为 4/6/8 分 | BM25 全量通过；E5 构建中；Qwen 用户暂缓 | 完整三类是本次额外目标，不是课程最低要求；有限神经检查点不得算全量。 |
| C05 / p2 | 恰好一个检索工具；基本 | 接口与真实调用通过 | 模型只通过 `search` 检索；支持工具另计，不暴露三个独立检索工具。 |
| C06 / p2 | query→按相关性排序的 ID/score/snippet；基本 | BM25 全量和小语料 E5 已测；其余待完成 | `retrieval/sparse.py` 等；排序、坐标与原文切片对照。全量三路比较未完成。 |
| C07 / p2 | 至少一种支持工具；基本 | open/find 真实调用通过 | 默认 search/open_document/find_in_document/load_skill 共 4 类工具，关闭技能时 3 类；见工具 schema 与 §4。 |
| C08 / p2 | 真实选工具、造参数、执行、观察、回答；必做 4% | 两引擎合成与固定验证诊断均实测 | `runtime.run_question` 和 production HTTP；旧 Agent1.2 上下文缺陷已修并真实重测。 |
| C09 / p2 | 后续查询依赖前轮结果；可选 Feature A 5% | 真实多跳通过，禁迭代消融完成 | 首跳发现大学名称，第二跳才使用该实体；§4/§5，不是预置全链查询。 |
| C10 / p3 | 独立结构化状态；可选 Feature B 5% | 实际状态轨迹通过 | 已读文档、证据、查询、候选和停滞记录，与原始历史分离。 |
| C11 / p3 | 上下文去重/选择/裁剪等；与 C10 同一加分项 | 长文本与超大并行结果修复通过 | 12,000 字符原返回保留；实际后续视图受限；原始轨迹不删，配对不破坏。 |
| C12 / p3 | 至少一个原创标准 SKILL.md；必做 6% | 两份项目技能的结构、元数据与运行流程验收通过 | `skills/multi-clue-decomposition`、`skills/search-recovery`；流程正文、项目设计与版本历史一并保留。 |
| C13 / p3 | 正文运行时加载，非永久基础 prompt；基本 | 实际请求证据通过 | 恢复题首次请求无正文，状态触发后完整正文进入后续请求。 |
| C14 / p3 | 至少两种不同技能，按问题/状态自动选，亦可不选；加分 4% | 两引擎三类情境真实覆盖通过 | 多线索、停滞恢复、简单无技能；属于确定规则自动路由，不虚称一定由模型自行选技能。 |
| C15 / p3 | CLI 或网页输入、答案、证据、技能、过程；基本 4% | CLI 与实际浏览器均已测 | 网页同配置、下载记录、空输入提示与密钥不显示已核对；见 §4。 |
| C16 / p4 | 测试恰好100条，六字段，完整trajectory | 测试100兼容记录全部通过 | 测试与验证独立输出；六字段、原题逐字一致、唯一ID与顺序已核验。原版身份另列。 |
| C17 / p4 | 完整时序与所有模型工具调用准确计数 | 功能/诊断及100+100审计通过 | 调用内部的检索融合不额外计工具次数；失败调用仍留记录。 |
| C18 / p4 | total_tokens 为所有实际 API usage 总和 | 功能/诊断及100+100审计通过 | 原始 HTTP usage 对账；错误响应有 usage 则计一次，未知用量不可估零。 |
| C19 / p4 | 100 条有效记录与答对率分开；禁止手写预测 | 两批完整覆盖，分层审计通过 | 两批各100条兼容/引用通过、20回答/80弃答；验证EM19%，测试无标签不评分。 |
| C20 / p4 | normalized EM 与全部 100 题效率 | 验证100及开发重叠5/其余95已算 | 归一化小写/标点/冠词/空格；F1仅补充。测试无标签，不造测试 EM 或课程排名。 |
| C21 / p5 | 完整源码、依赖、README、可复现 | 冻结源码独立重装与复现通过 | 无 Git ZIP 的实测缺陷已修；44个已安装Python文件与冻结源码逐一SHA相同，CLI导入/索引/查询/预测/续跑/复用通过。 |
| C22 / p5 | 无硬编码答案、无隐藏标签、无凭据提交 | 运行边界、回归及凭据扫描通过 | 答案只进评测器；版本/config/语料/实际索引/技能身份绑定；逐文件与Git历史凭据检查；密钥仅在本机。 |

### 2.2 本次任务额外要求（X01–X15）

| ID / 范围 | 额外要求 | 本轮状态 | 证据/剩余工作 |
|---|---|---|---|
| X01 / §1 | 更新代码、祖先核验、隔离分支、记录环境 | 分支与祖先通过；当前冻结身份已登记 | `dab7646`、候选选择和运行绑定；发布时补最终远端 SHA/核验记录。 |
| X02 / §1 | 固定验证/测试修订、哈希、100唯一ID、无交集 | 结构/哈希/ID核验通过 | `work/acceptance/input-audit.json`；测试内容未用于开发分析。 |
| X03 / §3 | 全量 BM25/E5/Qwen 同指纹并 ready | 部分满足 | BM25 ready；E5 BUILDING；Qwen USER_DEFERRED。不可称“三路全量完成”。 |
| X04 / §3 | 真模型代表短批、吞吐/内存/空间、据测调参 | 两路真实短批完成；E5持续 | E5 同 256 片段三组合测量，选 batch32/10线程；Qwen短批后按用户要求暂缓。 |
| X05 / §3 | 全量 sparse/encoder/instruction/hybrid 比较 | 部分满足 | 全量 BM25已测；97文档的小规模 BM25/E5 对照已测；完整神经与混合不就绪。 |
| X06 / §5 | 空/非法query、Unicode、损坏/版本不符、中断恢复 | 程序回归通过，真实检查点实测部分完成 | 不把 SyntheticEmbedder 回归或日志恢复当成真实大模型全量中断验证。 |
| X07 / §4 | 官方接口、余额、费用、主机限制 | 实际接口、余额与去重总账已汇总 | 只送官方主机；无充值；usage与费率估算/余额实查分开。 |
| X08 / §5 | 多轮、open/find、裁剪、技能、弃答、预算和协议 | 真实功能覆盖与相关回归完成 | 原 8 题7/8+独立补充1/1；保留未触发案例。限流/错误回归不得称真实限流已发生。 |
| X09 / §5 | CLI 和网页两个入口实际操作 | 合成及最终全量配置均完成 | 最终CLI/Web同题同配置，真实日期答案、来源片段及导出记录均通过；原文日期格式略有差别。 |
| X10 / §5 | 固定3–5题候选/机制消融与检索比较 | 候选/3机制消融完成；全量检索对照部分 | 六组5题结果见§5；Qwen/混合依用户暂缓，不伪补全量结论。 |
| X11 / §5 | 新身份完整验证100题与成本/错误统计 | **完整100已聚合、评分和独立审计** | 四分片同配置；5题开发重叠与其余95分开汇总；不并入旧90题。 |
| X12 / §5 | 锁定配置、同入口完整测试100题 | **完整测试100及零调用恢复通过** | 不停在诊断；先完成暂选API的100条兼容预测，原版身份另列。 |
| X13 / §5 | 最终回归、干净安装/独立目录复现 | 151主套件+新增1边界回归、70 Agent1.2通过；独立安装复现通过 | 非editable安装；44个源码SHA一致、pip check通过，3题离线CLI完整复用0调用。 |
| X14 / §6 | 完整回传、GitHub源码/配置/统计、远端查证 | 回传、统计、分支与Release移交 | §7列出入口；最终远端SHA、资产哈希及下载核验见Release的PUBLICATION.json。 |
| X15 / §6 | 一致SQLite、BM25、最高神经检查点、缓存/下载清单、<2GiB分卷/SHA/解包 | 一致快照、分卷、加密与独立恢复已通过 | E5快照313,344源片段；数据4卷、运行证据1卷，均小于2GiB，逐文件/数据库/1261分片/链接校验通过。 |

### 2.3 留到后续的课程材料（L01–L06）

| ID / 出处 | 要求 | 本轮边界 |
|---|---|---|
| L01 / p3 | Overleaf模板，正文至少4页，不计参考文献和最后贡献声明；20% | 待后续成稿；本工程回传不是最终课程报告。 |
| L02 / p3 | 方法、标注流程图、不同配置结果、UI设计/截图 | 本轮积累证据，后续整合写作；额外探索可选。 |
| L03 / p3 | 贡献比例合计100%，所有成员签名 | 待成员确认，不推测贡献或代签。 |
| L04 / p4 | 不超过5分钟MP4，演示真实系统及申报功能；20% | 网页/CLI已实测；视频后续制作。 |
| L05 / p5 | 组压缩包含预测、源码、报告、视频，测试后上传 | 当前开发/移交包不等于完整课程提交包。 |
| L06 / p1、p5 | 截止2026-11-26 23:59香港时间、Canvas组/一人提交、迟交规则 | 本轮不操作Canvas提交或组员资料；最终提交后续办理。 |

## 3. 语料与检索：已完成与未完成

[索引状态](acceptance_evidence/index-status.json)记录了持续构建和固定移交快照。以下是2026-11-15 14:48:03香港时间冻结、随后核验的移交快照，持续构建产生的新片段不自动计入这份已冻结快照：

| 路线 | 已覆盖源片段 / 4,345,592 | 向量行 / 分片 | 状态 |
|---|---:|---:|---|
| BM25 | 4,345,592 | 不适用 | READY |
| E5-small-v2 | 313,344（约7.21%） | 316,662 / 1,224 | 快照ready=false；持续构建已恢复，会话17739，batch32、10线程 |
| Qwen3-Embedding-0.6B | 9,472（约0.218%） | 9,722 / 37 | USER_DEFERRED；ready=false |
| hybrid | 依赖完整三路 | 不适用 | USER_DEFERRED / 未完成 |

E5固定 revision `ffb93f3bd4047442299a41ebb6fa998a38507c52`；Qwen固定 revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`。源片段与向量行并非恒等：长文本编码分段可能产生多个向量，不得用向量行冒充已覆盖源片段。

真实短批证据：E5 首批新增256源片段，包含加载和恢复的耗时13.158s、19.46片段/s、峰值RSS约535MB；Qwen新增256源片段耗时105.074s、2.44片段/s、峰值约2.29GB。Qwen的离线tokenizer加载路径已修复，此后用户要求暂缓后续计算。见 [E5短批](acceptance_evidence/index-benchmarks.json)、[Qwen短批](acceptance_evidence/index-benchmarks.json)。

E5另用同256源片段、同模型/精度/分段比较3组合：batch8/5线程39.65片段/s，batch32/5线程45.32，batch32/10线程54.81；向量差异均在1e-6内，选最后一组继续构建。测量仅为短批、RSS为进程累计峰值，不能把该速率直接承诺为全量完成时间。[批量/线程测量](acceptance_evidence/index-benchmarks.json)

另完成97篇真实文档、20条既有自编诊断的BM25/E5比较：总体证据Recall@5为1.00/0.95，热查询中位延迟约0.95ms/36.65ms。它不是100,195文档的全量路线评估，不是官方验证/测试集指标，也没有加载Qwen。[小规模检索对照](acceptance_evidence/index-benchmarks.json)

SQL改动保持原分数、rowid平局次序、片段ID、原文与坐标一致。单次长查询基准约24.49s，最终等价实现约24.54s；存在并发查询和缓存差异，**没有证据支持稳定提速声明**。[SQL基准](acceptance_evidence/index-benchmarks.json)、[最终等价检查](acceptance_evidence/index-benchmarks.json)

数据库副本采用空WAL和稳定源状态后的APFS clone，并核查元数据、数量及登记向量校验和；语料与BM25全库只读SQLite quick_check分别耗时265.98s和222.69s，均返回ok，文件大小/mtime不变、前后WAL均为0；没有把quick_check改称integrity_check。最初备份遇到阻塞的隔离临时文件未用于检索；其失败和清理限制保留在索引日志中，不将它冒充可用数据库。

## 4. 已完成的修复与真实功能验收

1. **官方兼容身份与记录审计。** 显式允许用户暂选官方别名；请求名、响应名、HTTP原始响应与usage都保留；formal课程身份验证仍独立。兼容恢复不重跑有效空答，失败尝试留档，未知用量不伪补零。
2. **归档环境复现。** 原三个实验脚本依赖 `.git`，在源码ZIP中真实失败；改为可空Git SHA加源码摘要，拒绝借用外围无关仓库的HEAD。源码包独立安装后的 prepare/index/search/ask/predict/resume/reuse/validate 已实测；再次运行跳过3条、无新调用。该次是较早检查点，最终冻结包还需重验。[独立环境汇总](acceptance_evidence/earlier-clean-install.json)
3. **Agent1.2超大并行结果导致空视野。** 原5题38次请求均无工具消息且证据快照为空。修复上下文分配顺序，先排除本来就装不下的完整工具组，再裁剪证据。2个通用大结果测试和5条实际轨迹的无API回放在修复前全部复现、修复后全部通过；97项相关回归通过。后续真实5题每个后续请求都有观察，最大23,853字符低于24,000。[阶段分析](acceptance_evidence/context-delivery.json)、[回放与新请求证据](acceptance_evidence/context-delivery.json)
4. **计费报告。** `audit_predictions.py --official-compat`分别报告兼容/正式有效性，audit_version2从原始HTTP响应计usage一次；无返回cost则为null。未知币种不改称USD，费率估算和余额变化不能冒充API返回实付费用。相关3项回归通过。
5. **运行身份。** 绑定源码、配置、固定输入、语料、实际检索路线及两份技能内容；变更后拒绝旧输出继续混跑。四分片聚合逐分片验收、按原始ID顺序原样汇总，并保留分片及失败尝试。

真实合成功能验收原8题7/8，补充独立恢复题1/1；原来的未触发案例未改写。总计9条、27个HTTP 200、19个工具调用，43,413 tokens（prompt41,908、completion1,505）。两引擎覆盖结果驱动多跳、两技能自动选择和无技能、open/find、诚实弃答；长返回12,000字符完整留在原轨迹，裁剪标记进入后续请求；最后一步收尾实际禁用工具。原Agent1.2恢复题因没有形成检索停滞而未加载恢复技能，补充题形成真实空结果后按状态自动加载，不能将原批次改报8/8。[原8题汇总](acceptance_evidence/feature-probes.json)、[独立补充题](acceptance_evidence/feature-probes.json)

先前合成网页提问、精确证据、无技能标记、search参数、结束状态、下载及空输入警告已实测，3,013 tokens、1次search。冻结后重启网页服务，再以最终配置和CLI完成同题真实语料验收：CLI 7,308 tokens、网页7,303 tokens，各1次工具调用，兼容/引用均通过；两答案表示同一日历日期，但原始字符串不同，未声称逐字相同。界面与下载均实际观察，密钥未显示。[网页验收](acceptance_evidence/final-cli-web.json)

冻结前主pytest完整套件151项通过，随后新增的聚合末轮边界回归1项通过，Agent1.2 unittest 70项通过。它们与较早干净环境134+70计数分开，不相加为一个测试总数。[最终主回归日志](acceptance_evidence/frozen-regression.json)、[Agent1.2日志](acceptance_evidence/frozen-regression.json)

## 5. 固定5题候选、消融与失败保留

| 配置 | 兼容合格 | 引用通过 | 非空回答 | EM / 补充F1 | tokens | 工具次数 |
|---|---:|---:|---:|---:|---:|---:|
| baseline 全机制 | 5/5 | 5/5 | 1 | 20% / 20% | 87,690 | 38 |
| Agent1.2 修复前 | 5/5 | 5/5 | 0 | 0% / 0% | 90,538 | 66 |
| Agent1.2 上下文修复后 | 4/5 | 4/5 | 2 | 40% / 40% | 127,356 | 29 |
| baseline 禁技能 | 5/5 | 5/5 | 2 | 20% / 36% | 70,452 | 34 |
| baseline 禁上下文管理 | 1/5 | 4/5 | 1 | 20% / 20% | 168,238 | 19 |
| baseline 禁迭代 | 5/5 | 5/5 | 1 | 20% / 20% | 25,077 | 10 |

评分只在模型运行后读取验证标签。禁技能两条非空回答只有一条完全匹配，不能把completed数当正确率。三机制配置各只改变一个布尔开关；代码版本变化以及只有5题限制了总体和因果结论。完整逐题指标见 [最终独立评分](acceptance_evidence/diagnostic-comparison.json)。

按阶段定位：宽泛多词BM25查询和同文档多片段占据前列影响检索多样性；baseline仍有非空证据快照，未完成题缺少充分实体驱动核查；原Agent1.2则存在已修复的“检索返回了证据但程序未展示”缺陷，不能全部归因于模型查不到证据。

修复后Agent1.2题253两次返回只有candidate/conditions/next_check的进度JSON，无answer亦无工具调用；一次真实修复后仍不合契约，保留invalid_response，不把candidate改写成答案。禁上下文组4题超过30,000配置预算；题253最后真实非空答案在预算停止前未进入导出，因而兼容审计正确拒绝。未重跑消融直至成功或手改预测。

最终选择baseline全机制，依据是5/5完整记录和已验收的技能、多轮、上下文功能覆盖；不是准确率领先宣称。Agent1.2修复后小样本EM更高但仍有协议失败；禁迭代更便宜且本5题EM持平，但关闭了多轮机制。候选选择详见 §1 证据。

## 6. 验证100、测试100：已完成

两批均使用配置`61d7cc3701b2a42a`和运行源码`bdf0d958...`，四个25题分片并行、最后按原输入顺序原样聚合。验证标签仅由运行后的评分器读取；测试没有答案字段，未用于调参或计算EM。没有并入旧90题、重写弃答或手工扩写答案。

| 指标 | 验证100 | 测试100 |
|---|---:|---:|
| 精确六字段、唯一ID、逐字问题与原顺序 | 100/100 | 100/100 |
| 官方兼容记录 / 引用检查 | 100/100、100/100 | 100/100、100/100 |
| 非空回答 / 证据不足弃答 | 20 / 80 | 20 / 80 |
| normalized EM / 补充token F1 | 19% / 19.8% | 无标签，不计算 |
| HTTP真实请求 / 模型工具调用 | 442 / 666 | 456 / 689 |
| prompt / completion tokens | 1,479,026 / 57,294 | 1,518,238 / 57,905 |
| cache hit / miss tokens | 548,096 / 930,930 | 523,904 / 994,334 |
| 总tokens | 1,536,320 | 1,576,143 |
| 单题中位 / P90 / P95秒 | 12.404 / 21.582 / 23.934 | 13.540 / 26.887 / 31.401 |
| 单题最小 / 平均 / 最大秒 | 4.711 / 13.585 / 35.077 | 5.447 / 15.380 / 39.922 |
| 公开费率估算CNY | 1.17106792 | 1.23643208 |

逐题延迟是各题单调时钟耗时，四分片并行时不能用其相加值当整批墙钟耗时。每个HTTP的原始usage计一次，assistant镜像不重复计费；没有未知usage、归档重试或token对账差异。两批API均未返回usage.cost，实际返回费用为null，费率估算不是实付账单。[验证统计](acceptance_evidence/validation100-statistics.json)、[验证独立终验](acceptance_evidence/validation100-completion-audit.json)、[测试独立终验](acceptance_evidence/test100-completion-audit.json)

5个已用于开发诊断的问题在本次完整验证中答复2题、正确1题，EM20%、F1 36%，54,641 tokens、24工具、17HTTP，中位10.148s；其余95题答复且答对18题，EM/F1均18.947%，1,481,679 tokens、642工具、425HTTP，中位12.428s、P95 25.049s。这是报告重叠边界，并非把95题包装为从未受任何开发决策影响的独立研究基准。

分阶段分析发现：80个弃答中，64题未在原始返回中发现参考答案字面串、8题只在原始返回中出现而未进入后续可见证据、8题实际请求已含字面串但仍缺充分条件支持。94题有精确重复查询，共211次；只11题使用open/find。342次观察后的请求都有非空证据，未再现先前Agent1.2的全证据丢失。另1题输出短名而参考为更完整姓名，严格EM计0。上述字面匹配是定位线索，不等同语义证据充足度或全语料召回率。[阶段分析及边界](acceptance_evidence/validation-stage-analysis.md)

正式课程身份审计与兼容审计分开：两批各有200条formal错误，全部来自“official_compat不验证课程原版身份”和“缺少原版模型身份核验”这两类、各100次；无其他formal错误。用户已经授权暂选官方API，因此记录保留为有效兼容输出，原版身份等待用户后续接口复核，不归类为HTTP失败或重跑空答。

两套独立恢复dry-run均为valid_existing100、pending0、new_api_calls0；实际CLI `predict --rerun-failed --limit 1`均attempted0、skipped100。恢复前后文件SHA完全一致：

| 聚合文件 | SHA-256 |
|---|---|
| validation_prediction.jsonl | `17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8` |
| test_prediction.jsonl | `5f8d11089c343a5543a21810b6ea97ba083f8e712a9fdad34ae174141fd68509` |

实际命令在仓库根目录使用同一已配置Python及dotenv；恢复检查先dry-run，再执行CLI，未读取或输出密钥：

```sh
PYTHONPATH=src:agent12 python scripts/recover_predictions.py \
  --config configs/acceptance-final.yaml --input data/test.jsonl \
  --predictions outputs/acceptance-test100-v1/test_prediction.jsonl --dry-run
PYTHONPATH=src:agent12 python -m rag_agent.cli predict \
  --config configs/acceptance-final.yaml --input data/test.jsonl \
  --output outputs/acceptance-test100-v1/test_prediction.jsonl --rerun-failed --limit 1
```

费率核对日期2026-11-15为周日，Flash空闲费率每百万tokens为缓存命中0.02元、未命中1元、输出4元；两批估计合计2.4075元。[DeepSeek官方费率](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

[本轮去重API总账](acceptance_evidence/api-usage-ledger.json)覆盖242条真实记录：200条完整批次、30条诊断、9条功能及3条网页/CLI，共1,065次HTTP、3,742,851 tokens、1,573工具调用，所有原始usage对账，按同费率估计2.94531836元。任务初余额9.99元，2026-11-15 14:55:56香港时间余额7.20元；余额可能延迟、也可能受同账户其他活动影响，因此不把余额差额称为本任务精确费用。初次余额检查前的10-token连接检查和8,762-token smoke单列在账本范围之外；没有充值。

## 7. 分支、发布与可恢复移交

- [工作分支](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/tree/codex/course-final-acceptance)：修复代码、配置、回归、43项矩阵、脱敏统计与恢复脚本。
- [Release移交入口](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)：源码ZIP、加密数据和完整运行证据。该版本标记为预发布，不能替代尚未完成的原版模型和全量向量验收。
- Release中的`PUBLICATION.json`记录实际交付提交、远端分支/标签核验、逐资产大小与SHA、下载校验结果；避免把本文的运行源码提交误当作最后文档提交。

| 产物 | 实际内容与验收 |
|---|---|
| `program-source.zip` | 对应交付提交的源码、README、依赖、配置、回归与报告；应用运行源码与100+100批次冻结身份一致。 |
| `data.*.aead`及`data.ENCRYPTED_VOLUMES.json` | 4卷，共6,048,600,182密文字节；最大卷1,900,009,655字节，小于2GiB。包括两份完整SQLite、E5的1,224分片、Qwen的37分片、manifest、相对链接与许可证据。 |
| `run-evidence.*.aead`及`run-evidence.ENCRYPTED_VOLUMES.json` | 1卷44,622,175字节，347个文件；含100+100原始轨迹、分片、运行身份、全部诊断/消融失败和恢复/安装证据。4份内部日志脱敏了本机工作区路径；所有预测JSONL原字节未改。 |
| `data-verification.json`及公开统计 | 数据独立解密后逐文件SHA检查、两库quick_check及计数、1,261个分片的shape/dtype/有限值/行数、相对链接全部通过。运行证据独立恢复后又用已安装包验收200条记录。 |
| `docs/handoff/MODEL_DOWNLOADS.json` | E5/Qwen/可选重排模型的固定revision与文件清单；默认只下载E5，不触发Qwen计算。 |

数据明文压缩档SHA-256为`dd2d6c63721911ea2b5da21cbd179de3eb3dfd313fa234b092ac71f7a6cf005a`；运行证据压缩档为`b4422eccdad96f511cb4f3503be88a4c4153c3cab0b22d0968874348e7a04870`。分卷及逐文件哈希以公开manifest和解密后的`HANDOFF.json`为准。

[软件独立安装检查](handoff/software_checks.json)、[移交和恢复步骤](handoff/README.md)、[运行证据独立恢复](acceptance_evidence/run-evidence-restoration.json)。密钥`data.key`与`run-evidence.key`仅保存在用户本机`private/`目录，权限600，由用户私下交组员；Git、Release与本文均不含密钥。没有向组员发送消息或进行Canvas提交。

E5快照冻结于2026-11-15 14:48:03香港时间，313,344源分块；随后原构建已恢复，snapshot与继续写入的目录独立。当前机器实测持续约62.17源分块/秒，剩余全量规模约403万；按这段速率约18小时，仅作资源估计。需要暂停时在仓库根目录创建`work/acceptance/indexes/stop-e5`，程序会在保存分片后停止；再次启动前移除该文件，并按移交README的同配置续跑命令继续。只有`ready=true`且源分块数等于4,345,592时，才能开始E5全量检索验收。Qwen依用户要求保持暂缓。

最终课程报告、贡献声明签名、5分钟视频和Canvas提交属于后续阶段，本工程移交包不等于最终课程提交包。
