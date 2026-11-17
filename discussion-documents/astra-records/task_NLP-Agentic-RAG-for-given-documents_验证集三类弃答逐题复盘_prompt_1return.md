> 资料快照，来源提交 `e90397b`。[原始文件](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/e90397bb2e6af7657077c8fcee9189370a767a1f/docs/task_NLP-Agentic-RAG-for-given-documents_%E9%AA%8C%E8%AF%81%E9%9B%86%E4%B8%89%E7%B1%BB%E5%BC%83%E7%AD%94%E9%80%90%E9%A2%98%E5%A4%8D%E7%9B%98_prompt_1return.md)。采集于 2026-11-17（香港时间）。

# 验证集三类弃答逐题复盘回传

| 验证题 | 原分组 | 历史第一次可证实的问题及位置 | 证据定位 | 历史 EM | 百炼基线 EM | 下一步 |
|---|---|---|---|---:|---:|---|
| 960 | 工具未匹配参考全文 | R2/seq12重复首轮两查询；恢复技能首次加载即禁工具 | seq13/14零新证据；离线doc21800、72555 | 0 | 0，弃答 | 检验恢复工具机会、论文作者与贡献定位 |
| 1035 | 工具未匹配参考全文 | R1/seq7混淆创业者公司与同名城市关系；后续重复 | seq21–23；离线doc44626等 | 0 | 0，弃答 | 保持实体关系，再补销售额/代言时段证据 |
| 64 | 工具未匹配参考全文 | 旧查询只取前5，核心事件/城市桥接片段位于13/14 | doc10744:0、81158:750；新轮E4在api20消失 | 0 | 0，错答 | 优先保留已发现的事件段；本轮最终请求对照已答对 |
| 231 | 工具匹配、请求未匹配 | state10完整，context11/api13首丢E9 | doc43835:0；排11、剩938字符但需1114 | 0 | 0，弃答 | 新基线先找回候选，再补关系条件；旧状态保留对照仍弃答 |
| 390 | 工具匹配、请求未匹配 | state31完整，context32/api34首丢E43 | doc3282:750；排36、剩651但需741 | 0 | 0，弃答 | 查询目标合辑第3轨；讣闻歌名不证明轨序 |
| 58 | 工具匹配、请求未匹配 | state24完整，context25/api27首丢E30；短E37最终亦丢 | doc28406:38250/38806；最终E37差3字符 | 0 | 0，弃答 | 新轮先定位资助段；旧状态保留E37后最终请求答对 |
| 1155 | 请求匹配、最终弃答 | seq12重复首轮查询，seq13/14无新增；之后禁工具 | doc20784、62625日期冲突；机场距离缺口 | 0 | 0，错答 | 逐项核实地点、距离与日期，避免跳到另一遗址 |
| 1066 | 请求匹配、最终弃答 | seq13曾见E12；context18/api20遗漏完整候选段 | doc26814:0；排16、剩249但需918 | 0 | 0，弃答 | 保留候选再补片长/剪辑师链；下一动作对照已完成 |
| 788 | 请求匹配、最终弃答 | seq15重复已知指标；api29遗漏seq25第8名竣工段 | doc70534:0；新轮E12在api22同样丢失 | 0 | 0，弃答 | 保留条件证据；另核实医院成立与步行距离 |

## 完成范围与结论

本次完成九道指定官方验证题的历史逐事件还原、固定全量BM25检索重放、百炼九题有效基线，以及五组成对真实API诊断。**九题新基线EM为0/9：7题模型直接弃答，64和1155题非空错答；9题记录均通过身份与协议校验；2个非空答案通过引用来源检查，7个空答未触发非空引用核验。** 这里“有效”表示调用和记录合规，不表示答案正确；校验原文坐标也不等于证据逻辑能支持答案。

本次只研究这九道从历史失败中挑出的验证题，不是随机样本，不代表全验证集得分。原100题预测保持字节不变；没有读取隐藏测试标签，也没有重新运行100题或Qwen。E5已按原任务恢复构建，但全量尚未完成，不能参与本轮向量检索比较。

旧轮使用DeepSeek官方兼容端点，请求名为`deepseek-v4-flash`，旧记录响应名为`deepseek-flash`；本轮为百炼北京端点及`deepseek-v4-flash-0731`，所有成功响应均返回该精确ID。提供商与可观察模型标识发生变化；旧响应未给出精确版本，不能将两轮作为单因素模型比较。独立配置沿用BM25、baseline Agent、900/150字符切块、top_k=5默认值、12步、24工具、30,000 token、24,000上下文字符、每轮最多1,024输出token；实际模型可能在工具参数中请求其他top_k，逐事件表保留真实值。

本轮生产代码仅增加百炼`enable_thinking=false`发送适配；未把诊断用证据排序或目标片段保留策略装入默认Agent。北京接入与模型/thinking字段已核对[百炼DeepSeek说明](https://help.aliyun.com/zh/model-studio/deepseek-api)及[北京接入说明](https://www.alibabacloud.com/help/en/model-studio/beijing-access-information)。Key保存在独立、Git忽略的`.env`，权限600；旧环境与历史记录保留。

### 实测对照：相同模型、相同预算、只改已观察证据的保留

| 题号 / 对照位置 | 唯一干预 | 控制臂 → 处理臂 | API总token（控制/处理） | 可以支持的结论 |
|---|---|---|---:|---|
| 64，新百炼最终api51 | 快照E7换为此前已见E4；其余7项不变 | 错答EM0 → 答对EM1；两臂引用检查通过 | 3425 / 3474 | 本次冻结最终请求中，事件证据可见性影响了答案 |
| 231，旧最终状态在本轮百炼重放 | 只把已观察E9换回证据列表 | 弃答EM0 → 弃答EM0 | 3602 / 3680 | 保留候选片段不保证其余关系条件已充分 |
| 390，旧最终状态在本轮百炼重放 | 只把已观察E43换回证据列表 | 弃答EM0 → 弃答EM0 | 3466 / 3519 | 讣闻中的歌名不足以证明目标合辑第3轨 |
| 58，旧最终状态在本轮百炼重放 | 优先已有open/find片段；E37进入，伴随同一选择算法的容量变化 | 弃答EM0 → 答对EM1；两臂schema通过，处理臂E37引用检查通过 | 3581 / 3640 | 该open/find优先保留构造本次由空答转为EM1；未隔离E37单片段贡献 |
| 1066，旧api20下一动作状态在本轮百炼重放 | 仅E9换为已观察E12，其余8项不变 | 各返回2个search；处理臂第二个明确围绕候选题名与导演 | 4179 / 4140 | 候选定向措辞与局部排名变化；未取得终局答案，EM不适用 |

五组十次请求均HTTP200，均为同一0731模型、`enable_thinking=false`、temperature=0，合计36,706个API已报告总token（输入+输出）。64采用**新百炼基线**原最终请求；231/390/58/1066采用**历史冻结观察集合**，两臂均重新调用当前百炼，不能把旧提供商回复当成控制臂。历史payload的model/thinking字段在两臂做完全一致的适配，其余字段保持不变。

这些是事后条件诊断，一组各一次，没有全Agent重新检索，也没有统计显著性结论。231/390的目标定位为参考辅助；58规则优先已发生的open/find但样本本身事后选定；64、1066保留的证据已经由原Agent观察到。**五组结果不能计成新的9题EM或宣称通用修复完成。** 1066的4个真实下一动作仅在固定BM25离线执行，未回送模型；控制臂也找回候选（第2），处理臂第1并增加年份片段，但完整片长/剪辑师关系仍未补齐。

### 充值后的恢复、用量和校验

第一次基线已有5题有效，58在两次成功响应后遇到Arrearage，1155/1066/788首请求失败。充值后短请求成功，再只补跑4条不合格记录。原先5条有效预测字节完全未变；旧失败尝试另存，最终恢复检查为`valid_existing=9, pending=0, new_api_calls=0`。

有效九题共47次HTTP、77次工具调用、167,499个API已报告总token（输入+输出）。加上被替换的58部分成功调用、两次连接探测、合成工具往返和十次成对诊断，显式台账共67次请求：63次HTTP200、4次HTTP400，API已报告总用量合计213,830 token（输入+输出）；4次错误未给usage，用量未知，不能按零计费。详细台账见[public-run-summary.json](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/e90397bb2e6af7657077c8fcee9189370a767a1f/docs/validation-review/public-run-summary.json)。

软件校验：完整测试集155项收集，150项通过、5项既有条件跳过；本轮代码/脚本Ruff检查通过。离线历史重放：第一组44个检索前缀完全相等；第二组15次上下文实际消息完全相等，并有30次诊断构造比较；第三组12次入选证据ID及顺序与实际请求完全一致。协议/来源检查与语义正确性分开报告。精确原题、标签、答案及规范化比较放在加密证据，公开正文保留题意、事件号、调用ID、排名与原文坐标。

### 运行身份

| 项目 | 固定值 |
|---|---|
| 分支起点 | `b55b8a6c5c8d3b9ad7f573c7c5ad22a415041869` |
| 历史源码 / 配置 | `dab7646158fef729c3bf3e0f37b7f302727fc568` / `61d7cc3701b2a42a` |
| 历史100题预测SHA-256 | `17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8` |
| 百炼运行源码提交 / 源码hash | `8c8e545126e329919d2c16b18cacea6e139ebb29` / `e0579c80ca064ba4aacf94a93dfdf494be95644cb094c18ace9f8ee2235277d5` |
| 百炼基线配置 | `900fc3b95b775d2a` |
| 九题仅题号/问题输入SHA-256 | `dd829d11a47ce9c4d7c150c0e75fbdbcf57341b5197f3221c162dfe00fb60ce9` |
| 百炼最终预测SHA-256 | `c2abcd99c0c2c062584441aafc7200ffe8c00cab96d3c098ca194cb6261984cc` |
| 官方验证参考文件SHA-256 | `5efedfaa2dd4cf58ee0c38be59d68be1fe7eb5a19beb9d3c45bfe91afda4a4da` |
| 语料/索引指纹 | `ea8764233b0d4a76d050842e290805a0f154858084dfd0430ba8c0d9c555025f` |
| 数据规模 / 固定revision | 100,195文档、4,345,592片段 / `b27b02bc3e45511b8b82a13e6f90ce761df726f6` |

最终交付提交仅追加诊断脚本、证据统计和文档，不改变上述已经实测的核心源码。成对调用单独关闭重试，运输配置ID为`d3e477226d31ee7b`，请求正文与已准备条件逐字段核对。输入没有答案列；标签仅在独立评测阶段读取，初次九条记录（含运行失败）与恢复后九条有效记录的评测分别保留。离线参考辅助定位与模型输入相互独立。

## 九题完整过程

以下保留各组独立的历史及本轮逐事件复盘。组内所述“未调用模型”指相应离线审计脚本；实际API实测由根任务统一执行并记录在上述台账。时间线中的推断、字面命中、语义支持和未证实条件分别标明。



## 第一类三题逐题复盘（公开脱敏稿）

历史依据：源码 `dab7646`、配置 `61d7cc3701b2a42a`，原100题预测SHA-256 `17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8`。BM25、上下文、循环与技能源码逐文件与该提交一致；固定索引指纹仍一致，两个SQLite均只读打开。未读.env、未调用模型、未改历史字节、未运行Qwen。这里的百炼结果来自根任务已完成的真实基线，本组只做事后读取审计。

原分组均为“工具返回未匹配完整参考答案”，人工复核后保留此历史分类，但百炼64的故障阶段改变。公开稿不展示原题、精确参考答案、预测答案或长原文；这些与完整实际请求放入私有附件。

| ID | 历史首个可证实问题 | 历史EM | 百炼基线EM / 状态及首故障 | 下一步 |
|---|---|---:|---|---|
| 960 | seq12重复首轮两query；无新证据后首次恢复加载即禁工具 | 0 | 0 / 有效弃答；候选论文仍未定位，后续重复动作停止 | 给恢复一次真实工具机会，验证论文定位策略 |
| 1035 | seq7检索表述混合城市与创业者公司的关系；后续重复 | 0 | 0 / 有效弃答；关系重述正确后仍未召回桥接实体 | 明确实体关系，再连接品牌/城市/推广证据 |
| 64 | 原seq39/46只取前5；核心与城市桥接片段实际第13/14 | 0 | 0 / 非空错答；seq20事件段失去可见性，seq21混淆揭幕日与遇难事件 | 保留事件段，区分揭幕纪念日与被纪念事件 |

三题历史合计47,759tokens、22工具、14HTTP；百炼合计67,757tokens、32工具、19HTTP。本组新基线均有有效模型响应；首次九题尝试中其他组发生的账户Arrearage阻塞不混入本组弃答；用户充值后的恢复由主任务另行记录。服务商、模型版本与实际payload不同，不能把两轮直接称为单因素模型优劣实验。百炼请求 `deepseek-v4-flash-0731`、`enable_thinking=false`，本组3条formal检查均通过；64非空答案来源检查通过，960/1035空答未触发非空引用核验，EM均0。

### 离线检索对照边界

15个唯一历史query分别执行top5/top20，共30次；历史重复动作仍逐次保留在时间线。另有42次变体/实体续查，合计72次固定生产BM25搜索；44个历史前缀比较（原22次工具调用×2种深度）在doc/chunk/offset/text/score上全部精确一致。另5次明确标记的AND语料定位属于事后诊断，改变了表达式语义，不算生产BM25重放或在线Agent能力。

恢复技能原选择规则在stalled_searches非零时就可触发；960与1035的两个重复search同属一组，计数在组内0→1→2，下轮首次加载恢复技能即达到收尾条件。因此不能声称把触发阈值从2改成1就能解决；候选改动应是预算充足时为首次恢复保留一次工具机会，本轮未在线验证。

这证明历史结果可复现，没有证明当前查询一定能完成语义检索。参考答案辅助、已知文档日期辅助、正文实体续搜分别标记；其中960加入已知年份的后续query不能称为盲改进。全量神经索引未就绪，本组未作向量对照。

### ID 960

从一篇晚近十年代精神健康研究的作者贡献表，找出唯一没有承担研究方法工作的作者。需核对九名作者、六位同学院而跨校区、北半球研究地点、指名资助和另一篇青年抑郁研究的五作者重叠。

**历史判断。** R1/seq5构造的两条宽泛检索没有把核心论文送入前10；固定重放前20仍未找到。R2/seq12逐字重复两条查询、seq13/14均0新证据，是最早能直接证明的无进展动作。 seq16/17第一次加载恢复技能后立即seq18停滞收尾，实际seq21请求tool_choice=none；剩余24693tokens。程序给了恢复正文但没有恢复检索机会。

**原因边界。** OR词项评分、通用学术词较多且缺少稀有实体可能造成排名偏离；重放证明索引按既有规则稳定执行，不能据此断言BM25实现错误。

**离线对照。** 纯题面词的四个变体未在前20取得21800；参考答案辅助query把21800:3750:900推至第2。事后已知论文年份的query取得21800:0:900第9；标post_hoc_document_informed，不当作盲改查询成功。

#### 条件与原文定位

这些文档是离线诊断重新定位的证据，不代表历史模型已经看到；原模型可见范围以下表真实API行为为准。

| 条件 | 核查状态 | 语料定位（Unicode左闭右开） |
|---|---|---|
| 论文时段/地点 | 支持 | `21800:[0,900)` |
| 九名作者及八位承担方法工作 | 支持 | `21800:[3317,5935)` |
| 六位同学院，分两校区 | 支持；若institution指大学，九位均属同一大学，需说明粒度 | `21800:[3317,5935)` |
| 资助授予指定作者 | 支持 | `21800:[2871,3210)` |
| 青年抑郁论文五作者交集 | 支持；以两文作者名单人工对齐 | `72555:[0,900)` |

#### 历史每次API、决策和工具动作

查询编号的公开语义说明：original-01：泛精神健康、九作者与方法贡献；original-02：青年抑郁、五作者联系和资助。

Q编号对应私有query-plan中的真实查询原文；同编号出现两次仍是两次真实执行。每个工具的完整排名、文档/片段ID和起止坐标在公开统计actions.results，原文在私有JSON。

| seq / R | 类型 | 实际操作与可观察依据 |
|---|---|---|
| 4 / 1 | api_attempt | HTTP200；2602字符；tool_choice=auto；可见证据无；1451tokens |
| 5 / 1 | assistant | 提出调用 call_00_mbwIUGd7c1Nhnw9qLdiK2767,call_01_nwveVEF4rikx1VRiW2VG4124 |
| 6 / 1 | tool | search original-01；top_k=10；返回10、新增10；重复query=False；调用call_00_mbwIUGd7c1Nhnw9qLdiK2767 |
| 7 / 1 | tool | search original-02；top_k=10；返回10、新增10；重复query=False；调用call_01_nwveVEF4rikx1VRiW2VG4124 |
| 11 / 2 | api_attempt | HTTP200；13149字符；tool_choice=auto；可见证据E3,E13,E1,E4,E11,E7,E12,E5,E8；3856tokens |
| 12 / 2 | assistant | 提出调用 call_00_g64fNrKCZVnt06NfkNKO5930,call_01_mI6gUU6SyRX22FK3fpCK9256 |
| 13 / 2 | tool | search original-01；top_k=10；返回10、新增0；重复query=True；调用call_00_g64fNrKCZVnt06NfkNKO5930 |
| 14 / 2 | tool | search original-02；top_k=10；返回10、新增0；重复query=True；调用call_01_mI6gUU6SyRX22FK3fpCK9256 |
| 21 / 3 | api_attempt | HTTP200；13626字符；tool_choice=none；可见证据E3,E13,E1,E4,E11,E7,E12,E5；3000tokens |
| 22 / 3 | assistant | 原始模型直接返回空答JSON；解析后原样导出空字符串 |

#### 百炼已完成基线对照

真实HTTP7次、工具12次、23567tokens，精确重复query4次；formal与引用错误均为空。
新模型曾open_document检查一个早期候选，还发起基于其项目实体的查询，因而比历史有更多结果驱动动作；但没有找到核心论文。之后重复查询达到限制，seq41为repeated_action，seq42为run_stopping；seq45收尾，原始模型给空答，导出空答，严格EM0。不能把多花tokens或多调用工具当作答题改善。


#### 百炼基线每次API、决策和工具动作

下面为完整新基线动作表；它与随后两条最终请求pair分开计数。每个实际请求均从api_attempt.request.messages核对，完整工具参数和响应在私有原迹。

| seq / R | 类型 | 实际动作及证据边界 |
|---|---|---|
| 4 / 1 | api_attempt | HTTP200；2602字符；工具=auto；可见无；usage=1437 |
| 5 / 1 | assistant | 启动两条宽泛检索；call_id=call_d8413692da374d66b522de2d,call_5bac3bbdf1114596a7247838 |
| 6 / 1 | tool | 精神健康论文的时期及九作者条件；search，返回5项；call_id=call_d8413692da374d66b522de2d；top_k=5 |
| 7 / 1 | tool | 青年抑郁研究与作者关系；search，返回5项；call_id=call_5bac3bbdf1114596a7247838；top_k=5 |
| 11 / 2 | api_attempt | HTTP200；13026字符；工具=auto；可见E1,E6,E9,E3,E7,E5,E10,E4,E8；usage=3983 |
| 12 / 2 | assistant | 根据E1选出一篇候选，打开原文并以其项目名续搜；call_id=call_143129890cf2481482078635,call_9642bbce852647c4ba66b6f5 |
| 13 / 2 | tool | 打开早期候选文档41503开头2400字符；open_document，返回1项；call_id=call_143129890cf2481482078635；读取参数={"doc_id": "41503", "offset": 0, "limit": 2400} |
| 14 / 2 | tool | 基于候选项目名继续找九作者及方法；search，返回5项；call_id=call_9642bbce852647c4ba66b6f5；top_k=5 |
| 18 / 3 | api_attempt | HTTP200；13377字符；工具=auto；可见E1,E6,E9,E11,E3,E7,E14,E5；usage=3840 |
| 19 / 3 | assistant | 重新从题目约束发起两条检索；call_id=call_91dc82015e1845258abf027a,call_bae3f03b718c4c14b7ddcea7 |
| 20 / 3 | tool | 同机构跨校区的精神健康论文；search，返回5项；call_id=call_91dc82015e1845258abf027a；top_k=5 |
| 21 / 3 | tool | 九作者、资助及作者贡献；search，返回5项；call_id=call_bae3f03b718c4c14b7ddcea7；top_k=5 |
| 25 / 4 | api_attempt | HTTP200；13486字符；工具=auto；可见E1,E6,E21,E22,E9,E11,E16,E20；usage=3858 |
| 26 / 4 | assistant | 重复核心query并微调另一条；call_id=call_176927e7bdf04b60a6e2ccf8,call_ba89c386fc40425a9de16c0e |
| 27 / 4 | tool | 再次搜索同机构跨校区条件；search，返回5项；call_id=call_176927e7bdf04b60a6e2ccf8；top_k=5 |
| 28 / 4 | tool | 调整作者贡献关键词；search，返回5项；call_id=call_ba89c386fc40425a9de16c0e；top_k=5 |
| 32 / 5 | api_attempt | HTTP200；12435字符；工具=auto；可见E1,E6,E24,E21,E22,E9,E11；usage=3674 |
| 33 / 5 | assistant | 重新列出条件，继续重复/微调；call_id=call_19ce4aad60c744a5b4bf23d6,call_da1478ac844145af84a28ffb |
| 34 / 5 | tool | 再次复用同机构跨校区query；search，返回5项；call_id=call_19ce4aad60c744a5b4bf23d6；top_k=5 |
| 35 / 5 | tool | 在贡献关键词中增加资助词；search，返回5项；call_id=call_da1478ac844145af84a28ffb；top_k=5 |
| 39 / 6 | api_attempt | HTTP200；12457字符；工具=auto；可见E1,E6,E24,E21,E22,E9,E11；usage=3610 |
| 40 / 6 | assistant | 再发重复query，随后触发工具侧限制；call_id=call_79c377c77dbc461bae36998b,call_39d97b1d181b40c08b4bfd5e |
| 41 / 6 | tool | 第四次复用同一query，被重复动作限制拒绝；search，返回0项；call_id=call_79c377c77dbc461bae36998b；top_k=5 |
| 42 / 6 | tool | 因前一调用进入停止状态而未执行；search，返回0项；call_id=call_39d97b1d181b40c08b4bfd5e；top_k=5 |
| 48 / 7 | api_attempt | HTTP200；13794字符；工具=none；可见E1,E6,E24,E21,E22,E9,E11；usage=3165 |
| 49 / 7 | assistant | 原始模型解释证据不足并给空答；解析保留空答 |

**下一步。** 先让恢复技能获得至少一次仍可调用工具的机会；另在无标签开发对照上评估更有区分度的查询与论文标题/作者栏定位。当前离线语义证据可确认官方参考，但未证明在线Agent能自行找到。

### ID 1035

识别一家成立时间、城市同名关系、运动员代言、海岸演出和指定年度销售额共同约束的公司。创业者仅用于定位同名城市，其应用创业公司并非必然就是待找公司。

**历史判断。** R1/seq7动作说明和Q01将“创业者迁居城市与公司A同名”压成“创业者公司以城市命名”。这是可观察查询关系偏差；R3/seq21又逐字重复R2两条query，seq22/23均0新证据。 seq25/26恢复技能首次加载，seq27即search_stalled，seq30实际tool_choice=none；剩余20082tokens，非token耗尽。

**原因边界。** 多个实体关系被放进长OR查询可能让不相关商业/演出文段排前；不能仅由结果差断言索引坏了。

**离线对照。** 4个历史唯一query各前20和6个纯题面词变体各前20均未命中已定位核心文档。参考答案辅助query找回44626/72400/45782/51735；连接创业者城市和运动员出生年的AND定位也明确为事后诊断，非生产检索重放。

#### 条件与原文定位

这些文档是离线诊断重新定位的证据，不代表历史模型已经看到；原模型可见范围以下表真实API行为为准。

| 条件 | 核查状态 | 语料定位（Unicode左闭右开） |
|---|---|---|
| 公司成立晚于给定年份 | 支持 | `44626:[0,750)` |
| 同名城市/创业者出生年代/随母迁居/应用业务 | 支持；post-hoc定位 | `66841:[0,1650)` |
| 运动员参与推广 | 支持；广告页面元数据日期异常，不能据此确认推广时段 | `51735:[0,900)` |
| 运动员出生年份 | 支持 | `82418:[1500,2400)` |
| 演出到场人数与政府官员 | 支持；North Coast地名不是原文明确beach词 | `72400:[1250,2200)` |
| 指定年度约十亿美元销售 | 部分：原文为本币31b；不能不查汇率就声称逐字USD一致 | `45782:[2850,3150)` |

#### 历史每次API、决策和工具动作

查询编号的公开语义说明：original-01：创业者迁居与应用公司命名关系（关系表述发生混合）；original-02：成立年代、代言、演出和销售额合并长query；original-03：删去修饰词后重复创业者/城市命名线索；original-04：删去成立年代后搜索公司代言/演出/销售。

Q编号对应私有query-plan中的真实查询原文；同编号出现两次仍是两次真实执行。每个工具的完整排名、文档/片段ID和起止坐标在公开统计actions.results，原文在私有JSON。

| seq / R | 类型 | 实际操作与可观察依据 |
|---|---|---|
| 6 / 1 | api_attempt | HTTP200；4061字符；tool_choice=auto；可见证据无；1804tokens |
| 7 / 1 | assistant | 提出调用 call_00_Zg7GGweVHKt4Nz6Wcf5n6084,call_01_psA585Y6mngpyPNPGroj6165 |
| 8 / 1 | tool | search original-01；top_k=10；返回10、新增10；重复query=False；调用call_00_Zg7GGweVHKt4Nz6Wcf5n6084 |
| 9 / 1 | tool | search original-02；top_k=10；返回10、新增9；重复query=False；调用call_01_psA585Y6mngpyPNPGroj6165 |
| 13 / 2 | api_attempt | HTTP200；13512字符；tool_choice=auto；可见证据E2,E11,E3,E4,E1,E5,E16,E9；4015tokens |
| 14 / 2 | assistant | 提出调用 call_00_ti1hCTAVrRp3QlF8sl1V0011,call_01_EXoWsSfSMAhtauMGBWoI8787 |
| 15 / 2 | tool | search original-03；top_k=10；返回10、新增3；重复query=False；调用call_00_ti1hCTAVrRp3QlF8sl1V0011 |
| 16 / 2 | tool | search original-04；top_k=10；返回10、新增4；重复query=False；调用call_01_EXoWsSfSMAhtauMGBWoI8787 |
| 20 / 3 | api_attempt | HTTP200；13839字符；tool_choice=auto；可见证据E2,E11,E21,E3,E4,E1,E5,E16；4099tokens |
| 21 / 3 | assistant | 提出调用 call_00_4jtFrWZQpKvNmIL8XPRB3325,call_01_0uRVDqUYw4D8PeHdhFvY6067 |
| 22 / 3 | tool | search original-03；top_k=10；返回10、新增0；重复query=True；调用call_00_4jtFrWZQpKvNmIL8XPRB3325 |
| 23 / 3 | tool | search original-04；top_k=10；返回10、新增0；重复query=True；调用call_01_0uRVDqUYw4D8PeHdhFvY6067 |
| 30 / 4 | api_attempt | HTTP200；14345字符；tool_choice=none；可见证据E2,E11,E21,E3,E4,E1,E5；3271tokens |
| 31 / 4 | assistant | 原始模型直接返回空答JSON；解析后原样导出空字符串 |

#### 百炼已完成基线对照

真实HTTP5次、工具8次、17820tokens，精确重复query3次；formal与引用错误均为空。
新模型首轮能正确列出公司—同名城市—创业者的关系，修正了历史公开检索措辞中的混合；但两条分支仍没有找到目标证据。后续切换演出/代言线索，又逐字重复，seq34因search_stalled收尾；真实模型输出空答，严格EM0。它说明关系重述正确本身还不足以解决召回。


#### 百炼基线每次API、决策和工具动作

下面为完整新基线动作表；它与随后两条最终请求pair分开计数。每个实际请求均从api_attempt.request.messages核对，完整工具参数和响应在私有原迹。

| seq / R | 类型 | 实际动作及证据边界 |
|---|---|---|
| 6 / 1 | api_attempt | HTTP200；4061字符；工具=auto；可见无；usage=1846 |
| 7 / 1 | assistant | 正确列出公司—同名城市—创业者关系并双检索；call_id=call_9a4a045d63e34e3cb8e13441,call_9007478b141342a28edee5a6 |
| 8 / 1 | tool | 公司成立年代与销售额；search，返回5项；call_id=call_9a4a045d63e34e3cb8e13441；top_k=5 |
| 9 / 1 | tool | 创业者迁居与应用业务；search，返回5项；call_id=call_9007478b141342a28edee5a6；top_k=5 |
| 13 / 2 | api_attempt | HTTP200；13478字符；工具=auto；可见E6,E5,E10,E2,E3,E4,E9,E7；usage=4229 |
| 14 / 2 | assistant | 复用创业者分支，扩展公司分支；call_id=call_08774eec41044d07a5962fd7,call_2efa1d82bffb4ddb99286a3c |
| 15 / 2 | tool | 重复上一轮创业者query；search，返回5项；call_id=call_08774eec41044d07a5962fd7；top_k=5 |
| 16 / 2 | tool | 为公司query增加演出和代言；search，返回5项；call_id=call_2efa1d82bffb4ddb99286a3c；top_k=5 |
| 20 / 3 | api_attempt | HTTP200；13595字符；工具=auto；可见E11,E6,E5,E10,E2,E3,E4,E9；usage=4223 |
| 21 / 3 | assistant | 转向演出和代言两条线索；call_id=call_a2e3e82b501c4a98bf7ab826,call_03142b42e3fe4c9d881cec57 |
| 22 / 3 | tool | 海岸演出及政府人员到场；search，返回5项；call_id=call_a2e3e82b501c4a98bf7ab826；top_k=5 |
| 23 / 3 | tool | 运动员出生年及公司合作；search，返回5项；call_id=call_03142b42e3fe4c9d881cec57；top_k=5 |
| 27 / 4 | api_attempt | HTTP200；13667字符；工具=auto；可见E11,E6,E5,E10,E2,E3,E4,E9；usage=4235 |
| 28 / 4 | assistant | 逐字重复上一轮两query；call_id=call_3018da8a557c44d68a351228,call_0bd0c1d5af70478ca312ca9d |
| 29 / 4 | tool | 重复演出query；search，返回5项；call_id=call_3018da8a557c44d68a351228；top_k=5 |
| 30 / 4 | tool | 重复运动员合作query；search，返回5项；call_id=call_0bd0c1d5af70478ca312ca9d；top_k=5 |
| 37 / 5 | api_attempt | HTTP200；14122字符；工具=none；可见E11,E6,E5,E10,E2,E3,E4；usage=3287 |
| 38 / 5 | assistant | 原始模型直接空答；解析保留空答 |

**下一步。** 优先拆清“公司—同名城市—创业者”的关系，再按所得城市/品牌续搜；金额币种及推广时间仍需语义核查，不以碰到品牌名当全条件证明。

### ID 64

根据波黑大城市中的战难纪念物、艺术家出生年代和建成年代，回答被纪念事件发生的年份；需区分建成年和事件年。

**历史判断。** 原查询R1未送入关键纪念文档；更明确可定位的范围问题发生在seq39/46：同一原query历史top_k=5，固定BM25第13名是核心10744:0:900，第14名81158:750:900是城市排行桥接段。 原工具返回已有城市列表文档，但所取0:900与1500:2400并未完整包含前四名的中间段；模型也未open/find相邻正文。seq48因reserve_final_usage收尾，剩余7065tokens。恢复技能在seq25/26已加载并获得后续工具轮次，不能套用960/1035的首次加载即禁工具结论。

**原因边界。** 这证明原候选范围截断了可用证据，不证明扩大top_k后模型一定能解答。初轮的通用纪念物结果也不能单独判实现错误。

**离线对照。** 原query第13名直接包含核心身份、建造年和事件年；纯题面变体也在第4名返回同文档邻接片段、第9名返回核心首片。由正文设计者实体续搜后，出生年资料第1名出现。语义链在离线可闭合，未进行在线top20单变量复测。

#### 条件与原文定位

这些文档是离线诊断重新定位的证据，不代表历史模型已经看到；原模型可见范围以下表真实API行为为准。

| 条件 | 核查状态 | 语料定位（Unicode左闭右开） |
|---|---|---|
| 纪念地点与城市 | 支持 | `10744:[0,900)` |
| 建成年早于阈值/设计者 | 支持 | `10744:[0,900)` |
| 遇难事件和年份 | 支持 | `10744:[750,1650)` |
| 2013人口城市/municipality前四 | 支持；来源以municipality口径列排名 | `81158:[750,1650)` |
| 艺术家出生年 | 支持；从已定位正文设计者实体离线续搜 | `50486:[0,127)` |

#### 历史每次API、决策和工具动作

查询编号的公开语义说明：original-01：地区、遇难者纪念物和艺术家出生年；original-02：人口普查大城市与碑建造时间上限；original-03：艺术家出生年及设计地点；original-04：人口普查中的前四大城市；original-05：调整城市/municipality/人口词序；original-06：用sculptor及出生年搜索纪念物；original-07：人口普查大城及人口；original-08：大municipality与人口；original-09：雕塑家出生年与地区全称（关键片段在第13/14）。

Q编号对应私有query-plan中的真实查询原文；同编号出现两次仍是两次真实执行。每个工具的完整排名、文档/片段ID和起止坐标在公开统计actions.results，原文在私有JSON。

| seq / R | 类型 | 实际操作与可观察依据 |
|---|---|---|
| 6 / 1 | api_attempt | HTTP200；3780字符；tool_choice=auto；可见证据无；1681tokens |
| 7 / 1 | assistant | 提出调用 call_00_k8l56aWldQNCnLZelDv05384,call_01_6evi0xhNy5TQnKdKYStG0964 |
| 8 / 1 | tool | search original-01；top_k=10；返回10、新增10；重复query=False；调用call_00_k8l56aWldQNCnLZelDv05384 |
| 9 / 1 | tool | search original-02；top_k=10；返回10、新增8；重复query=False；调用call_01_6evi0xhNy5TQnKdKYStG0964 |
| 13 / 2 | api_attempt | HTTP200；13598字符；tool_choice=auto；可见证据E9,E3,E5,E7,E10,E8,E14,E16,E11；4151tokens |
| 14 / 2 | assistant | 提出调用 call_00_s6EETpuv3TtqrGgNduLj0969,call_01_Isds8ReBoe8rTZyjPeDj1380 |
| 15 / 2 | tool | search original-03；top_k=10；返回10、新增5；重复query=False；调用call_00_s6EETpuv3TtqrGgNduLj0969 |
| 16 / 2 | tool | search original-04；top_k=5；返回5、新增1；重复query=False；调用call_01_Isds8ReBoe8rTZyjPeDj1380 |
| 20 / 3 | api_attempt | HTTP200；13717字符；tool_choice=auto；可见证据E9,E3,E5,E7,E10,E19,E23,E8,E11；4158tokens |
| 21 / 3 | assistant | 提出调用 call_00_TlUegzCcszDTXACeGZHx0698,call_01_LjI041vO7HHIR37ZOnc46432 |
| 22 / 3 | tool | search original-05；top_k=5；返回5、新增1；重复query=False；调用call_00_TlUegzCcszDTXACeGZHx0698 |
| 23 / 3 | tool | search original-03；top_k=5；返回5、新增0；重复query=True；调用call_01_LjI041vO7HHIR37ZOnc46432 |
| 29 / 4 | api_attempt | HTTP200；14667字符；tool_choice=auto；可见证据E9,E3,E5,E7,E10,E19,E23,E8；4308tokens |
| 30 / 4 | assistant | 提出调用 call_00_rJvb9bGA6UYo8RAqECmU1437,call_01_1StBWM7EVzfwbIXp8KBS2890 |
| 31 / 4 | tool | search original-06；top_k=10；返回10、新增8；重复query=False；调用call_00_rJvb9bGA6UYo8RAqECmU1437 |
| 32 / 4 | tool | search original-07；top_k=10；返回10、新增3；重复query=False；调用call_01_1StBWM7EVzfwbIXp8KBS2890 |
| 36 / 5 | api_attempt | HTTP200；14672字符；tool_choice=auto；可见证据E9,E3,E29,E5,E7,E10,E19,E23；4305tokens |
| 37 / 5 | assistant | 提出调用 call_00_joXj802y6l8d3ksdGztY7987,call_01_h5FxMjZHDkf0DGMKovVt0791 |
| 38 / 5 | tool | search original-08；top_k=5；返回5、新增0；重复query=False；调用call_00_joXj802y6l8d3ksdGztY7987 |
| 39 / 5 | tool | search original-09；top_k=5；返回5、新增2；重复query=False；调用call_01_h5FxMjZHDkf0DGMKovVt0791 |
| 43 / 6 | api_attempt | HTTP200；14640字符；tool_choice=auto；可见证据E9,E3,E29,E5,E7,E10,E19,E23；4332tokens |
| 44 / 6 | assistant | 提出调用 call_00_PyQyNjhsdlTcCqgGK3sd8293,call_01_wZffkol1u7l9vX7En6O36933 |
| 45 / 6 | tool | search original-08；top_k=5；返回5、新增0；重复query=True；调用call_00_PyQyNjhsdlTcCqgGK3sd8293 |
| 46 / 6 | tool | search original-09；top_k=5；返回5、新增0；重复query=True；调用call_01_wZffkol1u7l9vX7En6O36933 |
| 51 / 7 | api_attempt | HTTP200；14184字符；tool_choice=none；可见证据E9,E3,E29,E5,E7,E10,E19,E11；3328tokens |
| 52 / 7 | assistant | 原始模型直接返回空答JSON；解析后原样导出空字符串 |

#### 百炼已完成基线对照

真实HTTP7次、工具12次、26370tokens，精确重复query0次；formal与引用错误均为空。
新基线已在seq8第4名取回10744:0:900，seq13真实请求明确包含E4及被纪念事件年。因此这一轮已不属于“根本没召回”。seq20请求首次省去E4，保留E12=10744:5250:900的揭幕段；源码按题目词交集排序，E4始终11分，从seq10状态第7降至seq17状态第10，E12为13分。真实请求的变化与这一选择规则一致；随后seq21模型把“揭幕日期恰逢某起义纪念日”当成“碑本身纪念的遇难事件”，把另一个年份放进后续搜索。此后的请求没有再包含E4，虽然工具多次重新取回同一首片。

最终seq51只保留E28揭幕段、出生年E10及人口表尾部E30等；seq52原始模型自己输出错误年份，seq53解析/导出保留它，非程序把正确答案改错。E30位于81158:[1500,2400)，并不包含所称城市前四名；最终引用虽来自真原文，却不足以证明回答中的全部关系。首次可证明的程序侧选择损失是seq20；首次可见语义关系混淆是seq21。二者均有记录，但尚未通过单变量模型复测分离因果贡献。


#### 百炼基线每次API、决策和工具动作

下面为完整新基线动作表；它与随后两条最终请求pair分开计数。每个实际请求均从api_attempt.request.messages核对，完整工具参数和响应在私有原迹。

| seq / R | 类型 | 实际动作及证据边界 |
|---|---|---|
| 6 / 1 | api_attempt | HTTP200；3780字符；工具=auto；可见无；usage=1722 |
| 7 / 1 | assistant | 分解六项条件并双检索；call_id=call_28ae9eb710ef4591b31e2f39,call_30204c9ed4c646729103be9e |
| 8 / 1 | tool | 碑、地点与艺术家出生年；search，返回5项；call_id=call_28ae9eb710ef4591b31e2f39；top_k=5 |
| 9 / 1 | tool | 地区、建成年限与纪念物；search，返回5项；call_id=call_30204c9ed4c646729103be9e；top_k=5 |
| 13 / 2 | api_attempt | HTTP200；13088字符；工具=auto；可见E6,E1,E8,E7,E9,E3,E4,E5；usage=4192 |
| 14 / 2 | assistant | 由核心碑文提取设计者，核对出生年与城市；call_id=call_a4f044b896a141cfbfd342cb,call_76d71500a8a74fd38e786c2b |
| 15 / 2 | tool | 用已发现艺术家姓名核对出生年；search，返回5项；call_id=call_a4f044b896a141cfbfd342cb；top_k=5 |
| 16 / 2 | tool | 用城市候选核对人口排行；search，返回5项；call_id=call_76d71500a8a74fd38e786c2b；top_k=5 |
| 20 / 3 | api_attempt | HTTP200；13411字符；工具=auto；可见E6,E1,E8,E7,E9,E11,E12,E18,E10；usage=4227 |
| 21 / 3 | assistant | 将揭幕节日当作纪念事件，发起年份假设查询并读揭幕段；call_id=call_1f2b4ece1a11451d986a8d0b,call_d3131c10482f4a0c923e4adc |
| 22 / 3 | tool | 把揭幕节日假设作遇难事件继续搜索；search，返回5项；call_id=call_1f2b4ece1a11451d986a8d0b；top_k=5 |
| 23 / 3 | tool | 打开10744揭幕段[5250,6450)；open_document，返回1项；call_id=call_d3131c10482f4a0c923e4adc；读取参数={"doc_id": "10744", "offset": 5250, "limit": 1200} |
| 27 / 4 | api_attempt | HTTP200；13440字符；工具=auto；可见E6,E1,E8,E19,E7,E9,E11,E12,E10；usage=4199 |
| 28 / 4 | assistant | 沿同一事件假设继续搜并核查人口；call_id=call_a33ff0da0e224affa06dc603,call_d4fa6d6fe6a7478db1dd16ce |
| 29 / 4 | tool | 沿同一事件年份假设搜索；search，返回5项；call_id=call_a33ff0da0e224affa06dc603；top_k=5 |
| 30 / 4 | tool | 城市人口核查；search，返回5项；call_id=call_d4fa6d6fe6a7478db1dd16ce；top_k=5 |
| 34 / 5 | api_attempt | HTTP200；13891字符；工具=auto；可见E6,E1,E8,E19,E7,E9,E11,E12,E27,E10；usage=4345 |
| 35 / 5 | assistant | 继续假设查询，再读同一起点的更长段落；call_id=call_cda6edc623644ac3be958012,call_147456024edd494d8186b309 |
| 36 / 5 | tool | 继续同一碑与起义事件假设；search，返回5项；call_id=call_cda6edc623644ac3be958012；top_k=5 |
| 37 / 5 | tool | 再次打开相同起点，扩大至[5250,6850)；open_document，返回1项；call_id=call_147456024edd494d8186b309；读取参数={"doc_id": "10744", "offset": 5250, "limit": 1600} |
| 43 / 6 | api_attempt | HTTP200；14497字符；工具=auto；可见E6,E1,E8,E19,E28,E7,E9,E27；usage=4241 |
| 44 / 6 | assistant | 重述线索后再双检索；call_id=call_b51f82186c5145ed87be5dba,call_6aebba9069f94482b099fa73 |
| 45 / 6 | tool | 城市、艺术家出生年和起义词；search，返回5项；call_id=call_b51f82186c5145ed87be5dba；top_k=5 |
| 46 / 6 | tool | 人口普查与最大城市；search，返回5项；call_id=call_6aebba9069f94482b099fa73；top_k=5 |
| 51 / 7 | api_attempt | HTTP200；14722字符；工具=none；可见E6,E1,E8,E19,E28,E30,E7,E10；usage=3444 |
| 52 / 7 | assistant | 原始模型直接输出错误年份；程序原样解析导出 |

**后续验证边界。** 历史top5遗漏与新百炼的关键片段丢失是两个阶段的问题。历史查询的top5/top20固定重放已完成，但没有据此执行完整Agent重跑；新百炼已取得E4，因此本轮另做下面的单证据最终请求对照。通用证据保留策略仍需在不借助答案标签的开发样例上验证，不能把离线定位或本题事后选片当作自主能力改善。

### E4单证据最终请求对照：真实响应已验证

针对新百炼64最终请求seq51，冻结context函数、seq47实际state和6个原始工具组重放出的控制messages与真实请求逐字相等。治疗只在同一证据位置将E7替换为已观察过的E4（10744:0:900），其余7个证据、顺序、技能、system/user、工具及采样参数保持一致；出生年证据E10仍保留。两者tool_choice均none、max_tokens均1024、enable_thinking均false。

冻结证据配额8758字符，控制使用8715、治疗8683；最终完整请求为14722/14716字符，均在同一24000预算内。E4早在seq8、15、22、29、36、45的真实工具返回中出现，因此没有注入未观察片段。选择E4是事后参考答案辅助诊断，标签字符串没有另加到模型输入；原文自身包含的事实属于已观察证据。

两份完整payload为私有`e4-counterfactual/control-request-private.json`和`treatment-request-private.json`，公开来源证明为`e4-counterfactual/provenance-public.json`。主任务已分别执行一次，实际发送body与准备文件完全一致；本子任务只做离线验证，未另发API。

| 最终请求条件 | HTTP/模型 | E4当前可见 | 模型非空回答 | 严格EM | final schema/生产原文引用/当前请求可见引用 | 新增实际tokens |
|---|---|---|---|---:|---|---:|
| control原选择 | 200 / 固定0731 | 否 | 是 | 0 | 全通过，引用E28/E10/E30 | 3,425 |
| treatment仅E7→E4 | 200 / 同模型 | 是 | 是 | 1 | 全通过，引用E4/E28/E10 | 3,474 |

这两条新调用合计6,899tokens；加入同一真实收尾前已用22,926tokens后，分别为26,351和26,400，均低于原30,000预算。prompt/completion分别3331/94和3357/117；没有把历史完整基线用量再次当本次新增消耗。两份原始响应及解析结果、精确答案、规范化和引用文本保存在私有附件，公开数值见`e4-counterfactual/paired-results-public.json`。

控制仍将揭幕纪念日关联的事件当作所问事件；治疗转而引用E4中的实际遇难事件并匹配参考答案。本对照支持“在这个固定最终请求中，保留已经观察到的关键事件片段可以纠正最终答案”。每个条件只有一次响应，而且E4是事后辅助选择；它不证明完整Agent能自主保留E4、不证明一般题目的准确率提升，也不等同部署了通用选择策略。原历史与本次完整百炼基线的EM仍为0，不能用这个局部pair的EM1替换它们。

### 复现与附件清单

从BASE目录运行；Python使用已安装项目依赖的解释器，脚本不读取dotenv。私有计划文件从加密附件恢复到指定输出目录后运行：

```sh
PYTHONDONTWRITEBYTECODE=1 python work/validation-review-drafts/group-a/replay_group_a.py --extract --replay
python work/validation-review-drafts/group-a/locate_group_a.py --plan work/validation-review-drafts/group-a/locator-plan-private.json
python work/validation-review-drafts/group-a/export_group_a.py
PYTHONDONTWRITEBYTECODE=1 python work/validation-review-drafts/group-a/audit_bailian_group_a.py
PYTHONDONTWRITEBYTECODE=1 python work/validation-review-drafts/group-a/prepare_e4_counterfactual.py
PYTHONDONTWRITEBYTECODE=1 python work/validation-review-drafts/group-a/validate_e4_pair.py
```

脚本接受`--repo`/`--output`或`--directory`，无需本机绝对路径。`--extract`不会覆盖已恢复的私有扩展查询计划，`--replay`对已有(id,name,query,top_k)续跑跳过；所有诊断查询仍可追溯。

公开文件：`group-a-public-statistics.json`、`bailian-group-a-public-statistics.json`、本稿、E4来源证明/真实pair结果及六个Python脚本。私有附件：三题历史original/timeline JSON和中文MD、新百炼original/audit JSON、query-plan、72次重放、5次post-hoc定位、完整相关文档与邻接片段、条件证据窗口、case notes和`private-evidence-manifest.json`。API/assistant/tool事件覆盖由导出脚本逐题自动核对，无缺失。

历史三题均是模型直接选择空答，非协议拒绝或引用校验抹去答案；百炼本组三题中两题同样空答、一题为模型直接错答。所有标签只在完成原运行或本次基线后由评测/离线诊断读取，没有进入在线Agent输入。


## 第二类三题逐题复盘（可并入总回传）

公开版仅概述题意和证据坐标，不包含原题全文、原始标签或长篇原文。原题、规范化标签、原始API/工具正文及详细中文叙述均单独保留在private。

旧历史条件：冻结代码 `dab7646158fef729c3bf3e0f37b7f302727fc568`、config `61d7cc3701b2a42a`、官方兼容请求模型名与实际返回模型名有区别。新百炼条件：基线代码 `8c8e545126e329919d2c16b18cacea6e139ebb29`、config `900fc3b95b775d2a`，请求与成功响应均为 `deepseek-v4-flash-0731`。两者是不同运行，不能把相同ID下的证据编号或故障类别直接互换。

以下每张时间线使用原始0起点sequence，列出所有记录事件，因此每一次真实API、模型assistant决策、工具调用都各有一行。完整旧历史共123事件，当前有效百炼三题共116事件；合计239事件、29次API尝试、29次assistant响应、46次工具返回。旧58账户中断的23事件独立保存，不计入这239条有效历史。

| 题目ID | 旧EM | 新百炼EM | 新有效状态 | 新报告token/工具/API |
|---|---:|---:|---|---|
| 231 | 0 | 0 | insufficient_evidence | 9687 / 4 / 3 |
| 390 | 0 | 0 | insufficient_evidence | 23082 / 10 / 6 |
| 58 | 0 | 0 | insufficient_evidence | 19081 / 8 / 5 |

### ID 231

题意：定位一首符合人物经历、出生信息和合作关系的歌曲。

旧历史首次故障：旧raw工具seq8取得E9（doc43835:0，900字符）；state10原样保存。首次不可见发生在context11/request12/api13：E9排第11，整项1114字符但剩938；整个工具组加快照57490字符也超过24000，故两条传递通路均未保留。

语义和评分：片段提供歌曲、合作艺人及出生/星座的强候选，仍需核实帮派年龄和所属专辑；不是仅凭字面命中就已完成题意。旧最终raw/解析/导出均为空答，search_stalled提前收尾，剩24071 token，原EM=0。

新基线：新百炼3次HTTP200、4工具、9687 token，仍为空答、EM=0。此新检索未取得旧目标片段或参考串，故首缺口已是检索；历史保留hook对未观察到的目标空操作。

旧运行逐事件时间线：

| seq | 秒 | 事件 | 观察到的动作或状态 |
|---:|---:|---|---|
| 0 | 0.000106 | run_start | run_start |
| 1 | 0.000192 | user | 原始问题输入（公开省略） |
| 2 | 0.007660 | skill_selected | skill_selected |
| 3 | 0.007815 | skill_loaded | 自动加载过程指引：multi-clue-decomposition |
| 4 | 0.007904 | context | 选中0；丢工具组0；字符3972 |
| 5 | 0.008520 | request | 字符=3972；选中[]；full state目标=[]；真实request目标=[]；API seq6 |
| 6 | 1.428747 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 1610, "completion_tokens": 134, "total_tokens": 1744, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 202}；目标可见=[] |
| 7 | 1.428785 | assistant | 模型决定调用2个工具 |
| 8 | 3.341592 | tool | search；成功=True；返回10片段；IDs=E1,E2,E3,E4,E5,E6,E7,E8,E9,E10；待核实目标=E9 |
| 9 | 6.648922 | tool | search；成功=True；返回10片段；IDs=E11,E12,E13,E14,E15,E16,E17,E18,E19,E20；待核实目标=无 |
| 10 | 6.649114 | state | 完整state共20段；目标=['E9']；steps=1；tools=2；tokens=1744；stalled=0 |
| 11 | 6.649895 | context | 选中8；丢工具组1；字符13254 |
| 12 | 6.650854 | request | 字符=13254；选中['E6', 'E18', 'E13', 'E14', 'E3', 'E1', 'E17', 'E19']；full state目标=['E9']；真实request目标=[]；API seq13 |
| 13 | 8.104784 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4036, "completion_tokens": 149, "total_tokens": 4185, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2628}；目标可见=[] |
| 14 | 8.104817 | assistant | 模型决定调用2个工具 |
| 15 | 10.002271 | tool | search；成功=True；返回10片段；IDs=E1,E2,E3,E4,E5,E6,E7,E8,E9,E10；待核实目标=E9 |
| 16 | 12.083604 | tool | search；成功=True；返回10片段；IDs=E11,E12,E13,E14,E15,E16,E17,E18,E19,E20；待核实目标=无 |
| 17 | 12.083721 | state | 完整state共20段；目标=['E9']；steps=2；tools=4；tokens=5929；stalled=2 |
| 18 | 12.083729 | skill_selected | skill_selected |
| 19 | 12.083971 | skill_loaded | 自动加载过程指引：search-recovery |
| 20 | 12.084789 | finalization | search_stalled；剩余报告token=24071 |
| 21 | 12.084795 | context | 选中8；丢工具组2；字符14855 |
| 22 | 12.085547 | request | 字符=14855；选中['E6', 'E18', 'E13', 'E14', 'E3', 'E1', 'E17', 'E19']；full state目标=['E9']；真实request目标=[]；API seq23 |
| 23 | 13.446703 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=none；usage={"prompt_tokens": 3506, "completion_tokens": 107, "total_tokens": 3613, "prompt_tokens_details": {"cached_tokens": 640}, "prompt_cache_hit_tokens": 640, "prompt_cache_miss_tokens": 2866}；目标可见=[] |
| 24 | 13.446732 | assistant | 模型原始final为空答 |
| 25 | 13.446782 | answer | 解析后answer为空，与API原始final一致 |
| 26 | 13.446966 | run_end | insufficient_evidence；usage_complete=True；eligible=False |

新百炼有效运行逐事件时间线：

| seq | 秒 | 事件 | 实际记录 |
|---:|---:|---|---|
| 0 | 0.000125 | run_start | run_start |
| 1 | 0.000137 | user | user |
| 2 | 0.011859 | skill_selected | skill_selected |
| 3 | 0.012169 | skill_loaded | skill_loaded |
| 4 | 0.012350 | context | 保留0片段；丢0工具组；3972字符 |
| 5 | 0.013839 | request | 构造请求，0可见片段；以随后的api_attempt为实际发送证据 |
| 6 | 2.739744 | api_attempt | HTTP200，context seq4，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 1618, 'completion_tokens': 218, 'total_tokens': 1836, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 7 | 2.739779 | assistant | 模型决定调用2个工具 |
| 8 | 3.656122 | tool | search，ok=True，片段=5，目标IDs=[] |
| 9 | 4.335823 | tool | search，ok=True，片段=5，目标IDs=[] |
| 10 | 4.335965 | state | {"evidence_count": 10, "target_ids": [], "steps": 1, "tools": 2, "tokens": 1836, "stalled": 0} |
| 11 | 4.336592 | context | 保留8片段；丢1工具组；13487字符 |
| 12 | 4.337606 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 13 | 5.742281 | api_attempt | HTTP200，context seq11，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4262, 'completion_tokens': 93, 'total_tokens': 4355, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 14 | 5.742314 | assistant | 模型决定调用2个工具 |
| 15 | 6.483963 | tool | search，ok=True，片段=5，目标IDs=[] |
| 16 | 7.048091 | tool | search，ok=True，片段=5，目标IDs=[] |
| 17 | 7.048213 | state | {"evidence_count": 10, "target_ids": [], "steps": 2, "tools": 4, "tokens": 6191, "stalled": 2} |
| 18 | 7.048232 | skill_selected | skill_selected |
| 19 | 7.048555 | skill_loaded | skill_loaded |
| 20 | 7.049203 | finalization | search_stalled；余23809 token |
| 21 | 7.049211 | context | 保留7片段；丢2工具组；13947字符 |
| 22 | 7.050210 | request | 构造请求，7可见片段；以随后的api_attempt为实际发送证据 |
| 23 | 8.746300 | api_attempt | HTTP200，context seq21，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 3386, 'completion_tokens': 110, 'total_tokens': 3496, 'prompt_tokens_details': {'cached_tokens': 768}} |
| 24 | 8.746352 | assistant | 模型原始final为空答 |
| 25 | 8.746394 | answer | 解析后的空答，与原始模型final相同 |
| 26 | 8.746562 | run_end | insufficient_evidence；usage_complete=True |

历史最终请求的单变量成对诊断：

同24000字符总上限、23600选择器上限及1024输出token；control 14855字符，treatment 14931字符。条件 `observed-span-diagnostic`，参考辅助=True；仅改变state快照中的证据排序/选择，新增可见IDs=['E9']，移出IDs=['E19']。所有片段都是该题旧轨迹已成功观察的原文，未增加标签或新检索。

### ID 390

题意：从区域合辑、文章线索和艺人生平共同定位该合辑的第三首曲目。

旧历史首次故障：旧seq29取得E43（doc3282:750，476字符）；state31完整保存。context32/request33/api34首次不可见：E43排第36，整项741字符但剩651；工具组加快照57293字符超24000。更早E6人物证据曾在api13/api20可见、seq14被模型明确认出，从context25起被挤掉。

语义和评分：讣闻只给出艺人的代表作，未给合辑和第三轨对应关系。保留该片段只能恢复候选，不能证明歌名语义正确。旧最终raw/解析/导出均为空答，search_stalled时余11538 token，原EM=0。

新基线：新百炼6次HTTP200、10工具、23082 token，仍为空答、EM=0。新E15（同doc:offset）已经在API seq36和44可见；另有同名CD/重录片段，仍不是所问合辑。最终缺口是合辑与轨次的关联证据，不能再以“模型没见歌名”解释这一新结果。

旧运行逐事件时间线：

| seq | 秒 | 事件 | 观察到的动作或状态 |
|---:|---:|---|---|
| 0 | 0.000099 | run_start | run_start |
| 1 | 0.000113 | user | 原始问题输入（公开省略） |
| 2 | 0.009181 | skill_selected | skill_selected |
| 3 | 0.009377 | skill_loaded | 自动加载过程指引：multi-clue-decomposition |
| 4 | 0.009477 | context | 选中0；丢工具组0；字符4230 |
| 5 | 0.010019 | request | 字符=4230；选中[]；full state目标=[]；真实request目标=[]；API seq6 |
| 6 | 1.325951 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 1647, "completion_tokens": 123, "total_tokens": 1770, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 239}；目标可见=[] |
| 7 | 1.325984 | assistant | 模型决定调用2个工具 |
| 8 | 1.539369 | tool | search；成功=True；返回10片段；IDs=E1,E2,E3,E4,E5,E6,E7,E8,E9,E10；待核实目标=无 |
| 9 | 1.612413 | tool | search；成功=True；返回10片段；IDs=E11,E12,E13,E14,E15,E16,E17,E18,E19,E20；待核实目标=无 |
| 10 | 1.612532 | state | 完整state共20段；目标=[]；steps=1；tools=2；tokens=1770；stalled=0 |
| 11 | 1.613241 | context | 选中8；丢工具组1；字符13444 |
| 12 | 1.613891 | request | 字符=13444；选中['E8', 'E1', 'E2', 'E4', 'E6', 'E11', 'E5', 'E7']；full state目标=[]；真实request目标=[]；API seq13 |
| 13 | 3.058114 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4028, "completion_tokens": 162, "total_tokens": 4190, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2620}；目标可见=[] |
| 14 | 3.058151 | assistant | 模型决定调用2个工具 |
| 15 | 3.256960 | tool | search；成功=True；返回10片段；IDs=E21,E22,E23,E24,E6,E25,E26,E27,E28,E29；待核实目标=无 |
| 16 | 4.436095 | tool | search；成功=True；返回10片段；IDs=E25,E22,E23,E21,E30,E31,E32,E26,E33,E34；待核实目标=无 |
| 17 | 4.436433 | state | 完整state共34段；目标=[]；steps=2；tools=4；tokens=5960；stalled=0 |
| 18 | 4.437959 | context | 选中8；丢工具组2；字符13713 |
| 19 | 4.438938 | request | 字符=13713；选中['E8', 'E25', 'E30', 'E32', 'E1', 'E2', 'E4', 'E6']；full state目标=[]；真实request目标=[]；API seq20 |
| 20 | 5.849897 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4046, "completion_tokens": 142, "total_tokens": 4188, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2638}；目标可见=[] |
| 21 | 5.849936 | assistant | 模型决定调用2个工具 |
| 22 | 5.995776 | tool | search；成功=True；返回5片段；IDs=E6,E35,E36,E37,E38；待核实目标=无 |
| 23 | 6.357916 | tool | search；成功=True；返回5片段；IDs=E22,E23,E21,E39,E25；待核实目标=无 |
| 24 | 6.358128 | state | 完整state共39段；目标=[]；steps=3；tools=6；tokens=10148；stalled=0 |
| 25 | 6.359385 | context | 选中8；丢工具组3；字符13683 |
| 26 | 6.360022 | request | 字符=13683；选中['E8', 'E25', 'E30', 'E32', 'E36', 'E1', 'E2', 'E4']；full state目标=[]；真实request目标=[]；API seq27 |
| 27 | 7.660943 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4026, "completion_tokens": 131, "total_tokens": 4157, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2618}；目标可见=[] |
| 28 | 7.660979 | assistant | 模型决定调用2个工具 |
| 29 | 7.798217 | tool | search；成功=True；返回10片段；IDs=E6,E35,E36,E37,E38,E40,E41,E42,E43,E44；待核实目标=E43 |
| 30 | 8.128296 | tool | search；成功=True；返回10片段；IDs=E22,E23,E21,E39,E25,E26,E27,E30,E3,E45；待核实目标=无 |
| 31 | 8.128523 | state | 完整state共45段；目标=['E43']；steps=4；tools=8；tokens=14305；stalled=0 |
| 32 | 8.130008 | context | 选中8；丢工具组4；字符13684 |
| 33 | 8.130990 | request | 字符=13684；选中['E8', 'E25', 'E30', 'E32', 'E36', 'E1', 'E2', 'E4']；full state目标=['E43']；真实request目标=[]；API seq34 |
| 34 | 9.585298 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4026, "completion_tokens": 131, "total_tokens": 4157, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2618}；目标可见=[] |
| 35 | 9.585358 | assistant | 模型决定调用2个工具 |
| 36 | 9.702996 | tool | search；成功=True；返回10片段；IDs=E6,E35,E36,E37,E38,E40,E41,E42,E43,E44；待核实目标=E43 |
| 37 | 10.022914 | tool | search；成功=True；返回10片段；IDs=E22,E23,E21,E39,E25,E26,E27,E30,E3,E45；待核实目标=无 |
| 38 | 10.023182 | state | 完整state共45段；目标=['E43']；steps=5；tools=10；tokens=18462；stalled=2 |
| 39 | 10.023196 | skill_selected | skill_selected |
| 40 | 10.023475 | skill_loaded | 自动加载过程指引：search-recovery |
| 41 | 10.024798 | finalization | search_stalled；剩余报告token=11538 |
| 42 | 10.024806 | context | 选中8；丢工具组5；字符14923 |
| 43 | 10.025519 | request | 字符=14923；选中['E8', 'E25', 'E30', 'E32', 'E36', 'E1', 'E2', 'E31']；full state目标=['E43']；真实request目标=[]；API seq44 |
| 44 | 11.618550 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=none；usage={"prompt_tokens": 3390, "completion_tokens": 84, "total_tokens": 3474, "prompt_tokens_details": {"cached_tokens": 640}, "prompt_cache_hit_tokens": 640, "prompt_cache_miss_tokens": 2750}；目标可见=[] |
| 45 | 11.618575 | assistant | 模型原始final为空答 |
| 46 | 11.618616 | answer | 解析后answer为空，与API原始final一致 |
| 47 | 11.618890 | run_end | insufficient_evidence；usage_complete=True；eligible=False |

新百炼有效运行逐事件时间线：

| seq | 秒 | 事件 | 实际记录 |
|---:|---:|---|---|
| 0 | 0.000139 | run_start | run_start |
| 1 | 0.000156 | user | user |
| 2 | 0.010538 | skill_selected | skill_selected |
| 3 | 0.010795 | skill_loaded | skill_loaded |
| 4 | 0.010923 | context | 保留0片段；丢0工具组；4230字符 |
| 5 | 0.011850 | request | 构造请求，0可见片段；以随后的api_attempt为实际发送证据 |
| 6 | 2.305976 | api_attempt | HTTP200，context seq4，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 1655, 'completion_tokens': 221, 'total_tokens': 1876, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 7 | 2.306111 | assistant | 模型决定调用2个工具 |
| 8 | 2.602011 | tool | search，ok=True，片段=5，目标IDs=[] |
| 9 | 2.755452 | tool | search，ok=True，片段=5，目标IDs=[] |
| 10 | 2.755546 | state | {"evidence_count": 10, "target_ids": [], "steps": 1, "tools": 2, "tokens": 1876, "stalled": 0} |
| 11 | 2.756140 | context | 保留8片段；丢1工具组；13563字符 |
| 12 | 2.757181 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 13 | 5.451946 | api_attempt | HTTP200，context seq11，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4019, 'completion_tokens': 287, 'total_tokens': 4306, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 14 | 5.451990 | assistant | 模型决定调用2个工具 |
| 15 | 5.586889 | tool | search，ok=True，片段=5，目标IDs=[] |
| 16 | 5.741736 | tool | search，ok=True，片段=5，目标IDs=['E15'] |
| 17 | 5.741850 | state | {"evidence_count": 16, "target_ids": ["E15"], "steps": 2, "tools": 4, "tokens": 6182, "stalled": 0} |
| 18 | 5.742727 | context | 保留8片段；丢2工具组；13775字符 |
| 19 | 5.743406 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 20 | 8.285486 | api_attempt | HTTP200，context seq18，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4114, 'completion_tokens': 238, 'total_tokens': 4352, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 21 | 8.285521 | assistant | 模型决定调用2个工具 |
| 22 | 8.393911 | tool | search，ok=True，片段=5，目标IDs=[] |
| 23 | 8.556810 | tool | search，ok=True，片段=5，目标IDs=['E18'] |
| 24 | 8.556941 | state | {"evidence_count": 20, "target_ids": ["E15", "E18"], "steps": 3, "tools": 6, "tokens": 10534, "stalled": 0} |
| 25 | 8.557733 | context | 保留8片段；丢3工具组；13757字符 |
| 26 | 8.558447 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 27 | 11.496851 | api_attempt | HTTP200，context seq25，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4128, 'completion_tokens': 256, 'total_tokens': 4384, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 28 | 11.496884 | assistant | 模型决定调用2个工具 |
| 29 | 11.757809 | tool | search，ok=True，片段=5，目标IDs=[] |
| 30 | 11.898466 | tool | search，ok=True，片段=5，目标IDs=['E15'] |
| 31 | 11.898596 | state | {"evidence_count": 21, "target_ids": ["E15", "E18"], "steps": 4, "tools": 8, "tokens": 14918, "stalled": 1} |
| 32 | 11.898606 | skill_selected | skill_selected |
| 33 | 11.898898 | skill_loaded | skill_loaded |
| 34 | 11.899905 | context | 保留8片段；丢4工具组；14757字符 |
| 35 | 11.900794 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 36 | 14.573274 | api_attempt | HTTP200，context seq34，实际可见目标=[{'evidence_id': 'E15', 'doc_id': '3282', 'offset': 750}]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4300, 'completion_tokens': 275, 'total_tokens': 4575, 'prompt_tokens_details': {'cached_tokens': 1536}} |
| 37 | 14.573302 | assistant | 模型决定调用2个工具 |
| 38 | 14.678818 | tool | search，ok=True，片段=5，目标IDs=['E15'] |
| 39 | 14.918164 | tool | search，ok=True，片段=5，目标IDs=[] |
| 40 | 14.918294 | state | {"evidence_count": 24, "target_ids": ["E15", "E18"], "steps": 5, "tools": 10, "tokens": 19493, "stalled": 0} |
| 41 | 14.919051 | finalization | reserve_final_usage；余10507 token |
| 42 | 14.919056 | context | 保留8片段；丢5工具组；14901字符 |
| 43 | 14.919564 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 44 | 16.447082 | api_attempt | HTTP200，context seq42，实际可见目标=[{'evidence_id': 'E15', 'doc_id': '3282', 'offset': 750}]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 3497, 'completion_tokens': 92, 'total_tokens': 3589, 'prompt_tokens_details': {'cached_tokens': 768}} |
| 45 | 16.447130 | assistant | 模型原始final为空答 |
| 46 | 16.447182 | answer | 解析后的空答，与原始模型final相同 |
| 47 | 16.447427 | run_end | insufficient_evidence；usage_complete=True |

历史最终请求的单变量成对诊断：

同24000字符总上限、23600选择器上限及1024输出token；control 14923字符，treatment 14900字符。条件 `observed-span-diagnostic`，参考辅助=True；仅改变state快照中的证据排序/选择，新增可见IDs=['E43']，移出IDs=['E31']。所有片段都是该题旧轨迹已成功观察的原文，未增加标签或新检索。

### ID 58

题意：识别给定论文，并提取其致谢中用于资助的奖项名称。

旧历史首次故障：旧seq23取得E30（doc28406:38250，900字符）直接资助段；state24完整，context25/request26/api27排第14，1075字符大于剩432而遗漏。seq39文内查找再取E37（同doc:38806，410字符），state40完整；最终context42/request43/api44时整项552字符仅比剩549多3仍整项不选，工具组加快照26951又超收尾23600。

语义和评分：该奖项属于已识别论文的直接致谢记录；论文元数据时间与元素外部事实需单独谨慎核对，但不是只有同名词的无关命中。旧最终raw/解析/导出均为空答，reserve_final_usage在余10530 token时触发，原EM=0。

新基线：充值后新百炼5次HTTP200、8次search、19081 token，seq34 search_stalled（余14475）→seq37最终API→seq38明确空答，EM=0。新运行只命中同doc的参考文献尾段，未取得旧奖项窗口，也未open/find；首缺口在检索/论文定位。先前HTTP400 Arrearage的失败尝试另存attempt-0，不能和这次有效弃答混为一条记录。

旧运行逐事件时间线：

| seq | 秒 | 事件 | 观察到的动作或状态 |
|---:|---:|---|---|
| 0 | 0.000102 | run_start | run_start |
| 1 | 0.000109 | user | 原始问题输入（公开省略） |
| 2 | 0.009116 | skill_selected | skill_selected |
| 3 | 0.009473 | skill_loaded | 自动加载过程指引：multi-clue-decomposition |
| 4 | 0.009643 | context | 选中0；丢工具组0；字符4318 |
| 5 | 0.010458 | request | 字符=4318；选中[]；full state目标=[]；真实request目标=[]；API seq6 |
| 6 | 1.130300 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 1653, "completion_tokens": 141, "total_tokens": 1794, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 245}；目标可见=[] |
| 7 | 1.130331 | assistant | 模型决定调用2个工具 |
| 8 | 1.568481 | tool | search；成功=True；返回10片段；IDs=E1,E2,E3,E4,E5,E6,E7,E8,E9,E10；待核实目标=无 |
| 9 | 1.926164 | tool | search；成功=True；返回10片段；IDs=E11,E12,E13,E14,E1,E15,E16,E17,E2,E8；待核实目标=无 |
| 10 | 1.926276 | state | 完整state共17段；目标=[]；steps=1；tools=2；tokens=1794；stalled=0 |
| 11 | 1.926971 | context | 选中8；丢工具组1；字符13721 |
| 12 | 1.927783 | request | 字符=13721；选中['E1', 'E12', 'E2', 'E6', 'E7', 'E11', 'E8', 'E9']；full state目标=[]；真实request目标=[]；API seq13 |
| 13 | 3.311023 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4247, "completion_tokens": 142, "total_tokens": 4389, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2839}；目标可见=[] |
| 14 | 3.311058 | assistant | 模型决定调用2个工具 |
| 15 | 3.620690 | tool | search；成功=True；返回10片段；IDs=E18,E5,E19,E1,E20,E21,E22,E8,E16,E23；待核实目标=无 |
| 16 | 3.800809 | tool | search；成功=True；返回10片段；IDs=E18,E22,E24,E2,E21,E7,E25,E26,E27,E28；待核实目标=无 |
| 17 | 3.800960 | state | 完整state共28段；目标=[]；steps=2；tools=4；tokens=6183；stalled=0 |
| 18 | 3.801900 | context | 选中8；丢工具组2；字符13866 |
| 19 | 3.802560 | request | 字符=13866；选中['E1', 'E12', 'E2', 'E6', 'E7', 'E11', 'E25', 'E8']；full state目标=[]；真实request目标=[]；API seq20 |
| 20 | 5.439528 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4257, "completion_tokens": 183, "total_tokens": 4440, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2849}；目标可见=[] |
| 21 | 5.439560 | assistant | 模型决定调用2个工具 |
| 22 | 5.598475 | tool | search；成功=True；返回10片段；IDs=E18,E2,E22,E24,E21,E25,E7,E29,E16,E20；待核实目标=无 |
| 23 | 5.811217 | tool | search；成功=True；返回10片段；IDs=E30,E2,E31,E24,E18,E32,E33,E34,E35,E36；待核实目标=E30 |
| 24 | 5.811417 | state | 完整state共36段；目标=['E30']；steps=3；tools=6；tokens=10623；stalled=0 |
| 25 | 5.812461 | context | 选中8；丢工具组3；字符13908 |
| 26 | 5.813042 | request | 字符=13908；选中['E1', 'E12', 'E2', 'E6', 'E7', 'E11', 'E25', 'E33']；full state目标=['E30']；真实request目标=[]；API seq27 |
| 27 | 7.574640 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4260, "completion_tokens": 203, "total_tokens": 4463, "prompt_tokens_details": {"cached_tokens": 1408}, "prompt_cache_hit_tokens": 1408, "prompt_cache_miss_tokens": 2852}；目标可见=[] |
| 28 | 7.574670 | assistant | 模型决定调用2个工具 |
| 29 | 7.787074 | tool | search；成功=True；返回10片段；IDs=E18,E22,E2,E24,E21,E25,E7,E29,E16,E20；待核实目标=无 |
| 30 | 7.787471 | tool | find_in_document；成功=True；返回0片段；IDs=；待核实目标=无 |
| 31 | 7.787647 | state | 完整state共36段；目标=['E30']；steps=4；tools=8；tokens=15086；stalled=1 |
| 32 | 7.787655 | skill_selected | skill_selected |
| 33 | 7.787893 | skill_loaded | 自动加载过程指引：search-recovery |
| 34 | 7.788883 | context | 选中7；丢工具组4；字符14193 |
| 35 | 7.789518 | request | 字符=14193；选中['E1', 'E12', 'E2', 'E6', 'E7', 'E11', 'E25']；full state目标=['E30']；真实request目标=[]；API seq36 |
| 36 | 9.340528 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=auto；usage={"prompt_tokens": 4241, "completion_tokens": 143, "total_tokens": 4384, "prompt_tokens_details": {"cached_tokens": 1536}, "prompt_cache_hit_tokens": 1536, "prompt_cache_miss_tokens": 2705}；目标可见=[] |
| 37 | 9.340560 | assistant | 模型决定调用2个工具 |
| 38 | 9.449876 | tool | search；成功=True；返回5片段；IDs=E18,E2,E22,E21,E24；待核实目标=无 |
| 39 | 9.450205 | tool | find_in_document；成功=True；返回1片段；IDs=E37；待核实目标=E37 |
| 40 | 9.450384 | state | 完整state共37段；目标=['E30', 'E37']；steps=5；tools=10；tokens=19470；stalled=2 |
| 41 | 9.451347 | finalization | reserve_final_usage；剩余报告token=10530 |
| 42 | 9.451352 | context | 选中7；丢工具组5；字符14477 |
| 43 | 9.451933 | request | 字符=14477；选中['E1', 'E12', 'E2', 'E6', 'E7', 'E11', 'E25']；full state目标=['E30', 'E37']；真实request目标=[]；API seq44 |
| 44 | 10.333963 | api_attempt | HTTP=200；deepseek-v4-flash→deepseek-flash；tool_choice=none；usage={"prompt_tokens": 3473, "completion_tokens": 75, "total_tokens": 3548, "prompt_tokens_details": {"cached_tokens": 640}, "prompt_cache_hit_tokens": 640, "prompt_cache_miss_tokens": 2833}；目标可见=[] |
| 45 | 10.333985 | assistant | 模型原始final为空答 |
| 46 | 10.334020 | answer | 解析后answer为空，与API原始final一致 |
| 47 | 10.334255 | run_end | insufficient_evidence；usage_complete=True；eligible=False |

新百炼有效运行逐事件时间线：

| seq | 秒 | 事件 | 实际记录 |
|---:|---:|---|---|
| 0 | 0.000146 | run_start | run_start |
| 1 | 0.000154 | user | user |
| 2 | 0.074815 | skill_selected | skill_selected |
| 3 | 0.075192 | skill_loaded | skill_loaded |
| 4 | 0.075382 | context | 保留0片段；丢0工具组；4318字符 |
| 5 | 0.078617 | request | 构造请求，0可见片段；以随后的api_attempt为实际发送证据 |
| 6 | 3.021036 | api_attempt | HTTP200，context seq4，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 1661, 'completion_tokens': 279, 'total_tokens': 1940, 'prompt_tokens_details': {'cached_tokens': 0}} |
| 7 | 3.021135 | assistant | 模型决定调用2个工具 |
| 8 | 5.985086 | tool | search，ok=True，片段=5，目标IDs=[] |
| 9 | 6.422182 | tool | search，ok=True，片段=5，目标IDs=[] |
| 10 | 6.422263 | state | {"evidence_count": 9, "target_ids": [], "steps": 1, "tools": 2, "tokens": 1940, "stalled": 0} |
| 11 | 6.422794 | context | 保留8片段；丢1工具组；13597字符 |
| 12 | 6.423835 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 13 | 9.563942 | api_attempt | HTTP200，context seq11，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4237, 'completion_tokens': 309, 'total_tokens': 4546, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 14 | 9.563977 | assistant | 模型决定调用2个工具 |
| 15 | 9.845939 | tool | search，ok=True，片段=5，目标IDs=[] |
| 16 | 10.037530 | tool | search，ok=True，片段=5，目标IDs=[] |
| 17 | 10.037685 | state | {"evidence_count": 16, "target_ids": [], "steps": 2, "tools": 4, "tokens": 6486, "stalled": 0} |
| 18 | 10.038771 | context | 保留8片段；丢2工具组；13667字符 |
| 19 | 10.040155 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 20 | 12.338978 | api_attempt | HTTP200，context seq18，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4326, 'completion_tokens': 191, 'total_tokens': 4517, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 21 | 12.339015 | assistant | 模型决定调用2个工具 |
| 22 | 12.586852 | tool | search，ok=True，片段=5，目标IDs=[] |
| 23 | 12.887128 | tool | search，ok=True，片段=5，目标IDs=[] |
| 24 | 12.887234 | state | {"evidence_count": 17, "target_ids": [], "steps": 3, "tools": 6, "tokens": 11003, "stalled": 0} |
| 25 | 12.887964 | context | 保留8片段；丢3工具组；13719字符 |
| 26 | 12.888805 | request | 构造请求，8可见片段；以随后的api_attempt为实际发送证据 |
| 27 | 14.958008 | api_attempt | HTTP200，context seq25，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 4329, 'completion_tokens': 193, 'total_tokens': 4522, 'prompt_tokens_details': {'cached_tokens': 1280}} |
| 28 | 14.958040 | assistant | 模型决定调用2个工具 |
| 29 | 15.192331 | tool | search，ok=True，片段=5，目标IDs=[] |
| 30 | 15.452625 | tool | search，ok=True，片段=5，目标IDs=[] |
| 31 | 15.452758 | state | {"evidence_count": 17, "target_ids": [], "steps": 4, "tools": 8, "tokens": 15525, "stalled": 2} |
| 32 | 15.452772 | skill_selected | skill_selected |
| 33 | 15.454625 | skill_loaded | skill_loaded |
| 34 | 15.455303 | finalization | search_stalled；余14475 token |
| 35 | 15.455310 | context | 保留7片段；丢4工具组；14180字符 |
| 36 | 15.455967 | request | 构造请求，7可见片段；以随后的api_attempt为实际发送证据 |
| 37 | 17.226976 | api_attempt | HTTP200，context seq35，实际可见目标=[]，error=None，response_model=deepseek-v4-flash-0731，usage={'prompt_tokens': 3478, 'completion_tokens': 78, 'total_tokens': 3556, 'prompt_tokens_details': {'cached_tokens': 512}} |
| 38 | 17.227013 | assistant | 模型原始final为空答 |
| 39 | 17.227145 | answer | 解析后的空答，与原始模型final相同 |
| 40 | 17.227411 | run_end | insufficient_evidence；usage_complete=True |

历史最终请求的单变量成对诊断：

同24000字符总上限、23600选择器上限及1024输出token；control 14477字符，treatment 15056字符。条件 `focused-tool-first`，参考辅助=False；仅改变state快照中的证据排序/选择，新增可见IDs=['E33', 'E37']，移出IDs=['E25']。所有片段都是该题旧轨迹已成功观察的原文，未增加标签或新检索。

### 共性结论与验证范围

旧运行的字面证据确实完整到达内部state，随后因快照配额、整项跳过和整组历史删除而对模型不可见；15个原请求已逐条重放，与真实api_attempt.request.messages全等。两种hook在30个离线对照构造上也完全一致。此处的“成功”只指证据进入构造请求，不能当作模型回答成功。

通用对照的边界已实际检查：聚焦open/find窗口优先只恢复旧58最后一次定位片段；每doc最高词重合片段优先也仅在旧58最后阶段恢复短窗口，对旧231/390无效。新百炼231和58未取得相同目标，390最后已看到歌名，因此历史保留实验不能被包装成对三个新完整运行的统一修复。

成对实时诊断需另存双方实际百炼请求/响应，并在相同提供商映射后比较。引用核验使用原成功工具历史、该臂真实messages、原state及只读语料；分别记录raw final、解析/导出、引用有效性、规范化EM和语义核验。来源通过不代表满足全部题意，尤其390还必须确认合辑第三轨。前文EM表只统计完整旧/新基线；下文单列已完成的成对API结果，不能混入盲测基线得分。

可复现文件：`group-b-replay-summary.json`、`bailian-addendum.json`、`verification-result.json`、`ARTIFACT_HASHES.json`；成对输入及核验方法在`../paired-final-diagnostics/README.md`。私密原始记录和payload不随本公开正文展开。


### 历史最终轮次的真实API成对结果

在上述239个原始轨迹事件之外，本节另列6个真实诊断API记录及6个对应assistant响应字段，共12行；没有为它们伪造历史sequence，也没有新工具调用。

## 历史最终轮次：三组成对API结果

以下6次真实调用由root执行，本脚本仅做离线核验。两臂均百炼0731、thinking关闭、temperature0、工具禁用、max_tokens1024、总上下文上限24000；实际发送请求除messages[1]中的证据选择之外逐字段相同。每个响应都在独立进程中使用OLD冻结解析器与只读语料验证。

| ID | 条件 | control → treatment EM | schema/引用 | 语义结论 |
|---|---|---|---|---|
| 231 | observed-span-diagnostic；参考辅助=True | 0 → 0 | 两臂schema通过；两臂空答，无非空引用待核验 | control沿用错误出生月份的人物候选并称没有歌曲桥接；treatment明确认出正确出生/星座及合作歌曲候选，说明E9确已被理解，但仍指出缺入帮年龄及专辑/发行关系，最终answer保持空串。候选识别改善，没有达到EM或全部约束通过；不能把explanation中出现候选名计为answer正确。 |
| 390 | observed-span-diagnostic；参考辅助=True | 0 → 0 | 两臂schema通过；两臂空答，无非空引用待核验 | control缺合辑及人物关联；treatment明确引用E43的人物死亡线索，但仍指出未把该人物或代表作连接到所问合辑和第三轨。讣闻中的字面歌名没有补上轨次关系，空答符合现有语义证据缺口；不应通过要求模型放宽断言来制造EM提升。 |
| 58 | focused-tool-first；参考辅助=False | 0 → 1 | 两臂schema通过；非空答案E37来源/可见/原文坐标通过 | control已识别论文，但表示未见致谢奖项而空答；treatment给出奖项答案并选择E37，冻结引用门控核对原成功find结果、真实请求可见性、SQLite原文/坐标/URL均通过，规范化EM由0变1。该奖项在同论文Funding段直接出现，语义支持充分。此结果支持旧观察集合下的上下文保留政策影响最终回答；新百炼完整运行未取到该段的问题仍未被解决。treatment因同一装箱排序变化也增加E33并移出E25，不能描述成只多了一句话，也未单独排除其他片段交互。 |

空答通过schema不意味着完成了引用证明：冻结程序对空answer直接返回insufficient_evidence；只有58 treatment的非空回答实际经过ID来源、历史可见性和语料原文核验。也没有JSON解析后误删答案：6臂raw answer与解析后保存结果逐字一致。成对实验仅调用最终一轮并验证响应，未执行完整batch预测导出链，不能声称该导出链也在此实验中复测。

单变量是保留政策；58同时因容量重排加入E33、E37并移出E25，记录如实保留。结果支持这一次旧观察集合下的可见性改动有效，不能据此宣称新百炼完整运行、其他题或一般正确率已改善。231/390 treatment的explanation虽识别了更好的候选，answer仍空，EM不能因此算1。

以下是6个API事件及对应6个assistant响应字段，位置来自实际诊断记录；不是伪造的历史sequence。诊断过程无新工具调用。

| 记录位置 | 类型 | 可公开观察 |
|---|---|---|
| 231/control/api_attempt | API | HTTP200；输入14855字符；模型0731；usage={"prompt_tokens": 3504, "completion_tokens": 98, "total_tokens": 3602, "prompt_tokens_details": {"cached_tokens": 768}}；实际request SHA=7f6392ea985df3942e287cba40ff73d5357fa88f99006872f398a8b800346342 |
| 231/control/response.choices[0].message | assistant | 原始空答；schema通过；citation=not_required_for_empty_answer；EM=0；引用IDs=[]；finish_reason=stop |
| 231/treatment/api_attempt | API | HTTP200；输入14931字符；模型0731；usage={"prompt_tokens": 3552, "completion_tokens": 128, "total_tokens": 3680, "prompt_tokens_details": {"cached_tokens": 768}}；实际request SHA=b7c5f67273699cf3137d46227daec256bf440b8e3d7ac6afc18579b3cfe6e53e |
| 231/treatment/response.choices[0].message | assistant | 原始空答；schema通过；citation=not_required_for_empty_answer；EM=0；引用IDs=[]；finish_reason=stop |
| 390/control/api_attempt | API | HTTP200；输入14923字符；模型0731；usage={"prompt_tokens": 3388, "completion_tokens": 78, "total_tokens": 3466, "prompt_tokens_details": {"cached_tokens": 768}}；实际request SHA=35ebb89d3f05fdd70ee7dd0d16aadd7f2f75cf1756b745efd245fdb4fe278ae9 |
| 390/control/response.choices[0].message | assistant | 原始空答；schema通过；citation=not_required_for_empty_answer；EM=0；引用IDs=[]；finish_reason=stop |
| 390/treatment/api_attempt | API | HTTP200；输入14900字符；模型0731；usage={"prompt_tokens": 3412, "completion_tokens": 107, "total_tokens": 3519, "prompt_tokens_details": {"cached_tokens": 768}}；实际request SHA=9c550a35d829f777bf365c761ce8cac4af22a533efb82097bc107d5df4d30e3b |
| 390/treatment/response.choices[0].message | assistant | 原始空答；schema通过；citation=not_required_for_empty_answer；EM=0；引用IDs=[]；finish_reason=stop |
| 58/control/api_attempt | API | HTTP200；输入14477字符；模型0731；usage={"prompt_tokens": 3471, "completion_tokens": 110, "total_tokens": 3581, "prompt_tokens_details": {"cached_tokens": 768}}；实际request SHA=e632436b6dbfc0fc511d3ca96b95cef13eaee1b23ed94e56609bed62659f4cb7 |
| 58/control/response.choices[0].message | assistant | 原始空答；schema通过；citation=not_required_for_empty_answer；EM=0；引用IDs=[]；finish_reason=stop |
| 58/treatment/api_attempt | API | HTTP200；输入15056字符；模型0731；usage={"prompt_tokens": 3580, "completion_tokens": 60, "total_tokens": 3640, "prompt_tokens_details": {"cached_tokens": 1024}}；实际request SHA=aabd681f19509f1d245b3ed6a3ab06985dae6adf12ac9005bf4a09ff5535811c |
| 58/treatment/response.choices[0].message | assistant | 原始非空答案；schema通过；citation=passed_original_observed_visible_and_exact_corpus；EM=1；引用IDs=['E37']；finish_reason=stop |

精确raw final与规范化标签仅见`../paired-final-diagnostics/private/PAIRED_FINAL_RESULTS.md`。公开JSON保留实际请求/响应SHA、用量、证据ID、schema、citation、EM与语义判定，未公开答案和原标签。


## 验证题 1155 逐题复盘

寻找属于指定历史地标的古村落，同时核对建村年代、步道长度、机场空中距离和时间截点。

历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。

### 可证实的结论

候选与步道信息可见，但重复查询触发提前收尾；离线找到年代支持及冲突，机场距离仍未闭环。

首次问题：seq12完整重复首轮两条查询，而seq11已见候选村落和步道片段；seq13–14新增证据均为0，停滞计数升至2。seq18在仍有大量预算时禁用工具收尾。

工具4次（全部search，open/find均0），真实API3次，总usage=8679。收尾前余额：{'tokens': 24555, 'tools': 20, 'steps': 10, 'stalled_searches': 2}。

### 按序时间线

|seq/index|事件|观察及定位|
|---|---|---|
|0|run_start|启动baseline；config_id=61d7cc3701b2a42a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|context|上下文选择；移除历史组0，选证据0，2354字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|3|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|4|api_attempt|真实API#1；HTTP 200；usage=1428；tool_choice=auto；实际messages=2354字符；证据[]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|5|assistant|模型决定发起工具；call_00_xLZyCZEifOCCUVpnVNPz6464:search, call_01_6cYBSp8wA013ccrImtqv5234:search|
|6|tool|search call_00_xLZyCZEifOCCUVpnVNPz6464；query SHA256=8e8706e0debad753，top_k=10；ok=True，返回10，新证据10，完全重复查询=False；#1 46699:25500+900(E1); #2 44164:750+900(E2); #3 56790:0+900(E3); #4 96616:9000+900(E4); #5 90811:0+900(E5); #6 34133:750+900(E6); #7 46699:20250+900(E7); #8 94025:3000+900(E8); #9 3094:435000+900(E9); #10 76909:12000+900(E10)|
|7|tool|search call_01_6cYBSp8wA013ccrImtqv5234；query SHA256=1d0b05d058cdd8ac，top_k=10；ok=True，返回10，新证据9，完全重复查询=False；#1 62625:6750+900(E11); #2 8865:1500+900(E12); #3 8865:2250+900(E13); #4 60896:9750+900(E14); #5 46699:7500+900(E15); #6 78245:63000+900(E16); #7 3094:583500+900(E17); #8 3094:584250+900(E18); #9 46699:25500+900(E1); #10 46699:0+900(E19)|
|8|state|步骤1，工具2，累计token1428，stalled_searches=0；完整state证据数19，candidate_answer仍空。|
|9|context|上下文选择；移除历史组1，选证据9，12773字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|10|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|11|api_attempt|真实API#2；HTTP 200；usage=4017；tool_choice=auto；实际messages=12773字符；证据[E1,E4,E5,E6,E2,E7,E16,E8,E12]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|12|assistant|模型决定发起工具；call_00_lndTvfOpZ6cVGqu0ZWVs4125:search, call_01_QKs6XD3X6N2MQrR7TEg88719:search|
|13|tool|search call_00_lndTvfOpZ6cVGqu0ZWVs4125；query SHA256=8e8706e0debad753，top_k=10；ok=True，返回10，新证据0，完全重复查询=True；#1 46699:25500+900(E1); #2 44164:750+900(E2); #3 56790:0+900(E3); #4 96616:9000+900(E4); #5 90811:0+900(E5); #6 34133:750+900(E6); #7 46699:20250+900(E7); #8 94025:3000+900(E8); #9 3094:435000+900(E9); #10 76909:12000+900(E10)|
|14|tool|search call_01_QKs6XD3X6N2MQrR7TEg88719；query SHA256=1d0b05d058cdd8ac，top_k=10；ok=True，返回10，新证据0，完全重复查询=True；#1 62625:6750+900(E11); #2 8865:1500+900(E12); #3 8865:2250+900(E13); #4 60896:9750+900(E14); #5 46699:7500+900(E15); #6 78245:63000+900(E16); #7 3094:583500+900(E17); #8 3094:584250+900(E18); #9 46699:25500+900(E1); #10 46699:0+900(E19)|
|15|state|步骤2，工具4，累计token5445，stalled_searches=2；完整state证据数19，candidate_answer仍空。|
|16|skill_selected|skill_selected：search-recovery，来源automatic。|
|17|skill_loaded|skill_loaded：search-recovery，来源automatic。|
|18|finalization|进入收尾：search_stalled；剩余已报告token预算=24555；下一请求工具禁用。|
|19|context|上下文选择；移除历史组2，选证据8，13301字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|20|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|21|api_attempt|真实API#3；HTTP 200；usage=3234；tool_choice=none；实际messages=13301字符；证据[E1,E4,E5,E6,E2,E7,E16,E8]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|22|assistant|模型最终决定：原始content中的answer已经为空。|
|23|answer|JSON解析接受原始空answer；supporting_evidence=['E6', 'E2']；空答提前返回，未执行非空答案引用解析。|
|24|run_end|运行结束status=insufficient_evidence；usage_complete=True；导出answer为空。|

条件核查原文只保存在加密私有附件。公开定位：20784:73:208; 34133:1364:1576; 34133:753:922; 34133:984:1056; 62625:2207:2371。

### 下一步单变量与未确认项

只替换第二轮第一条重复查询为历史候选名+缺失年代，其他设置不动；分别测新片段是否召回、是否进入实际请求。机场距离和年代来源冲突若仍未解决，仍可能弃答；没有已证实EM提升。

百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。

<!-- BAILIAN-APPENDIX -->

### 充值后百炼基线对照

百炼本次输出非空，但严格EM仍为0。固定语料把输出候选与参考候选放在不同遗址，未发现可把两者视为拼写或别名的证据。最终引用里的同名步道长度与题意区间不符，机场距离仅以宽泛地区描述代替验证。属于条件未核实的候选输出；解析、引用定位和导出均保留原答。

本次有效运行：配置`900fc3b95b775d2a`，5个HTTP200、8次search、usage总计16671；严格EM=0。没有open/find，所有search使用配置默认top5。

首次问题：seq19重复一条宽泛查询；此前实际seq18已含另一遗址候选及其步道长度。seq36原始回答仍将该候选视为符合全部线索，缺少机场距离支持且忽略步道长度不合。

#### 初次账户错误尝试：全部事件

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|context|上下文选择；移除历史组0，选证据0，2354字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|3|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|4|api_attempt|首请求HTTP400，Arrearage；无模型答题回复，usage_unknown=True。实际输入只认本事件request.messages。|
|5|error|服务商账户错误被记录；没有Agent答题决定。|
|6|run_end|provider_error结束，reported_tokens=0，工具0，EM未测；不与充值后运行拼接。|

#### 充值后有效运行：全部事件

seq为本次轨迹自己的零起算位置，不与历史seq混用。实际模型输入只读取`api_attempt.request.messages`。

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|context|上下文选择；移除历史组0，选证据0，2354字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|3|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|4|api_attempt|真实API#1；HTTP 200；usage=1425；tool_choice=auto；实际messages=2354字符；证据[]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|5|assistant|模型决定发起工具；call_e7dbd780cc884a6b9d78acd1:search, call_0ec79b47398d4803855de3e9:search|
|6|tool|search call_e7dbd780cc884a6b9d78acd1；query SHA256=a8ea7b9879b727d7，top_k=None；ok=True，返回5，新证据5，完全重复查询=False；#1 56790:0+900(E1); #2 44164:750+900(E2); #3 90811:0+900(E3); #4 46699:25500+900(E4); #5 96616:9000+900(E5)|
|7|tool|search call_0ec79b47398d4803855de3e9；query SHA256=e4e0f2ce54cb3b58，top_k=None；ok=True，返回5，新证据5，完全重复查询=False；#1 78676:3750+900(E6); #2 17323:3000+900(E7); #3 88797:16500+900(E8); #4 3094:583500+900(E9); #5 8865:1500+900(E10)|
|8|state|步骤1，工具2，累计token1425，stalled_searches=0；完整state证据数10，candidate_answer仍空。|
|9|context|上下文选择；移除历史组1，选证据9，12679字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|10|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|11|api_attempt|真实API#2；HTTP 200；usage=4008；tool_choice=auto；实际messages=12679字符；证据[E3,E4,E5,E2,E9,E10,E1,E7,E8]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|12|assistant|模型决定发起工具；call_471a7eea426342ccbcfdda83:search, call_28bd026eb11941c48ea63b12:search|
|13|tool|search call_471a7eea426342ccbcfdda83；query SHA256=b06e0e79bba1473b，top_k=None；ok=True，返回5，新证据2，完全重复查询=False；#1 8865:1500+900(E10); #2 78245:63000+900(E11); #3 3094:583500+900(E9); #4 56790:0+900(E1); #5 3094:143250+900(E12)|
|14|tool|search call_28bd026eb11941c48ea63b12；query SHA256=cc2a0f1f8a5d8e97，top_k=None；ok=True，返回5，新证据1，完全重复查询=False；#1 44164:750+900(E2); #2 46699:25500+900(E4); #3 8865:1500+900(E10); #4 3094:583500+900(E9); #5 69407:11250+900(E13)|
|15|state|步骤2，工具4，累计token5433，stalled_searches=0；完整state证据数13，candidate_answer仍空。|
|16|context|上下文选择；移除历史组2，选证据9，12886字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|17|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|18|api_attempt|真实API#3；HTTP 200；usage=4048；tool_choice=auto；实际messages=12886字符；证据[E3,E4,E5,E2,E11,E9,E10,E13,E1]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|19|assistant|模型决定发起工具；call_05929a6a57cf4e5da6e25944:search, call_a703d0c8c7874ec79343e316:search|
|20|tool|search call_05929a6a57cf4e5da6e25944；query SHA256=b06e0e79bba1473b，top_k=None；ok=True，返回5，新证据0，完全重复查询=True；#1 8865:1500+900(E10); #2 78245:63000+900(E11); #3 3094:583500+900(E9); #4 56790:0+900(E1); #5 3094:143250+900(E12)|
|21|tool|search call_a703d0c8c7874ec79343e316；query SHA256=d83718f97e4cf6d2，top_k=None；ok=True，返回5，新证据3，完全重复查询=False；#1 3094:583500+900(E9); #2 8865:1500+900(E10); #3 8865:2250+900(E14); #4 50983:1215000+900(E15); #5 32144:1215000+900(E16)|
|22|state|步骤3，工具6，累计token9481，stalled_searches=0；完整state证据数16，candidate_answer仍空。|
|23|context|上下文选择；移除历史组3，选证据9，12905字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|24|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|25|api_attempt|真实API#4；HTTP 200；usage=4050；tool_choice=auto；实际messages=12905字符；证据[E3,E4,E5,E2,E11,E9,E10,E13,E1]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|26|assistant|模型决定发起工具；call_2edf49b4c2fe43bab9f5250f:search, call_3bb9760ae8df4f63ad35d1d1:search|
|27|tool|search call_2edf49b4c2fe43bab9f5250f；query SHA256=73714810d1da07fd，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 8865:1500+900(E10); #2 78245:63000+900(E11); #3 3094:583500+900(E9); #4 56790:0+900(E1); #5 3094:143250+900(E12)|
|28|tool|search call_3bb9760ae8df4f63ad35d1d1；query SHA256=272ba403c0e30dc9，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 3094:583500+900(E9); #2 8865:1500+900(E10); #3 8865:2250+900(E14); #4 50983:1215000+900(E15); #5 32144:1215000+900(E16)|
|29|state|步骤4，工具8，累计token13531，stalled_searches=2；完整state证据数16，candidate_answer仍空。|
|30|skill_selected|skill_selected：search-recovery，来源automatic。|
|31|skill_loaded|skill_loaded：search-recovery，来源automatic。|
|32|finalization|进入收尾：search_stalled；剩余已报告token预算=16469；下一请求工具禁用。|
|33|context|上下文选择；移除历史组4，选证据8，13435字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|34|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|35|api_attempt|真实API#5；HTTP 200；usage=3140；tool_choice=none；实际messages=13435字符；证据[E3,E4,E5,E2,E11,E9,E10,E13]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|36|assistant|模型最终决定：原始content中的answer为非空候选。|
|37|answer|JSON解析接受原始非空answer；supporting_evidence=['E2', 'E13']；引用片段坐标验证通过。坐标有效不代表全部条件语义成立。|
|38|run_end|运行结束status=completed；usage_complete=True；导出answer保留非空候选。|

#### 本次逐条件语义核查

|条件|判定|支持/反证定位|缺口与实际可见性|
|---|---|---|---|
|条件1（对应历史条件表）|不同候选；别名关系无支持|支持 doc69407[11620:11912]; 反证 doc34133[753:922]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件2（对应历史条件表）|部分相关，起止语义不同|支持 doc44164[1484:1626]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件3（对应历史条件表）|所引用同名步道出现反证|反证 doc69407[11921:12125]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件4（对应历史条件表）|未证明||完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
#### 可复测项及解释边界

保持预算与检索方法不变，在历史或新运行的同一候选节点只替换一条重复查询为“该候选+尚缺距离/步道条件”核查，分别报告找回反证与是否改变输出；不把尚未执行的效果写作提升。

本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。



## 验证题 1066 逐题复盘

识别一部短片，并核对年份、片长、乡村新教师情节、导演第一学历、剪辑师与指定战争片的关联。

历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。

### 可证实的结论

曾出现参考文字不等于最后仍有候选证据。关键片段后续被上下文选择丢失，且电影关联条件尚未全部验证。

首次问题：seq18构建上下文、seq20实际请求首次遗漏E12；E12仍在完整state，seq13曾可见，seq14也已发出包含候选及导演的查询。

工具8次（全部search，open/find均0），真实API5次，总usage=17843。收尾前余额：{'tokens': 15590, 'tools': 16, 'steps': 8, 'stalled_searches': 3}。

### 按序时间线

|seq/index|事件|观察及定位|
|---|---|---|
|0|run_start|启动baseline；config_id=61d7cc3701b2a42a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|skill_selected|skill_selected：multi-clue-decomposition，来源automatic。|
|3|skill_loaded|skill_loaded：multi-clue-decomposition，来源automatic。|
|4|context|上下文选择；移除历史组0，选证据0，3856字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|5|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|6|api_attempt|真实API#1；HTTP 200；usage=1705；tool_choice=auto；实际messages=3856字符；证据[]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|7|assistant|模型决定发起工具；call_00_DuhQeZ2DYmACfrnh8lyz5719:search, call_01_RCUt40y7Hhsc02bbCVt09488:search|
|8|tool|search call_00_DuhQeZ2DYmACfrnh8lyz5719；query SHA256=c18112055061ef87，top_k=10；ok=True，返回10，新证据10，完全重复查询=False；#1 41005:2250+900(E1); #2 12060:0+696(E2); #3 15322:54750+900(E3); #4 53440:91500+900(E4); #5 44637:3000+900(E5); #6 1992:3750+900(E6); #7 74534:1256250+900(E7); #8 71762:13500+900(E8); #9 83893:0+900(E9); #10 74402:91500+900(E10)|
|9|tool|search call_01_RCUt40y7Hhsc02bbCVt09488；query SHA256=2eee2ddd5c15010e，top_k=10；ok=True，返回10，新证据9，完全重复查询=False；#1 64336:27000+900(E11); #2 26814:0+726(E12); #3 90881:88500+900(E13); #4 8930:252000+900(E14); #5 35113:3000+900(E15); #6 71762:13500+900(E8); #7 3644:2250+900(E16); #8 72668:63750+900(E17); #9 60541:18750+900(E18); #10 40371:335250+900(E19)|
|10|state|步骤1，工具2，累计token1705，stalled_searches=0；完整state证据数19，candidate_answer仍空。|
|11|context|上下文选择；移除历史组1，选证据9，13834字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|12|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|13|api_attempt|真实API#2；HTTP 200；usage=4224；tool_choice=auto；实际messages=13834字符；证据[E1,E4,E5,E9,E11,E13,E15,E2,E12]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|14|assistant|模型决定发起工具；call_00_teXwC658ZQoEy3FgwpoY5581:search, call_01_8hUWE6QjNJNVFH6BFUBt2291:search|
|15|tool|search call_00_teXwC658ZQoEy3FgwpoY5581；query SHA256=8fd7cd18727af466，top_k=10；ok=True，返回10，新证据9，完全重复查询=False；#1 47663:750+900(E20); #2 61697:3750+900(E21); #3 76530:0+900(E22); #4 26814:0+726(E12); #5 24276:38250+900(E23); #6 10058:162000+900(E24); #7 17258:455250+900(E25); #8 8294:1500+900(E26); #9 76530:750+900(E27); #10 46079:9000+452(E28)|
|16|tool|search call_01_8hUWE6QjNJNVFH6BFUBt2291；query SHA256=f322b5a6711c32cb，top_k=10；ok=True，返回10，新证据8，完全重复查询=False；#1 26814:0+726(E12); #2 71762:13500+900(E8); #3 23031:6000+900(E29); #4 61101:1500+380(E30); #5 46411:23250+900(E31); #6 4256:14250+707(E32); #7 76869:153000+900(E33); #8 14809:13500+900(E34); #9 76530:9750+900(E35); #10 77139:6000+900(E36)|
|17|state|步骤2，工具4，累计token5929，stalled_searches=0；完整state证据数36，candidate_answer仍空。|
|18|context|上下文选择；移除历史组2，选证据9，13880字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|19|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|20|api_attempt|真实API#3；HTTP 200；usage=4200；tool_choice=auto；实际messages=13880字符；证据[E1,E25,E21,E23,E26,E4,E5,E9,E28]；参考字面串在messages/证据=True/False。输入仅按api_attempt.request.messages审计。|
|21|assistant|模型决定发起工具；call_00_bffCXnyhhjBulrmPY8eQ3540:search, call_01_8KXXivhGosM5xkw12yO71393:search|
|22|tool|search call_00_bffCXnyhhjBulrmPY8eQ3540；query SHA256=c903c60cd3bac188，top_k=10；ok=True，返回10，新证据1，完全重复查询=False；#1 10058:162000+900(E24); #2 26814:0+726(E12); #3 70355:40500+900(E37); #4 41005:2250+900(E1); #5 76530:750+900(E27); #6 12060:0+696(E2); #7 47663:750+900(E20); #8 15322:54750+900(E3); #9 53440:91500+900(E4); #10 44637:3000+900(E5)|
|23|tool|search call_01_8KXXivhGosM5xkw12yO71393；query SHA256=f322b5a6711c32cb，top_k=10；ok=True，返回10，新证据0，完全重复查询=True；#1 26814:0+726(E12); #2 71762:13500+900(E8); #3 23031:6000+900(E29); #4 61101:1500+380(E30); #5 46411:23250+900(E31); #6 4256:14250+707(E32); #7 76869:153000+900(E33); #8 14809:13500+900(E34); #9 76530:9750+900(E35); #10 77139:6000+900(E36)|
|24|state|步骤3，工具6，累计token10129，stalled_searches=1；完整state证据数37，candidate_answer仍空。|
|25|skill_selected|skill_selected：search-recovery，来源automatic。|
|26|skill_loaded|skill_loaded：search-recovery，来源automatic。|
|27|context|上下文选择；移除历史组3，选证据8，14572字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|28|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|29|api_attempt|真实API#4；HTTP 200；usage=4281；tool_choice=auto；实际messages=14572字符；证据[E1,E25,E21,E23,E26,E4,E5,E9]；参考字面串在messages/证据=True/False。输入仅按api_attempt.request.messages审计。|
|30|assistant|模型决定发起工具；call_00_L94EmWOwbckYVmLucHPx0505:search, call_01_Ugt2o495alPZVttQKnVP5281:search|
|31|tool|search call_00_L94EmWOwbckYVmLucHPx0505；query SHA256=463883d3a3535d33，top_k=10；ok=True，返回10，新证据0，完全重复查询=False；#1 10058:162000+900(E24); #2 26814:0+726(E12); #3 70355:40500+900(E37); #4 41005:2250+900(E1); #5 76530:750+900(E27); #6 12060:0+696(E2); #7 47663:750+900(E20); #8 15322:54750+900(E3); #9 53440:91500+900(E4); #10 44637:3000+900(E5)|
|32|tool|search call_01_Ugt2o495alPZVttQKnVP5281；query SHA256=f322b5a6711c32cb，top_k=10；ok=True，返回10，新证据0，完全重复查询=True；#1 26814:0+726(E12); #2 71762:13500+900(E8); #3 23031:6000+900(E29); #4 61101:1500+380(E30); #5 46411:23250+900(E31); #6 4256:14250+707(E32); #7 76869:153000+900(E33); #8 14809:13500+900(E34); #9 76530:9750+900(E35); #10 77139:6000+900(E36)|
|33|state|步骤4，工具8，累计token14410，stalled_searches=3；完整state证据数37，candidate_answer仍空。|
|34|finalization|进入收尾：search_stalled；剩余已报告token预算=15590；下一请求工具禁用。|
|35|context|上下文选择；移除历史组4，选证据8，14802字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|36|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|37|api_attempt|真实API#5；HTTP 200；usage=3433；tool_choice=none；实际messages=14802字符；证据[E1,E25,E21,E23,E26,E4,E5,E35]；参考字面串在messages/证据=True/False。输入仅按api_attempt.request.messages审计。|
|38|assistant|模型最终决定：原始content中的answer已经为空。|
|39|answer|JSON解析接受原始空answer；supporting_evidence=[]；空答提前返回，未执行非空答案引用解析。|
|40|run_end|运行结束status=insufficient_evidence；usage_complete=True；导出answer为空。|

条件核查原文只保存在加密私有附件。公开定位：26814:330:726; 26814:66:149; 61101:1546:1578; 61101:222:247; 61101:577:599; 61101:601:615; 77139:2369:2533; 77139:80:193。

### 下一步单变量与未确认项

最小对照仅优先保留历史已经观察到的E12，维持同一证据字符预算。离线已证实seq20/29/37可重入且总字符<24000；不同时加入新导演/剪辑证据。已实测下一动作，尚未续跑最终回答与终局EM。

百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。

<!-- BAILIAN-APPENDIX -->

### 充值后百炼基线对照

百炼本次在两个相同宽泛查询各重复一次后弃答。候选定位页从未进入这次工具结果或实际模型输入，因此本次首要问题在候选发现/查询恢复；历史那次则已经发现候选、后来从输入中消失。两条轨迹不能混成同一种“看见答案还不答”。原始模型直接空答，解析和导出没有清空非空内容。

本次有效运行：配置`900fc3b95b775d2a`，3个HTTP200、4次search、usage总计9082；严格EM=0。没有open/find，所有search使用配置默认top5。

首次问题：seq14把首轮两条查询原样重发，seq15/16无新证据；seq20 search_stalled收尾时仍余24193 tokens、20工具、10步骤。

#### 初次账户错误尝试：全部事件

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|skill_selected|skill_selected：multi-clue-decomposition，来源automatic。|
|3|skill_loaded|skill_loaded：multi-clue-decomposition，来源automatic。|
|4|context|上下文选择；移除历史组0，选证据0，3856字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|5|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|6|api_attempt|首请求HTTP400，Arrearage；无模型答题回复，usage_unknown=True。实际输入只认本事件request.messages。|
|7|error|服务商账户错误被记录；没有Agent答题决定。|
|8|run_end|provider_error结束，reported_tokens=0，工具0，EM未测；不与充值后运行拼接。|

#### 充值后有效运行：全部事件

seq为本次轨迹自己的零起算位置，不与历史seq混用。实际模型输入只读取`api_attempt.request.messages`。

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|skill_selected|skill_selected：multi-clue-decomposition，来源automatic。|
|3|skill_loaded|skill_loaded：multi-clue-decomposition，来源automatic。|
|4|context|上下文选择；移除历史组0，选证据0，3856字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|5|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|6|api_attempt|真实API#1；HTTP 200；usage=1691；tool_choice=auto；实际messages=3856字符；证据[]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|7|assistant|模型决定发起工具；call_8c32c4c2b6e44116b5f2e39d:search, call_ea8c00adf6884322b1aaf4f6:search|
|8|tool|search call_8c32c4c2b6e44116b5f2e39d；query SHA256=a7919dd5f324e149，top_k=None；ok=True，返回5，新证据5，完全重复查询=False；#1 41005:2250+900(E1); #2 12060:0+696(E2); #3 15322:54750+900(E3); #4 53440:91500+900(E4); #5 44637:3000+900(E5)|
|9|tool|search call_ea8c00adf6884322b1aaf4f6；query SHA256=3574029b5d213bbf，top_k=None；ok=True，返回5，新证据5，完全重复查询=False；#1 71762:13500+900(E6); #2 74534:3221250+900(E7); #3 57799:3000+900(E8); #4 82975:124500+900(E9); #5 15322:89250+900(E10)|
|10|state|步骤1，工具2，累计token1691，stalled_searches=0；完整state证据数10，candidate_answer仍空。|
|11|context|上下文选择；移除历史组1，选证据9，13917字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|12|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|13|api_attempt|真实API#2；HTTP 200；usage=4116；tool_choice=auto；实际messages=13917字符；证据[E1,E4,E5,E2,E8,E10,E7,E9,E3]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|14|assistant|模型决定发起工具；call_60294c07ec4f4a13b4e2a891:search, call_9084a1bcbbd8424fa5814495:search|
|15|tool|search call_60294c07ec4f4a13b4e2a891；query SHA256=a7919dd5f324e149，top_k=None；ok=True，返回5，新证据0，完全重复查询=True；#1 41005:2250+900(E1); #2 12060:0+696(E2); #3 15322:54750+900(E3); #4 53440:91500+900(E4); #5 44637:3000+900(E5)|
|16|tool|search call_9084a1bcbbd8424fa5814495；query SHA256=3574029b5d213bbf，top_k=None；ok=True，返回5，新证据0，完全重复查询=True；#1 71762:13500+900(E6); #2 74534:3221250+900(E7); #3 57799:3000+900(E8); #4 82975:124500+900(E9); #5 15322:89250+900(E10)|
|17|state|步骤2，工具4，累计token5807，stalled_searches=2；完整state证据数10，candidate_answer仍空。|
|18|skill_selected|skill_selected：search-recovery，来源automatic。|
|19|skill_loaded|skill_loaded：search-recovery，来源automatic。|
|20|finalization|进入收尾：search_stalled；剩余已报告token预算=24193；下一请求工具禁用。|
|21|context|上下文选择；移除历史组2，选证据8，14425字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|22|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|23|api_attempt|真实API#3；HTTP 200；usage=3275；tool_choice=none；实际messages=14425字符；证据[E1,E4,E5,E2,E8,E10,E7,E9]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|24|assistant|模型最终决定：原始content中的answer已经为空。|
|25|answer|JSON解析接受原始空answer；supporting_evidence=[]；空答提前返回，未执行非空答案引用解析。|
|26|run_end|运行结束status=insufficient_evidence；usage_complete=True；导出answer为空。|

#### 本次逐条件语义核查

|条件|判定|支持/反证定位|缺口与实际可见性|
|---|---|---|---|
|条件1（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc61101[1546:1578]; 支持 doc61101[577:599]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件2（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc61101[601:615]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件3（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc26814[66:149]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件4（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc26814[330:726]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件5（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc61101[222:247]; 支持 doc77139[80:193]; 支持 doc77139[2369:2533]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
#### 可复测项及解释边界

1066历史seq20严格E9→E12单片段替换对照用于检验“保留已观察候选”影响，由主任务以相同服务商适配执行；它不是本次百炼seq20（本次seq20是finalization）的替换，也不是完整新基线重跑。另可针对新运行单独替换一次重复查询，仅测候选发现，不与保留片段实验合并。

本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。

<!-- RETENTION-PAIR-APPENDIX -->

### 1066 严格单片段保留：真实下一动作对照

保留历史候选片段后，处理组第二条查询使用候选及导演，对照组第二条仍是问题词泛搜。固定BM25离线执行显示：对照组第二条也找回doc26814:0（排名2），处理组排名1，并额外在排名4返回doc61101:1500的年份片目。不能说对照组未找到候选。两边第一条相同且前5均无该候选；这轮都没有片长和剪辑师战争片时长的完整支持。只能确认局部下一动作与检索排序差异，终局EM未测。

固定节点是历史轨迹api seq20。对照请求为原始完整请求；处理请求只把证据列表第7位E9换为此前已经观察到的E12(doc26814:0)。不是充值后新基线的seq20，也不是重新选取全部证据。原question、tools、其他八片段及顺序、非证据状态均不变。

两臂统一改为百炼0731、enable_thinking=false，去掉旧thinking字段。已用完整JSON对象比较证明实际请求只作了这些相同适配；max_tokens均1024、证据预算9568字符、消息上限24000字符。处理片段稍短，实际输入字符及prompt token可不同；预算一致不等于输入长度相同。

没有新增检索证据进入API输入，未用标签选片段。两臂各只有一次API调用、一次模型下一动作回复；后续工具调用仅由离线复放执行，没有把结果回传模型，也没有运行到最终答案。

|臂|HTTP/响应身份|prompt/completion/total token|两条查询结果|终局EM|
|---|---|---|---|---|
|control|200/deepseek-v4-flash-0731|4074/105/4179|第二条候选排名2|未测|
|treatment|200/deepseek-v4-flash-0731|4023/117/4140|第二条候选排名1；年份片目排名4|未测|

#### 两臂完整事件表

两臂没有共享Agent轨迹seq，以下用臂内事件标签定位；offline-search不是一次新API请求。

|臂/事件|类型|动作及定位|
|---|---|---|
|control/request|api_attempt|HTTP200；实际输入仅按该文件request.messages；证据['E1', 'E25', 'E21', 'E23', 'E26', 'E4', 'E5', 'E9', 'E28']；SHA256=ebfea3589d46a5be80f948028c4b6799bfa6b39d614dece99494893f3a5be531。|
|control/decision|assistant|模型返回两个search工具调用，finish_reason=tool_calls；尚无最终answer。|
|control/search-1|offline-search|call_id=call_257f73ed40964e2598a07e02；query SHA256=c18112055061ef877e661d955b14525d8cfea9596119bf050e82aa7ff737732c；top5；2.675695s；#1 41005:2250:3150; #2 12060:0:696; #3 15322:54750:55650; #4 53440:91500:92400; #5 44637:3000:3900；结果未回传模型。|
|control/search-2|offline-search|call_id=call_be932a777ee947b4b5a77107；query SHA256=2eee2ddd5c15010e0341e50348ae036967b01743d83764ca0460a1170fd1caf7；top5；0.738524s；#1 64336:27000:27900; #2 26814:0:726; #3 90881:88500:89400; #4 8930:252000:252900; #5 35113:3000:3900；结果未回传模型。|
|treatment/request|api_attempt|HTTP200；实际输入仅按该文件request.messages；证据['E1', 'E25', 'E21', 'E23', 'E26', 'E4', 'E5', 'E12', 'E28']；SHA256=477a9620e6bf1a506ed325a0acbb656b1a3d0400c9ccf7256dcd53ead557c2d9。|
|treatment/decision|assistant|模型返回两个search工具调用，finish_reason=tool_calls；尚无最终answer。|
|treatment/search-1|offline-search|call_id=call_37b22e866bba4f778f1a599b；query SHA256=c18112055061ef877e661d955b14525d8cfea9596119bf050e82aa7ff737732c；top5；0.806368s；#1 41005:2250:3150; #2 12060:0:696; #3 15322:54750:55650; #4 53440:91500:92400; #5 44637:3000:3900；结果未回传模型。|
|treatment/search-2|offline-search|call_id=call_c37cd022c6e140239ccc7358；query SHA256=f322b5a6711c32cb81f2be797c9c7d0af16412e54fb866a69cf17d4749d3177f；top5；0.335407s；#1 26814:0:726; #2 71762:13500:14400; #3 23031:6000:6900; #4 61101:1500:1880; #5 46411:23250:24150；结果未回传模型。|

#### 逐条件解释

两臂的候选页均覆盖乡村学校教师情节以及导演学习经历；学习经历措辞仍不足以精确证明题目所问的第一学历。处理组多返回年份片目，但没有因此获得片长或完整剪辑师链条。命中现有注释片段不等于该条件已经严格成立，尤其是带有未解决限定的学历条件。

这是一次局部、单样本对照。temperature相同也不保证模型服务完全无随机差异；没有重复样本或完整续跑，不能外推出准确率改善、显著性、召回率全局提升或预算节省。四条离线查询的耗时受缓存和执行顺序影响，不作为两臂速度优劣结论。



## 验证题 788 逐题复盘

识别清真寺，核对竣工年代、容量、室内面积，与另一清真寺及医院的步行关系和成立年代。

历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。

### 可证实的结论

主要指标可见，关键条件片段未保留；离线还发现面积来源冲突及候选医院年代反证，不能认定所有条件原已满足。

首次问题：seq15在候选主要指标已进入seq13请求后继续重复该指标；程序层更明确的问题为seq29遗漏seq25第8名返回的竣工年份E20。

工具12次（全部search，open/find均0），真实API7次，总usage=26364。收尾前余额：{'tokens': 7086, 'tools': 12, 'steps': 6, 'stalled_searches': 3}。

### 按序时间线

|seq/index|事件|观察及定位|
|---|---|---|
|0|run_start|启动baseline；config_id=61d7cc3701b2a42a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|skill_selected|skill_selected：multi-clue-decomposition，来源automatic。|
|3|skill_loaded|skill_loaded：multi-clue-decomposition，来源automatic。|
|4|context|上下文选择；移除历史组0，选证据0，3867字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|5|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|6|api_attempt|真实API#1；HTTP 200；usage=1706；tool_choice=auto；实际messages=3867字符；证据[]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|7|assistant|模型决定发起工具；call_00_HIAVsJwdvHCaC07Etfe93174:search, call_01_FSvEfVu8Ldn6rC3UvvK51498:search|
|8|tool|search call_00_HIAVsJwdvHCaC07Etfe93174；query SHA256=d48683c68e2cad0c，top_k=10；ok=True，返回10，新证据10，完全重复查询=False；#1 45789:3750+900(E1); #2 96357:0+562(E2); #3 45789:4500+900(E3); #4 81783:1500+900(E4); #5 1823:0+900(E5); #6 42601:1500+900(E6); #7 45789:6000+900(E7); #8 100170:6750+900(E8); #9 45789:1500+900(E9); #10 37436:214500+900(E10)|
|9|tool|search call_01_FSvEfVu8Ldn6rC3UvvK51498；query SHA256=061ba1e6669eb4e8，top_k=10；ok=True，返回10，新证据5，完全重复查询=False；#1 96357:0+562(E2); #2 1823:0+900(E5); #3 45789:3750+900(E1); #4 45789:6000+900(E7); #5 45789:3000+900(E11); #6 70227:1500+900(E12); #7 38198:49500+900(E13); #8 81783:9750+900(E14); #9 81783:1500+900(E4); #10 45789:2250+900(E15)|
|10|state|步骤1，工具2，累计token1706，stalled_searches=0；完整state证据数15，candidate_answer仍空。|
|11|context|上下文选择；移除历史组1，选证据9，13741字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|12|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|13|api_attempt|真实API#2；HTTP 200；usage=4284；tool_choice=auto；实际messages=13741字符；证据[E7,E1,E6,E9,E2,E4,E11,E15,E5]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|14|assistant|模型决定发起工具；call_00_eq6AkGjAUZow0gXlxesL2266:search, call_01_RyPtitp7Bc2sohxsUj3h3215:search|
|15|tool|search call_00_eq6AkGjAUZow0gXlxesL2266；query SHA256=e95043d9e1db4c0d，top_k=5；ok=True，返回5，新证据1，完全重复查询=False；#1 96357:0+562(E2); #2 1823:0+900(E5); #3 45789:2250+900(E15); #4 45789:3750+900(E1); #5 81783:7500+900(E16)|
|16|tool|search call_01_RyPtitp7Bc2sohxsUj3h3215；query SHA256=3e0e658ec7a47666，top_k=5；ok=True，返回5，新证据0，完全重复查询=False；#1 45789:3750+900(E1); #2 45789:6000+900(E7); #3 96357:0+562(E2); #4 45789:1500+900(E9); #5 42601:1500+900(E6)|
|17|state|步骤2，工具4，累计token5990，stalled_searches=1；完整state证据数16，candidate_answer仍空。|
|18|skill_selected|skill_selected：search-recovery，来源automatic。|
|19|skill_loaded|skill_loaded：search-recovery，来源automatic。|
|20|context|上下文选择；移除历史组2，选证据8，14114字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|21|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|22|api_attempt|真实API#3；HTTP 200；usage=4230；tool_choice=auto；实际messages=14114字符；证据[E7,E1,E6,E9,E2,E4,E11,E15]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|23|assistant|模型决定发起工具；call_00_mz318dMuaAoGNc6fdALm3552:search, call_01_cJdO7TMpWHfcHiuRxXA61130:search|
|24|tool|search call_00_mz318dMuaAoGNc6fdALm3552；query SHA256=77eed5aca19b1d55，top_k=10；ok=True，返回10，新证据2，完全重复查询=False；#1 45789:3750+900(E1); #2 96357:0+562(E2); #3 45789:6000+900(E7); #4 45789:4500+900(E3); #5 81783:1500+900(E4); #6 1823:0+900(E5); #7 42601:1500+900(E6); #8 100170:6750+900(E8); #9 77869:522750+900(E17); #10 52795:0+900(E18)|
|25|tool|search call_01_cJdO7TMpWHfcHiuRxXA61130；query SHA256=fe1b6aa5721efc12，top_k=10；ok=True，返回10，新证据2，完全重复查询=False；#1 96357:0+562(E2); #2 1823:0+900(E5); #3 45789:2250+900(E15); #4 45789:3750+900(E1); #5 81783:7500+900(E16); #6 70227:1500+900(E12); #7 72467:5250+900(E19); #8 70534:0+900(E20); #9 38198:49500+900(E13); #10 81783:1500+900(E4)|
|26|state|步骤3，工具6，累计token10220，stalled_searches=0；完整state证据数20，candidate_answer仍空。|
|27|context|上下文选择；移除历史组3，选证据8，14133字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|28|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|29|api_attempt|真实API#4；HTTP 200；usage=4240；tool_choice=auto；实际messages=14133字符；证据[E7,E1,E6,E9,E2,E4,E11,E15]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|30|assistant|模型决定发起工具；call_00_Z7GbguGT88gfsR17KY0N0758:search, call_01_ecRpnSUQ6ASEUGXFSQgn1775:search|
|31|tool|search call_00_Z7GbguGT88gfsR17KY0N0758；query SHA256=e95043d9e1db4c0d，top_k=5；ok=True，返回5，新证据0，完全重复查询=True；#1 96357:0+562(E2); #2 1823:0+900(E5); #3 45789:2250+900(E15); #4 45789:3750+900(E1); #5 81783:7500+900(E16)|
|32|tool|search call_01_ecRpnSUQ6ASEUGXFSQgn1775；query SHA256=fb20aa859fba028f，top_k=5；ok=True，返回5，新证据5，完全重复查询=False；#1 70534:3000+900(E21); #2 6743:0+900(E22); #3 56188:0+900(E23); #4 56202:0+900(E24); #5 70534:750+900(E25)|
|33|state|步骤4，工具8，累计token14460，stalled_searches=0；完整state证据数25，candidate_answer仍空。|
|34|context|上下文选择；移除历史组4，选证据8，14119字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|35|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|36|api_attempt|真实API#5；HTTP 200；usage=4225；tool_choice=auto；实际messages=14119字符；证据[E7,E1,E6,E9,E2,E4,E11,E15]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|37|assistant|模型决定发起工具；call_00_oHVDnxk42TSjIMMcbwj00950:search, call_01_MzxDFwDWSn8xFcT7NLED1492:search|
|38|tool|search call_00_oHVDnxk42TSjIMMcbwj00950；query SHA256=445075b119ae9b1d，top_k=10；ok=True，返回10，新证据4，完全重复查询=False；#1 70534:3000+900(E21); #2 6743:0+900(E22); #3 56188:0+900(E23); #4 56202:0+900(E24); #5 70534:750+900(E25); #6 70534:0+900(E20); #7 56202:5250+900(E26); #8 70534:3750+672(E27); #9 56202:2250+900(E28); #10 56202:1500+900(E29)|
|39|tool|search call_01_MzxDFwDWSn8xFcT7NLED1492；query SHA256=529befe134c981f2，top_k=10；ok=True，返回10，新证据0，完全重复查询=False；#1 96357:0+562(E2); #2 1823:0+900(E5); #3 70534:0+900(E20); #4 45789:2250+900(E15); #5 77869:522750+900(E17); #6 45789:6000+900(E7); #7 45789:3750+900(E1); #8 81783:7500+900(E16); #9 81783:9750+900(E14); #10 70227:1500+900(E12)|
|40|state|步骤5，工具10，累计token18685，stalled_searches=1；完整state证据数29，candidate_answer仍空。|
|41|context|上下文选择；移除历史组5，选证据8，14087字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|42|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|43|api_attempt|真实API#6；HTTP 200；usage=4229；tool_choice=auto；实际messages=14087字符；证据[E7,E1,E6,E9,E2,E4,E11,E15]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|44|assistant|模型决定发起工具；call_00_Mc0pEoqqwGnkBJximGwt3965:search, call_01_NJWm7XjriLTF9eQjA0UM7324:search|
|45|tool|search call_00_Mc0pEoqqwGnkBJximGwt3965；query SHA256=e95043d9e1db4c0d，top_k=5；ok=True，返回5，新证据0，完全重复查询=True；#1 96357:0+562(E2); #2 1823:0+900(E5); #3 45789:2250+900(E15); #4 45789:3750+900(E1); #5 81783:7500+900(E16)|
|46|tool|search call_01_NJWm7XjriLTF9eQjA0UM7324；query SHA256=445075b119ae9b1d，top_k=5；ok=True，返回5，新证据0，完全重复查询=True；#1 70534:3000+900(E21); #2 6743:0+900(E22); #3 56188:0+900(E23); #4 56202:0+900(E24); #5 70534:750+900(E25)|
|47|state|步骤6，工具12，累计token22914，stalled_searches=3；完整state证据数29，candidate_answer仍空。|
|48|finalization|进入收尾：reserve_final_usage；剩余已报告token预算=7086；下一请求工具禁用。|
|49|context|上下文选择；移除历史组6，选证据8，14330字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|50|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|51|api_attempt|真实API#7；HTTP 200；usage=3450；tool_choice=none；实际messages=14330字符；证据[E7,E1,E6,E9,E2,E4,E11,E15]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|52|assistant|模型最终决定：原始content中的answer已经为空。|
|53|answer|JSON解析接受原始空answer；supporting_evidence=['E2', 'E15']；空答提前返回，未执行非空答案引用解析。|
|54|run_end|运行结束status=insufficient_evidence；usage_complete=True；导出answer为空。|

条件核查原文只保存在加密私有附件。公开定位：56188:875:932; 56202:3638:3756; 57904:586:735; 6743:409:431; 70534:1930:2032; 70534:622:642; 70534:643:673; 70534:674:697; 95802:120:182; 96357:245:295; 96357:297:341。

### 下一步单变量与未确认项

优先只保留已观察E20，检查该条件进入实际请求后是否被确认；不同时改查询、医院假设、预算。下一独立对照可核查候选医院成立年，观察是否避免把扩建年当创立年。

百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。

<!-- BAILIAN-APPENDIX -->

### 充值后百炼基线对照

百炼仍弃答，且再次出现可直接定位的证据保留问题：完工年份片段在seq15/24/31/39工具结果出现，实际seq22及随后请求均未保留；邻近对象片段也未保留。最终模型据其实际输入说缺年份是可解释的，但固定语料仍存在面积口径冲突与邻近医院成立时间缺口，因此保留年份本身尚不能证明全部条件或保证答对。

本次有效运行：配置`900fc3b95b775d2a`，6个HTTP200、11次search、usage总计22139；严格EM=0。没有open/find，所有search使用配置默认top5。

首次问题：seq15已返回完工年份与邻近对象，紧接实际seq22却排除E12与E8；seq23因此继续查询同一缺失条件。

#### 初次账户错误尝试：全部事件

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|skill_selected|skill_selected：multi-clue-decomposition，来源automatic。|
|3|skill_loaded|skill_loaded：multi-clue-decomposition，来源automatic。|
|4|context|上下文选择；移除历史组0，选证据0，3867字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|5|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|6|api_attempt|首请求HTTP400，Arrearage；无模型答题回复，usage_unknown=True。实际输入只认本事件request.messages。|
|7|error|服务商账户错误被记录；没有Agent答题决定。|
|8|run_end|provider_error结束，reported_tokens=0，工具0，EM未测；不与充值后运行拼接。|

#### 充值后有效运行：全部事件

seq为本次轨迹自己的零起算位置，不与历史seq混用。实际模型输入只读取`api_attempt.request.messages`。

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|skill_selected|skill_selected：multi-clue-decomposition，来源automatic。|
|3|skill_loaded|skill_loaded：multi-clue-decomposition，来源automatic。|
|4|context|上下文选择；移除历史组0，选证据0，3867字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|5|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|6|api_attempt|真实API#1；HTTP 200；usage=1693；tool_choice=auto；实际messages=3867字符；证据[]；参考字面串在messages/证据=False/False。输入仅按api_attempt.request.messages审计。|
|7|assistant|模型决定发起工具；call_c0c074dc3bab4bcf840f9ba7:search, call_6fbe8a43f451462c8c4f6670:search|
|8|tool|search call_c0c074dc3bab4bcf840f9ba7；query SHA256=73499f6a8aa51879，top_k=None；ok=True，返回5，新证据5，完全重复查询=False；#1 96357:0+562(E1); #2 45789:3750+900(E2); #3 45789:6000+900(E3); #4 1823:0+900(E4); #5 45789:4500+900(E5)|
|9|tool|search call_6fbe8a43f451462c8c4f6670；query SHA256=93039dd2845f1f48，top_k=None；ok=True，返回5，新证据2，完全重复查询=False；#1 45789:3000+900(E6); #2 45789:750+900(E7); #3 45789:3750+900(E2); #4 45789:6000+900(E3); #5 96357:0+562(E1)|
|10|state|步骤1，工具2，累计token1693，stalled_searches=0；完整state证据数7，candidate_answer仍空。|
|11|context|上下文选择；移除历史组1，选证据7，11436字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|12|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|13|api_attempt|真实API#2；HTTP 200；usage=3752；tool_choice=auto；实际messages=11436字符；证据[E3,E2,E7,E1,E6,E4,E5]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|14|assistant|模型决定发起工具；call_084cb95f57b54a479d51dea3:search, call_6d39746e5fe74e82bf29fbe3:search|
|15|tool|search call_084cb95f57b54a479d51dea3；query SHA256=72308db62b519e0e，top_k=None；ok=True，返回5，新证据5，完全重复查询=False；#1 6743:0+900(E8); #2 70534:750+900(E9); #3 56202:0+900(E10); #4 70534:3000+900(E11); #5 70534:0+900(E12)|
|16|tool|search call_6d39746e5fe74e82bf29fbe3；query SHA256=74f4c295e31f6117，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 6743:0+900(E8); #2 70534:3000+900(E11); #3 56202:0+900(E10); #4 96357:0+562(E1); #5 70534:750+900(E9)|
|17|state|步骤2，工具4，累计token5445，stalled_searches=1；完整state证据数12，candidate_answer仍空。|
|18|skill_selected|skill_selected：search-recovery，来源automatic。|
|19|skill_loaded|skill_loaded：search-recovery，来源automatic。|
|20|context|上下文选择；移除历史组2，选证据8，14081字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|21|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|22|api_attempt|真实API#3；HTTP 200；usage=4416；tool_choice=auto；实际messages=14081字符；证据[E3,E2,E7,E1,E6,E4,E5,E10]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|23|assistant|模型决定发起工具；call_e0df5c6253b8499b8fa1c735:search, call_6f194b2b30d54acdbb5f54b7:search|
|24|tool|search call_e0df5c6253b8499b8fa1c735；query SHA256=13e364d3b2898d3d，top_k=None；ok=True，返回5，新证据1，完全重复查询=False；#1 70534:3000+900(E11); #2 70534:750+900(E9); #3 6743:0+900(E8); #4 70534:0+900(E12); #5 56202:2250+900(E13)|
|25|tool|search call_6f194b2b30d54acdbb5f54b7；query SHA256=40f6e1b38607172d，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 6743:0+900(E8); #2 70534:3000+900(E11); #3 56202:0+900(E10); #4 96357:0+562(E1); #5 70534:750+900(E9)|
|26|state|步骤3，工具6，累计token9861，stalled_searches=1；完整state证据数13，candidate_answer仍空。|
|27|context|上下文选择；移除历史组3，选证据8，14110字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|28|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|29|api_attempt|真实API#4；HTTP 200；usage=4382；tool_choice=auto；实际messages=14110字符；证据[E3,E2,E7,E1,E6,E4,E5,E10]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|30|assistant|模型决定发起工具；call_cff66a9309954ac190fb627c:search, call_7f0397840ccb40b6907c2423:search, call_ccc94847a51240c7833ef705:search|
|31|tool|search call_cff66a9309954ac190fb627c；query SHA256=3047b4430113895f，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 6743:0+900(E8); #2 70534:3000+900(E11); #3 70534:0+900(E12); #4 70534:750+900(E9); #5 56202:0+900(E10)|
|32|tool|search call_7f0397840ccb40b6907c2423；query SHA256=2c6f1e31875a9773，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 6743:0+900(E8); #2 70534:3000+900(E11); #3 56202:0+900(E10); #4 96357:0+562(E1); #5 70534:750+900(E9)|
|33|tool|search call_ccc94847a51240c7833ef705；query SHA256=c76d2bef63361748，top_k=None；ok=True，返回5，新证据1，完全重复查询=False；#1 6743:0+900(E8); #2 70534:3000+900(E11); #3 56202:0+900(E10); #4 56188:0+900(E14); #5 70534:750+900(E9)|
|34|state|步骤4，工具9，累计token14243，stalled_searches=0；完整state证据数14，candidate_answer仍空。|
|35|context|上下文选择；移除历史组4，选证据8，14116字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|36|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|37|api_attempt|真实API#5；HTTP 200；usage=4394；tool_choice=auto；实际messages=14116字符；证据[E3,E2,E7,E1,E6,E4,E5,E10]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|38|assistant|模型决定发起工具；call_ddaf83ff17274935a8221fc9:search, call_8a6166da6f47472a95cc0b85:search|
|39|tool|search call_ddaf83ff17274935a8221fc9；query SHA256=e958ac387b9d4dad，top_k=None；ok=True，返回5，新证据0，完全重复查询=False；#1 70534:3000+900(E11); #2 70534:750+900(E9); #3 6743:0+900(E8); #4 70534:0+900(E12); #5 56202:2250+900(E13)|
|40|tool|search call_8a6166da6f47472a95cc0b85；query SHA256=2c6f1e31875a9773，top_k=None；ok=True，返回5，新证据0，完全重复查询=True；#1 6743:0+900(E8); #2 70534:3000+900(E11); #3 56202:0+900(E10); #4 96357:0+562(E1); #5 70534:750+900(E9)|
|41|state|步骤5，工具11，累计token18637，stalled_searches=2；完整state证据数14，candidate_answer仍空。|
|42|finalization|进入收尾：search_stalled；剩余已报告token预算=11363；下一请求工具禁用。|
|43|context|上下文选择；移除历史组5，选证据8，14348字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|44|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|45|api_attempt|真实API#6；HTTP 200；usage=3502；tool_choice=none；实际messages=14348字符；证据[E3,E2,E7,E1,E6,E4,E5,E10]；参考字面串在messages/证据=True/True。输入仅按api_attempt.request.messages审计。|
|46|assistant|模型最终决定：原始content中的answer已经为空。|
|47|answer|JSON解析接受原始空answer；supporting_evidence=[]；空答提前返回，未执行非空答案引用解析。|
|48|run_end|运行结束status=insufficient_evidence；usage_complete=True；导出answer为空。|

#### 本次逐条件语义核查

|条件|判定|支持/反证定位|缺口与实际可见性|
|---|---|---|---|
|条件1（对应历史条件表）|新工具已回，实际请求遗失|支持 doc70534[622:642]; 支持 doc70534[1930:2032]; 支持 doc56202[3638:3756]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件2（对应历史条件表）|新实际输入有支持|支持 doc96357[297:341]; 支持 doc70534[643:673]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件3（对应历史条件表）|新实际输入有支持，固定原文存在口径冲突|支持 doc96357[245:295]; 反证 doc70534[674:697]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件4（对应历史条件表）|新工具局部出现，实际输入未保留；条件仍不完备|支持 doc6743[409:431]; 支持 doc95802[120:182]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件5（对应历史条件表）|新工具局部出现，实际输入未保留；条件仍不完备|支持 doc56188[875:932]; 反证 doc57904[586:735]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
#### 可复测项及解释边界

只把新运行seq22一个低相关片段换为已观察E12，保持预算与其他输入固定，可测年份使用/继续查询选择；完整答案仍需另证面积口径、步行关系及医院成立年。不得将附近医院扩建年误当创办年，不应因容量/面积两项匹配就自动答题。

本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。




## 跨题发现与下一轮优先级

1. **优先修复已发现证据的保留。** 64新状态的单片段对照和58旧状态的定位片段对照均在冻结最终请求的单次实测中改变了EM；58同时有容量选择变化，尚未隔离E37单片段贡献；788与1066也有可复现的丢失位置。下一版本应按候选、事件/日期、关系与未满足条件组织有限证据，保持24,000字符总预算；避免用题面词重合分数单独决定保留。生产实现尚未采用任何定向片段ID或参考答案规则。
2. **给恢复策略一次真实执行机会。** 960、1035中，同组两次重复search使停滞计数连续增加，下一轮恢复技能虽加载却立即收尾。可测试“预算允许且首次恢复时留一次工具机会”，同时报告额外用量、恢复后的新证据数及误答变化。本轮已定位原因，尚未在线验证该新策略。
3. **把检索词和证据条件对齐。** 1035需保持城市/创业者/公司三者关系；960需找作者贡献与资助栏；58新基线只见论文参考文献尾部，需要定位致谢/资助。64旧查询top20暴露了关键第13/14名，适合检验有条件扩展候选范围；不能据一题主张无条件把所有请求top_k增大。
4. **把答案文字出现与条件被证明分开。** 390旧新运行均不能用讣闻歌名替代合辑轨序；1155需拒绝地点、距离单位与年代条件不合的替代遗址；788不能把医院床位统计或扩建年当成成立年。引用来源正确只是必要条件，条件表必须记录尚缺关系，不能强迫已有候选立即作答。

建议ddg优先批准“条件证据保留”进入下一轮独立开发对照，再考虑恢复机会与查询策略；一次只改变一处。此优先级是依据本轮证据作出的工程建议，尚不是已完成的通用修复效果。下一轮至少同时记录：支持片段检回率、各实际请求的关键证据可见性、条件覆盖、非空答比例、EM、错误非空答、重复查询、工具数及API总token（输入+输出）。要报告预先固定的独立验证集合，不能把本次事后九题诊断成绩当作泛化能力。

尚未确认：1035销售额换算与推广时间，1155距离及冲突年代，1066第一学历的精确表述及剪辑师2009战争片/142分钟关系（离线已找到候选片长，但本次pair下一步结果未返回该段），788确切相邻医院和步行距离；这些均有固定语料定位或缺口记录。E5尚未完成全量构建，Qwen按用户要求搁置，未作向量优劣结论。没有发现本九题历史空答被解析器或导出器从正确非空答案清空的证据。

## 复现与团队移交

公开复现步骤见[REPRODUCE.md](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/e90397bb2e6af7657077c8fcee9189370a767a1f/docs/validation-review/REPRODUCE.md)，逐组脱敏统计与准备/验证代码分别位于`docs/validation-review/`和`scripts/validation_review/`。完整原题、官方参考、真实答案、规范化值、原始请求响应、必要原文、成对冻结状态与来源清单在加密附件；解密密钥仅本地另存，不随Git或Release上传。

本轮Release：[validation-failure-review-20261115](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/validation-failure-review-20261115)。加密卷与SHA-256见[HANDOFF.md](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/e90397bb2e6af7657077c8fcee9189370a767a1f/docs/validation-review/HANDOFF.md)和[encrypted-evidence-manifest.json](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/blob/e90397bb2e6af7657077c8fcee9189370a767a1f/docs/validation-review/encrypted-evidence-manifest.json)。完整固定语料与BM25沿用[上一轮Release](https://github.com/zz1170115506-del/NLP-Agentic-RAG-for-given-documents/releases/tag/program-acceptance-20261115)，避免重新发布大型语料副本。

工作分支为`codex/validation-failure-review`。该分支交付的是逐题复盘、百炼适配与诊断实测，不替代主分支，也不把本次9题当课程100题正式提交。最终远端提交、下载与解密校验记录随本地交接索引提供。
