# 全项目程序验收与缺口补齐回传

## 1. 本轮结论

**没有满足全部本轮需求。** 程序、两种 Agent 的正式记录链路、真实工具/多跳/上下文/自动 skills、CLI/网页/恢复及独立评测已修复并实测；固定语料 **100,195 篇、4,345,592 片段**已完整导入，全量 BM25 已完成。两路全量向量索引仅达到可恢复检查点，**未完成全量 E5/Qwen 索引与全量三路融合验收**，不能把 97 篇的三路实测当作完成。

官方验证集因服务 **HTTP 402额度不足**停止于 **90/100**：86条通过单条校验、4条服务失败、10条未运行。暂按缺失/失败计错的 **Normalized EM（归一化后完全匹配率）为** **19/100（19.00%）**；课程单条真实记录校验通过 **86/100**，引用校验 **86/100**，正式批量校验 **False**；这不是完整100题的最终成绩。实际配置为全量 **BM25 + 基线 Agent**，不是全量 hybrid。完整数字及所有失败保留在[脱敏汇总](course-program-validation-summary.json)。

待满足/部分满足/未验证：①两路全量向量构建；②全量三路查询延迟、磁盘和端到端效果；③原服务可用额度恢复后补跑10条缺失和4条HTTP 402失败；④完整100题覆盖、正式校验及最终EM尚未达到标准（见第6节）。官方测试文件、最终课程冻结、Overleaf课程报告、视频、贡献签名及最终课程压缩包均是后续阶段；本轮工程回传与功能分支推送已授权并执行。

## 2. 来源、执行路径和实际变更

- 原始指南：`COMP5423_26Fall_Project.pdf`，August 2026 v1.0，完整6页；SHA256 `1826731f2cba92f0c03a13888e2b2938174342bab468f68a1e3ac3eb6d54f13a`。正文核对 p1资源、p2检索/工具/Agent、p3状态/skills/UI、p4预测/指标、p5可复现/诚信、p6来源。p4另渲染检查六字段与计数定义。已明确区分课程最低要求与本轮选择的三类完整目标。
- 从目标 GitHub 仓库 `fetch origin` 后，确认最新 `origin/main` 为 `1162703f5ca920ca8a16947ea7a10cbb7cd85bbd`，包含重排评估和合入的Agent1.2。原检出保持原样；本轮在独立干净副本的 `codex/course-program-validation` 开始执行。
- 实测程序提交：`7855fe8c341917b657c4e3d3286d061830694db6`。最终报告提交及全部历史从分支HEAD查询：`git log --oneline origin/main..HEAD`；最终交付SHA以该分支远端HEAD及返回消息为准。
- 实际顺序：完整指南/源码审计→新隔离环境安装和起始两套测试→固定语料后台导入→证据ID/输出/HTTP/validator/身份/恢复修复→真实小样本与5题配对→实际网页/多跳/skills/长证据→代表性索引吞吐→全量导入恢复和索引→官方验证分批实跑（90/100后额度阻塞）→复核、返回文档和推送。
- 原计划全量三路；实际发现全量含434万片段，MPS Qwen实测约9.31片段/秒，按代表样本线性估计约129.7小时（约5.4天），E5约8.5小时；并非假定有更快的另一台执行机。已尝试MPS、batch16、缓存复用、分片与恢复；本轮保留全量BM25和两路全量身份的真实检查点，使用完整可用语料的BM25执行验证。
- 真实失败复现：原始模型会在最终JSON前附说明，Agent1.2先前两次修复均失败；现只提取唯一、完整、模型自己写出的对象，保留原始响应；歧义/破损JSON仍拒绝。网页又发现同一证据被search/open重复观察、可选chunk元数据缺失导致误报冲突，已修复并回归。Agent1.2真实未主动load技能，补入按题目/停滞状态可检查的自动路由。
- 全量BM25将逐条Python转换改为SQLite原生分批复制和原子FTS重建；实际复制全部片段并核对覆盖，FTS失败时ready保持false。没有改变BM25分词/得分定义或同一search工具契约。

## 3. 完整需求矩阵

以下“通过”只对应给出的范围与可观察事实，不承诺教师评分。每行代码/测试与第4–7节实测数字一起构成证据；合成mock只用于协议和负向校验。

| 要求ID与出处 | 当前实现/检查入口 | 起点缺口 | 本轮方案及验收 | 实际结果与判定 |
|---|---|---|---|---|
| D1，p1；固定 100,195 文档 | [prepare.py](../src/rag_agent/data/prepare.py)、[store.py](../src/rag_agent/data/store.py) | 历史只有 97 篇诊断语料；全量导入期间实际中断 | 按相同 revision 恢复；核对读取、去重、指纹、完整原文和分块 | 全量 100,195 唯一文档、4,345,592 片段；已实现且实测通过 |
| D2，p1/2；同程序验证/测试、无标签输入 | [io.py](../src/rag_agent/evaluation/io.py)、[batch.py](../src/rag_agent/evaluation/batch.py) | 参考答案不得进入 Agent | 只投影 Question(id,question)；合成无标签输入及恢复；官方文件同入口 | 已实现且实测通过；官方测试文件本轮未取得 |
| R1，p2 §1.1；三类检索，本项目完整目标 | [retrieval/](../src/rag_agent/retrieval/) | 历史 97 篇三路完整，不能作为全量 | 真实模型查询、代表性吞吐、全量 sparse、两路全量身份检查点 | 三类小样本真实通过；全量神经索引未满足，硬件吞吐限制 |
| R2，p2；恰好一个 search | [registry.py](../src/rag_agent/tools/registry.py)、[ports.py](../agent12/search_agent/ports.py) | 内部三路不得重复计工具 | 标准 CLI 单路/融合，schema 与真实轨迹对账 | 已实现且实测通过；三路内部操作只计一次模型 search |
| R3，本轮；片段 top_k、稳定 ID、Unicode 坐标 | [test_retrieval.py](../tests/test_retrieval.py)、[evidence.py](../src/rag_agent/evidence.py) | 同文档多片段、压缩后完整范围存在混淆 | 同文档不同坐标、原文切片、片段排序与引用范围回归 | 已实现且实测通过；完整神经规模查询尚未达到验证标准 |
| R4，本轮；索引中断恢复与身份 | [dense.py](../src/rag_agent/retrieval/dense.py)、[sparse.py](../src/rag_agent/retrieval/sparse.py) | 全量构建不可用小样本冒充 | 新增按新分片数检查点；ready=false 禁止查询；实际恢复复用旧分片 | 已实现且检查点实测通过；全量两路向量完成仍未满足 |
| T1，p2 §1.1；支持工具/schema/错误 | [registry.py](../src/rag_agent/tools/registry.py)、[peer.py](../agent12/search_agent/peer.py) | 必须可被真实模型调用，错误可定位 | 真实 open_document、find_in_document、正常/空/非法/边界离线回归 | 已实现且实测通过；真实长文案例执行 open 与 find |
| A1，p1/2 §1.2；指定 API backbone | [provider.py](../src/rag_agent/llm/provider.py)、[config.py](../src/rag_agent/config.py) | 服务目录与真实调用分开 | 先查目录/额度，少量测费；每次响应 model 与配置逐一核对 | 已实现且真实通过；只使用指定固定 DeepSeek V4 Flash ID |
| A2，p2；基本工具 Agent | [loop.py](../src/rag_agent/agent/loop.py)、[agent12.py](../src/rag_agent/agent/agent12.py) | Agent12 原来固定 eligible=false | 同一生产 HTTP 边界，保留真实服务调用 ID；实际短答案与引用 | 两种 Agent 已实现且实测通过 |
| A3，p2；结果驱动多轮 | [agent.py](../agent12/search_agent/agent.py)、[test_agent.py](../tests/test_agent.py) | 不能以固定检索后生成代替迭代 | 真实第一跳找到学校，第二跳按该学校改写查询；单次检索消融 | 已实现且实测通过；真实合成两跳两种 Agent 均得 Northport |
| A4，p3；独立状态 | [schemas.py](../src/rag_agent/schemas.py)、[context.py](../src/rag_agent/agent/context.py) | 访问文档、查询进度和选证据需与历史独立 | 保存 state、实际请求、原始事件；检查已选证据 ID 与查询进度 | 已实现且实测通过 |
| A5，p3；上下文控制 | [context.py](../src/rag_agent/agent/context.py)、[agent.py](../agent12/search_agent/agent.py) | 压缩不能把未见尾部当引用 | 真实 12,000 字符读取触发压缩，find 找尾部，原始长文保留 | 真实 8000 字符预算，最大请求 7426；答案 1977，引用通过 |
| A6，本轮；证据 ID 和输出修复 | [evidence.py](../src/rag_agent/evidence.py)、[final_output.py](../agent12/search_agent/final_output.py) | 真实模型输出说明文字+JSON；旧基线需复写坐标 | 只提取唯一完整原始对象；实际工具/模型视图确定性恢复；最多一次修复 | 已实现且复现原失败后实测通过；原始响应保持原样 |
| A7，本轮；负向引用与用量回归 | [test_course_acceptance.py](../tests/test_course_acceptance.py) | 不能仅把 eligible 改真 | 坏/重复 ID、错位、缺返回、缺 usage、假 HTTP、篡改原响应均拒绝 | 已实现且回归通过；合成协议夹具单列，不作真实 API 证据 |
| S1，p3 §1.3；原创技能结构 | [skills/](../skills/)、[runtime.py](../src/rag_agent/skills/runtime.py) | 两个不同功能、合法 YAML 元信息 | 多线索拆解和搜索恢复；先发现元数据，再选择/加载正文 | 已实现且实测通过；均为本项目原创技能 |
| S2，p3；自动选择 | [agent.py](../agent12/search_agent/agent.py)、[runtime.py](../src/rag_agent/skills/runtime.py) | 真实 Agent12 未主动选择技能 | 候选补入可验证的规则自动路由；保留模型 load_skill 工具 | 真实多跳选 decomposition，停滞选 recovery，简单题无需技能；内部路由不计工具 |
| U1，p3 §1.4；CLI/Streamlit | [runtime.py](../src/rag_agent/runtime.py)、[web_app.py](../src/rag_agent/web_app.py) | 候选、引用、失败状态要可见 | AppTest 两引擎及失败路径；浏览器实际默认/候选/真实提交并下载轨迹 | 已实现且实测通过；真实网页答 1984，2 工具、4564 tokens、引用通过 |
| P1，p4；六字段/类型/完整覆盖 | [schemas.py](../src/rag_agent/schemas.py)、[validate.py](../src/rag_agent/evaluation/validate.py) | 覆盖与单条记录资格须分别检查 | 严格六字段、ID 唯一、输入文本一致；正式100覆盖门槛保留 | 已实现且程序验证通过；官方实跑结果见下文，不伪造100成功 |
| P2，p4；完整真实时间序列 | [agent12.py](../src/rag_agent/agent/agent12.py)、[provider.py](../src/rag_agent/llm/provider.py) | 旧适配修改调用 ID，HTTP 事件只在包装层 | 原始请求/响应与 provider call ID；完整原始 Agent12 事件保留 | 已实现且真实正向、负向审计通过 |
| P3，p4；真实工具和 API usage | [validate.py](../src/rag_agent/evaluation/validate.py) | 重试返回 usage 也应计入，未知用量不能估算 | assistant/API error usage 求和；逐一核对 raw response、模型、用量、配对 | 已实现且实测通过；离线HTTP错误/重试用例与真实正常记录分开 |
| P4，p4；有效性/引用/答案分层 | [validate.py](../src/rag_agent/evaluation/validate.py)、[metrics.py](../src/rag_agent/evaluation/metrics.py) | 旧 formal 把项目引用质量等同课程有效性 | --formal 检查真实记录，--strict-grounding 另查引用，evaluator 单独比较答案 | 已实现且回归通过；答错/诚实弃答不因内部 eligible 被机械判无效 |
| B1，本轮；续跑身份与分批 | [identity.py](../src/rag_agent/identity.py)、[batch.py](../src/rag_agent/evaluation/batch.py) | 同一路径换语料/索引/代码会误续跑 | 清单绑定输入/配置/代码/实际语料与索引；--limit 分批；变更拒绝 | 已实现且实测通过；旧 schema=1 清单需用新输出 |
| B2，本轮；中断/失败重跑 | [test_course_acceptance.py](../tests/test_course_acceptance.py)、[test_evaluation.py](../tests/test_evaluation.py)、[恢复脚本](../scripts/recover_predictions.py)、[恢复回归](../tests/test_recovery_script.py) | 成功记录不得丢失或重复成本 | 真实子进程 SIGTERM 后跳过已落盘题；旧失败另存并汇总全部尝试 | 已实现且回归通过；定向恢复dry-run为86有效、14待处理、0 API；模拟中断日志恢复不重复调用 |
| E1，p4；Normalized EM 与本组效率 | [metrics.py](../src/rag_agent/evaluation/metrics.py)、[audit_predictions.py](../scripts/audit_predictions.py) | 分母包括失败，不能只筛成功题 | 按现有小写/英文标点/冠词/空白规则，100题总调用/tokens，失败列明 | 已实现且实测通过；没有其他组数据，不计算成绩/排名 |
| E2，本轮；官方100验证 | [fetch_validation.py](../scripts/fetch_validation.py)、[cli.py](../src/rag_agent/cli.py) | 100唯一题，固定 revision，真实运行 | 只用固定全语料，5题分批；标签只供独立 evaluator | 未满足：90/100记录，86条单条合格，4条HTTP 402失败、10条缺失；额度阻塞；详见第6节 |
| E3，本轮；同题对照和机制消融 | [audit_predictions.py](../scripts/audit_predictions.py)、[配置](../configs/) | 旧小样本排名不应盲迁到全量 | 5题基线/1.2同题；单路/融合10题；迭代/skills/context单因素5题 | 已实测；小样本结论与全量分开，未声称统计显著性或最优 |
| C1，p5；干净安装与复现 | [pyproject.toml](../pyproject.toml)、[README](../README.md) | 源码、安装包与入口须一致 | 新 .venv 安装所有依赖；源码草稿解压后另隔离安装并运行 CLI | 已实现且实测通过；主套90、Agent12套70、Ruff/pip check通过 |
| O1，p3-5；报告/视频/签名/课程包/正式测试 | [requirements.md](requirements.md) | 本轮文档明确排除最终课程交付 | 工程回传/程序说明本轮完成，后续取得测试文件再跑、冻结与交付 | 本轮排除；未代交 Canvas、未制作虚假签名/成绩/测试预测 |

## 4. 执行机、语料、索引与恢复

执行位置：`/Users/kiki/Documents/ChatGPT/关于大数据计算的项目写作/NLP-Agentic-RAG-for-given-documents`。macOS arm64，Python 3.12.14，统一内存24GiB；沙箱内MPS探测受限，真实执行命令在已授权外部环境确认MPS可用。CPU/CUDA没有互相冒充。基础/检索/开发依赖在新建 `.venv` 实际安装；版本快照见 [requirements-lock-py312-macos.txt](../requirements-lock-py312-macos.txt)。起始主测试66通过、2个网页测试受继承API环境影响失败；已隔离测试环境。正确的Agent1.2测试需在`agent12/`目录运行，最终70项通过。

固定语料：`https://huggingface.co/datasets/Tevatron/browsecomp-plus-corpus`，train，revision `b27b02bc3e45511b8b82a13e6f90ce761df726f6`，字段docid/text/url。唯一文档数100,195；Unicode字符分块900、重叠150；共4,345,592。指纹 `ea8764233b0d4a76d050842e290805a0f154858084dfd0430ba8c0d9c555025f`。`document.text[start:end] == snippet`为原文坐标条件，start/end不是字节或token位置。

首次导入在约46,800篇时被本轮执行中断；使用相同来源/范围恢复，已存在文档仅校验并跳过，完成后统一重算指纹。最终不是“把部分语料改名当全量”。完整SQLite、原文、索引与缓存均在忽略目录。

| 向量路由 | 模型 | 维度 | 已构建源片段/全量 | 实际向量数 | ready |
|---|---|---|---|---|---|
| encoder | intfloat/e5-small-v2 | 384 | 33,536 / 4,345,592 (0.77172%) | 34,424 | False |
| instruction | Qwen/Qwen3-Embedding-0.6B | 1024 | 9,216 / 4,345,592 (0.21208%) | 9,466 | False |

E5 revision `ffb93f3bd4047442299a41ebb6fa998a38507c52`；Qwen revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，tokenizer与权重同版本，dense格式1。每路先在`indexes/course-full/`完成2个新分片，再独立调用复用已有分片并增加1片（768源片段）；为了不改变正在运行的BM25恢复身份，随后复制到独立`indexes/course-full-vectors/`继续推进，E5再建128片、Qwen再建32片，随后用提交的续跑脚本再实际构建1片验证（8960→9216）。E5在并行MPS构建时发生内存不足，已保留4608源片段并以CPU/batch8/两线程恢复；没有关闭MPS内存保护。Qwen强制离线模式因当前tokenizer依赖查询Hugging Face元数据而退出，移除限制后继续；长进程也发生MPS内存不足，进一步改用每片独立真实进程，正常退出释放设备缓存，未更换模型权重版本或关闭内存保护。可复用的提交入口为`scripts/index_in_shards.py`，已核验真实检查点状态、错误配置拒绝，并实际执行父子进程续跑生成新真实分片（退出0、ready=false）。上表记录最后已完成并校验的最高覆盖；检查点文件校验与范围兼容通过。部分索引不可被SearchService当作完整索引加载。

代表性真实样本含5篇文档（短文、中等、长文及923,114字符高分块文档）；两路各测64个覆盖首/中/尾的源片段。MPS、batch16：E5加载2.990s，纯编码0.450s，142.23片段/s；Qwen加载1.977s，编码6.875s，9.31片段/s，进程RSS高水位约3.83GiB。加载使用已验证的本地模型缓存，无需重新下载权重。初始纯编码外推不是完整构建耗时承诺。后续安全续跑实测E5 CPU为34.38源片段/秒，Qwen逐片进程为6.58源片段/秒（含加载/校验/退出开销）；按这些实测估算剩余约34.8小时和183.1小时，仍受输入分布、机器负载及逐片恢复时不断增长的历史分片校验开销影响，不是完成承诺；有足够GPU资源时宜用标准连续构建。

全量BM25构建实测 137.538s，索引文件 6.212GiB；全量神经索引的最终磁盘/查询延迟尚未实测，不能拿97篇的延迟外推。阶段耗时、ready、模型维度与覆盖另见脱敏JSON；完整可恢复manifest在`indexes/course-full-vectors/`（完整BM25仍在`indexes/course-full/`）。

## 5. 真实模型、诊断对照与机制证据

指定服务：`https://openrouter.ai/api/v1`，模型 `deepseek/deepseek-v4-flash-0731`。本轮重新读取[模型目录](https://openrouter.ai/api/v1/models)及[原模型页面](https://openrouter.ai/deepseek/deepseek-v4-flash-0731)，核对同一原版GA模型与tools/tool_choice；每次真实响应model仍逐一核对。先查可用限额、真实少量请求和usage.cost，再启动后续。不能把目录支持当作请求已经发生，也不能独立鉴定服务端模型权重。

基础修复后的5题配对（当时未启用最终回复预留，代码c039cbc）固定相同97篇诊断语料、三路RRF、候选50、top_k5、关闭重排、相同模型、max_steps10、每题30000 tokens、context24000。参考答案由evaluator在预测后读入；这5题不是官方验证题。两端实际有效配对5，失败总数0。

| Agent | Normalized EM | 单条真实记录通过 | 引用通过 | 工具调用 | API tokens | 服务报告费用 |
|---|---|---|---|---|---|---|
| baseline | 5/5 | 5/5 | 5/5 | 11 | 31,170 | $0.00239320 |
| agent12 | 5/5 | 5/5 | 5/5 | 19 | 49,049 | $0.00257867 |

另离线回放原2026-11-11的10条真实尝试：9个token_budget、1个completed，共317,360历史tokens、43次工具。34条模型最终输出候选中，旧严格JSON可解析15条，新唯一对象解析可识别34条，语法层恢复19条；但当前正式校验仍只有原1条通过，没有改写旧失败的预测或引用，也没有新增API请求。源轨迹仍在原检出忽略目录，本轮只输出脱敏回放统计。

第一轮也是两端5/5，Agent1.2较省；自动skills补齐后的最终复测基线更省，因此推荐暂用**基线**，Agent1.2保留可切换路径。没有把单次小样本随机波动解释成稳定优势，也没有按最高小样本结果宣称最优。

同一真实诊断保留集10题的检索对照（部分证据标注；单个片段完整覆盖标注才算命中，未标注不作负例；预热后延迟）：

| 方法 | 证据Hit@5 | 首证据MRR | 查询中位秒 |
|---|---|---|---|
| sparse | 10/10 | 0.7917 | 0.000878 |
| encoder | 9/10 | 0.7333 | 0.013523 |
| instruction | 10/10 | 0.7500 | 0.111136 |
| hybrid | 10/10 | 0.8083 | 0.097398 |

关键机制单因素消融，固定上述5题，分母保留失败：

| 配置 | EM | 单条真实记录通过 | 工具调用 | API tokens | 结束状态 |
|---|---|---|---|---|---|
| single-search | 1/5 | 1/5 | 9 | 12,719 | {"single_step_limit": 4, "completed": 1} |
| no-skills | 5/5 | 5/5 | 11 | 35,927 | {"completed": 5} |
| no-context | 5/5 | 5/5 | 6 | 34,756 | {"completed": 5} |

单次检索配置的4个失败来自模型仍请求下一次检索而被配置阻断，已保留真实发出调用及失败结果，不补写答案。无skills/无context在这5题均答对，说明小集合不能证明它们的准确率收益；保留它们是课程实现目标，另有功能触发证据。

真实合成机制演示（非benchmark成绩）：两种Agent均先查Lumen Observatory architect，读到Cedar University后再查其位置，答案Northport；多跳自动选multi-clue-decomposition；不存在实体导致停滞时自动选search-recovery，诚实弃答；简单馆舍年份题不加载skill。自动路由不冒充模型工具调用，正文确实进入后续实际请求。

真实长证据：Agent1.2先open 12000字符，再find定位尾部，答1977；8,000字符上下文预算下最大实际请求7,426字符，出现可见范围截短标记，原始长返回保留；引用、工具配对和API usage通过。网页通过浏览器实际提交真实模型问题，答1984、2工具、4564 tokens，显示E1原文0–63及引用来源，下载记录再次通过校验。

全量BM25另以相同10道诊断保留题实测：证据Hit@5 **9/10**、MRR **0.6783**，预热后查询中位 **3.2368秒**（官方小批量可能并发，非独占基准）；原文坐标与重复排序全部核对。97篇时的延迟和命中不能外推全量。另测试SQLite原生rank排序候选，在3个固定查询上ID/分数相同，但约3.39–3.59秒，慢于原SQL的2.74–2.92秒，因此未采用。

## 6. 官方100题验证与实际失败

数据：`HongruCai/COMP5423-BrowseComp-Plus-Val`，revision `277d3b49913c176976e8b40b7df55b00212cf158`；100唯一ID。输入保留课程原始文件，答题边界只投影id/question，答案仅evaluator读入。官方测试文件本轮未取得。

全量预检先在原程序的前5题发现2个token_budget、2个repeated_action、1个completed；第2轮前15题仍有2个并行重复动作退出。原始5/15题均原样保留在`outputs/official-validation/`与`outputs/official-validation-r2/`，程序身份变化会阻止混跑，后续使用新目录重新运行。最终修复在固定预算内预留真实最终API回复，并在并行调用触及重复限制后保留全部配对、切换到关闭工具的最后一轮。没有把旧失败的状态或答案改写为成功。

实测代码 `7855fe8c341917b657c4e3d3286d061830694db6`；配置[course-full-sparse.yaml](../configs/course-full-sparse.yaml)。固定全部100,195篇语料，检索为BM25，5题分批并用同一清单续跑。候选启用`graceful_finalization: true`，在预算/停滞/最后一轮及并行重复动作后请求模型真实收尾或弃答；每题max_steps12、工具上限24、API tokens上限30000、context24000、单请求60s、单题300s，重排关闭；程序上限不是服务账单估算，所有实际API usage都完整计入。

- 记录覆盖：90/100，状态：`{"insufficient_evidence": 60, "completed": 26, "provider_error": 4}`。
- 临时 Normalized EM：19/100（19.00%）；固定分母100，10条未运行及4条服务失败暂计错，完整运行后的最终EM未得。
- 工具 657 次，API tokens 1,516,813，真实HTTP请求 420 次；服务报告费用 $0.11847578。
- 单条真实记录通过 86/100，引用通过 86/100；普通完整性 `False`，正式100条门槛 `False`。错误答案、诚实弃答、预算退出、基础设施错误分别按原始结束状态保留。
- 前15题用于程序排故，其余85题为固定程序后的复核范围，实际已记录75条、缺失10条；前15题EM 4/15，后85题EM 15/85，后85题单条记录通过 71/85。临时100题分母包含排故题及未运行题，不能声称100题全是未见复核样本。
- 没有其他组指标，不计算相对名次或课程得分。100题运行不等于三路完整工程验收，不能将验证集结果冒充正式测试集。

**当前阻碍与恢复条件：** 第87–90条出现真实HTTP 402，服务提示当前可用额度仅支持114个输出tokens，而请求的max_tokens为1024。只读额度接口仍显示名义剩余，因此不把名义限额当作实际可用余额；实际请求拒绝是停止依据。本轮未充值、修改账户限额或改用别的模型。4个失败HTTP没有usage，故保留“用量未知”，不假设费用为0。实际有26条模型作答（19正确、7错误）、60条模型弃答、4条服务失败、10题未运行。26条作答的19个正确不能作为100题完成率。

事后离线审计未追加API、未修改预测：60条弃答的真实收尾触发为search_stalled 46、reserve_final_usage 13、repeated_action 1；7条错误答案仍通过引用坐标及记录审计，说明“引用可定位”并不证明它支持正确答案。预算收尾修复解决了记录/循环问题，没有证明搜索准确率提升。当前答案效果仍未达到可靠使用的验证标准；下一步需在完整神经索引与可用额度恢复后，固定诊断/复核划分比较候选覆盖或独立语义核验，不能把这些尚未测试的策略写成已实现收益。90条记录的逐题elapsed合计2465.500秒（不是包含排队、构建和批间停顿的总墙钟时间）；正确/错误/弃答的逐题中位耗时分别22.411/50.928/16.373秒。

已按任务§1.5提示资源需求；剩余14次题目运行按当前单位题耗费粗估约$0.02–$0.05，不是预算保证。原服务恢复实际额度或在忽略的`.env`提供同服务已授权key后，可以使用下面定向恢复命令；endpoint/model/配置/程序/索引变化须新开输出目录。`.env`中的凭据值、账户标识和错误体中的key管理URL均不发布。当前未因等待额度而停止离线开发、索引补救、回传和推送。

已新增`scripts/recover_predictions.py`，用正式单条校验确定86条保留、14条待处理；dry-run不发API。恢复保留原4条失败于`.attempts.jsonl`，每条新真实结果先持久化journal再替换，进程中断后复用已落盘结果。遇到新的provider/模型/用量基础设施错误即停止。合成测试已验证不重复有效弃答、旧失败原样归档和journal恢复不重复API；额度未恢复，14条真实恢复仍待运行。不要使用普通`--rerun-failed`重跑本次60条有效弃答。

本轮outputs中以六字段保存的去重真实尝试（含最初失败、两轮诊断、消融、网页与官方验证）共158次、HTTP 652次、2,236,866 tokens、964工具、服务报告费用$0.16677907。这是去除相同记录副本后的实际合计，归档旧尝试也纳入，原始失败没有删除；不含历史回放、不属于六字段记录的独立API探针或账户其它运行，因此不冒充账户总账单；mock与demo未算成付费调用；未知用量事件4。

## 7. 测试、自审与可复现路径

最终主项目 `python -m pytest`：90通过；在`agent12/`执行`../.venv/bin/python -m unittest discover -s tests -v`：70通过；Ruff及pip check通过。新增回归含唯一JSON提取、同文档两个证据/截断范围、重开同一范围可选元数据、坏ID/重复ID/错坐标/缺返回/缺usage/假HTTP/篡改原响应、真实子进程中断恢复、索引身份变更拒绝及真实分片检查点恢复。测试夹具均为合成输入。

主环境从新venv实际安装依赖，不只重用旧解释器。另把源码开发包解压，在独立环境安装声明依赖并跑prepare/index/predict/validate，3个无标签合成输入得到2个有答案、1个弃答，普通覆盖校验通过；该包明确是开发源码包，不是课程最终提交包。完整课程包/报告/视频属于后续。

当前执行机先在项目根目录激活`.venv`。迁移环境可按README用Python3.12重建，并使用项目内缓存。不要提交或回显`.env`密钥。

### 无需API的实际烟测路线

```bash
rag-agent prepare --config configs/demo.yaml --source tests/fixtures/corpus.jsonl
rag-agent index --config configs/demo.yaml --methods sparse
rag-agent predict --config configs/demo.yaml --input tests/fixtures/questions.jsonl --output outputs/demo-new.jsonl --limit 1
rag-agent predict --config configs/demo.yaml --input tests/fixtures/questions.jsonl --output outputs/demo-new.jsonl
rag-agent validate --config configs/demo.yaml --input tests/fixtures/questions.jsonl --predictions outputs/demo-new.jsonl
```

实际同一路线使用`outputs/installed-demo.jsonl`及源码包隔离输出，退出0，3条完整；`--formal`拒绝demo符合预期。

### 指定模型小样本路线

```bash
rag-agent check-config --config configs/course-synthetic-agent12.yaml --live
rag-agent prepare --config configs/course-synthetic.yaml --source tests/fixtures/corpus.jsonl
rag-agent index --config configs/course-synthetic.yaml --methods sparse
rag-agent ask --config configs/course-synthetic-agent12.yaml 'When did the Copper Museum open?' --output outputs/new-live-smoke.jsonl
```

真实输出为1984，未手工编辑预测；单条正式条件由`validate_record(..., formal=True)`核验，小样本不能通过要求100条的`--formal`批量门槛。

### 全量索引及官方验证续跑路线

```bash
USE_TORCH=0 rag-agent prepare --config configs/course-full.yaml --hf --revision b27b02bc3e45511b8b82a13e6f90ce761df726f6
rag-agent index --config configs/course-full.yaml --methods sparse
# 以下会复用已校验的真实分片，当前硬件预计需数小时至数天：
rag-agent index --config configs/course-full-vectors-cpu.yaml --methods encoder
python scripts/index_in_shards.py --config configs/course-full-vectors.yaml --method instruction
# 当前候选使用完整BM25；先做0 API核查：
python scripts/recover_predictions.py --config configs/course-full-sparse.yaml --input data/validation.jsonl --predictions outputs/official-validation-r3/predictions.jsonl --dry-run
# 仅在原服务额度已恢复后执行，最多处理5条待恢复题：
python scripts/recover_predictions.py --config configs/course-full-sparse.yaml --input data/validation.jsonl --predictions outputs/official-validation-r3/predictions.jsonl --limit 5
# 重复恢复直至pending=0，再执行以下完整验收：
rag-agent validate --config configs/course-full-sparse.yaml --input data/validation.jsonl --predictions outputs/official-validation-r3/predictions.jsonl --formal
rag-agent validate --config configs/course-full-sparse.yaml --input data/validation.jsonl --predictions outputs/official-validation-r3/predictions.jsonl --formal --strict-grounding
rag-agent evaluate --config configs/course-full-sparse.yaml --input data/validation.jsonl --predictions outputs/official-validation-r3/predictions.jsonl
python scripts/audit_predictions.py --input data/validation.jsonl --predictions outputs/official-validation-r3/predictions.jsonl --evaluate --allow-partial --output outputs/official-validation-r3/audit-new.json
```

当前dry-run退出0：valid_existing=86、pending=14、missing=10、ineligible=4；部分诊断audit退出0但其ordinary_valid/formal_batch_valid均false。普通与正式validate会因缺10题退出1；完整evaluate因缺题退出2，这是预期的失败检查，并非100题验收通过。指定模型小样本和无需API路径在额度不足前实际退出0；当前无法保证新的付费smoke成功。

如果完成/变更神经索引，或修改代码、模型、Agent、问题文件，必须选择新的输出目录；身份校验会阻止混用旧结果。本次仅在身份未变且服务额度恢复后使用上面的`recover_predictions.py`；它保留所有已通过单条校验的弃答，只补缺失或无效记录，旧尝试进入`.attempts.jsonl`，所有尝试成本另行累计。不要手动修预测或轨迹。

## 8. 本机产物、迁移与下一步

忽略产物均在本项目下：

| 路径 | 实际内容 |
|---|---|
| `data/course-full/documents.sqlite` | 完整原文、URL、分块、固定来源revision、指纹 |
| `indexes/course-full/` | 完整sparse.sqlite/sparse.manifest.json；初始768源片段的两路检查点 |
| `indexes/course-full-vectors/` | 最高覆盖的两路向量、metadata、manifest；sparse文件用相对符号链接指向完整BM25，迁移需同时保留两个目录 |
| `indexes/model_cache/` | 固定版本E5/Qwen权重缓存；不进Git |
| `data/validation.jsonl` | 官方100验证题与参考答案；仅本地评测使用 |
| `data/rerank-eval/`、`indexes/rerank-eval-bounded/` | 97篇诊断语料、问题、独立标注及完整三路索引；不能改称全量 |
| `outputs/official-validation-r3/` | 每题六字段、完整真实轨迹、恢复清单、实际配置、代码SHA、进度和汇总 |
| `outputs/course-paired-r1/`、`outputs/course-paired-r2/` | 两轮同题对照、原始失败/成功和各自配置 |
| `outputs/real-mechanisms-r2/`、`outputs/real-context/`、`outputs/web-acceptance/` | 自动技能/多跳/恢复、长证据、浏览器真实下载记录 |
| `outputs/mechanism-ablations/`、`outputs/retrieval-comparison.json` | 关键机制与检索对照，原始内容本地保留 |
| `outputs/*test*`、`outputs/*install*`、`work/release-audit/` | 两套测试、安装、源码包隔离复现日志 |

迁移至少保留语料SQLite、完整及部分索引目录/manifest、固定模型revision、配置、题目输入、预测与.meta/.attempts清单；通过课程允许方式迁移大文件，Git仅含代码、回归、配置、说明和脱敏统计。安装后依然校验指纹/分片sha256；不要把其他机器同名路径当作相同索引。

推荐暂用`configs/course-full-sparse.yaml`的基线。下一步先恢复原服务额度补齐14条，完成100题覆盖/正式校验/最终EM；同时在合适的GPU执行机完成两路完整索引并测全量混合检索，再复核候选选择；当前本机的检查点可直接续跑。取得仅id/question的官方测试文件后，用同一个predict入口和新的输出路径处理100题，再正式校验并由组员决定版本冻结/最终课程材料。未取得文件不制造测试结果，不作成绩保证。

GitHub功能分支：[`codex/course-program-validation`](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/tree/codex/course-program-validation)。[与main比较](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/compare/main...codex/course-program-validation)。程序提交已实际推送并以`git ls-remote`核对；回传文档/脱敏结果随后提交同一分支，最终SHA见返回消息与远端HEAD。
