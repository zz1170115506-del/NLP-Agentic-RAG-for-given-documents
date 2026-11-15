# 第一类三题逐题复盘（公开脱敏稿）

历史依据：源码 `dab7646`、配置 `61d7cc3701b2a42a`，原100题预测SHA-256 `17fdcf79dcf7ee09d5d14329fd272ee27d23db64d42ad4044890d691db59acf8`。BM25、上下文、循环与技能源码逐文件与该提交一致；固定索引指纹仍一致，两个SQLite均只读打开。未读.env、未调用模型、未改历史字节、未运行Qwen。这里的百炼结果来自根任务已完成的真实基线，本组只做事后读取审计。

原分组均为“工具返回未匹配完整参考答案”，人工复核后保留此历史分类，但百炼64的故障阶段改变。公开稿不展示原题、精确参考答案、预测答案或长原文；这些与完整实际请求放入私有附件。

| ID | 历史首个可证实问题 | 历史EM | 百炼基线EM / 状态及首故障 | 下一步 |
|---|---|---:|---|---|
| 960 | seq12重复首轮两query；无新证据后首次恢复加载即禁工具 | 0 | 0 / 有效弃答；候选论文仍未定位，后续重复动作停止 | 给恢复一次真实工具机会，验证论文定位策略 |
| 1035 | seq7检索表述混合城市与创业者公司的关系；后续重复 | 0 | 0 / 有效弃答；关系重述正确后仍未召回桥接实体 | 明确实体关系，再连接品牌/城市/推广证据 |
| 64 | 原seq39/46只取前5；核心与城市桥接片段实际第13/14 | 0 | 0 / 非空错答；seq20事件段失去可见性，seq21混淆揭幕日与遇难事件 | 保留事件段，区分揭幕纪念日与被纪念事件 |

三题历史合计47,759tokens、22工具、14HTTP；百炼合计67,757tokens、32工具、19HTTP。本组新基线均有有效模型响应；首次九题尝试中其他组发生的账户Arrearage阻塞不混入本组弃答；用户充值后的恢复由主任务另行记录。服务商、模型版本与实际payload不同，不能把两轮直接称为单因素模型优劣实验。百炼请求 `deepseek-v4-flash-0731`、`enable_thinking=false`，本组formal与引用检查均通过，EM均0。

## 离线检索对照边界

15个唯一历史query分别执行top5/top20，共30次；历史重复动作仍逐次保留在时间线。另有42次变体/实体续查，合计72次固定生产BM25搜索；44个历史前缀比较（原22次工具调用×2种深度）在doc/chunk/offset/text/score上全部精确一致。另5次明确标记的AND语料定位属于事后诊断，改变了表达式语义，不算生产BM25重放或在线Agent能力。

恢复技能原选择规则在stalled_searches非零时就可触发；960与1035的两个重复search同属一组，计数在组内0→1→2，下轮首次加载恢复技能即达到收尾条件。因此不能声称把触发阈值从2改成1就能解决；候选改动应是预算充足时为首次恢复保留一次工具机会，本轮未在线验证。

这证明历史结果可复现，没有证明当前查询一定能完成语义检索。参考答案辅助、已知文档日期辅助、正文实体续搜分别标记；其中960加入已知年份的后续query不能称为盲改进。全量神经索引未就绪，本组未作向量对照。

## ID 960

从一篇晚近十年代精神健康研究的作者贡献表，找出唯一没有承担研究方法工作的作者。需核对九名作者、六位同学院而跨校区、北半球研究地点、指名资助和另一篇青年抑郁研究的五作者重叠。

**历史判断。** R1/seq5构造的两条宽泛检索没有把核心论文送入前10；固定重放前20仍未找到。R2/seq12逐字重复两条查询、seq13/14均0新证据，是最早能直接证明的无进展动作。 seq16/17第一次加载恢复技能后立即seq18停滞收尾，实际seq21请求tool_choice=none；剩余24693tokens。程序给了恢复正文但没有恢复检索机会。

**原因边界。** OR词项评分、通用学术词较多且缺少稀有实体可能造成排名偏离；重放证明索引按既有规则稳定执行，不能据此断言BM25实现错误。

**离线对照。** 纯题面词的四个变体未在前20取得21800；参考答案辅助query把21800:3750:900推至第2。事后已知论文年份的query取得21800:0:900第9；标post_hoc_document_informed，不当作盲改查询成功。

### 条件与原文定位

这些文档是离线诊断重新定位的证据，不代表历史模型已经看到；原模型可见范围以下表真实API行为为准。

| 条件 | 核查状态 | 语料定位（Unicode左闭右开） |
|---|---|---|
| 论文时段/地点 | 支持 | `21800:[0,900)` |
| 九名作者及八位承担方法工作 | 支持 | `21800:[3317,5935)` |
| 六位同学院，分两校区 | 支持；若institution指大学，九位均属同一大学，需说明粒度 | `21800:[3317,5935)` |
| 资助授予指定作者 | 支持 | `21800:[2871,3210)` |
| 青年抑郁论文五作者交集 | 支持；以两文作者名单人工对齐 | `72555:[0,900)` |

### 历史每次API、决策和工具动作

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

### 百炼已完成基线对照

真实HTTP7次、工具12次、23567tokens，精确重复query4次；formal与引用错误均为空。
新模型曾open_document检查一个早期候选，还发起基于其项目实体的查询，因而比历史有更多结果驱动动作；但没有找到核心论文。之后重复查询达到限制，seq41为repeated_action，seq42为run_stopping；seq45收尾，原始模型给空答，导出空答，严格EM0。不能把多花tokens或多调用工具当作答题改善。


### 百炼基线每次API、决策和工具动作

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

## ID 1035

识别一家成立时间、城市同名关系、运动员代言、海岸演出和指定年度销售额共同约束的公司。创业者仅用于定位同名城市，其应用创业公司并非必然就是待找公司。

**历史判断。** R1/seq7动作说明和Q01将“创业者迁居城市与公司A同名”压成“创业者公司以城市命名”。这是可观察查询关系偏差；R3/seq21又逐字重复R2两条query，seq22/23均0新证据。 seq25/26恢复技能首次加载，seq27即search_stalled，seq30实际tool_choice=none；剩余20082tokens，非token耗尽。

**原因边界。** 多个实体关系被放进长OR查询可能让不相关商业/演出文段排前；不能仅由结果差断言索引坏了。

**离线对照。** 4个历史唯一query各前20和6个纯题面词变体各前20均未命中已定位核心文档。参考答案辅助query找回44626/72400/45782/51735；连接创业者城市和运动员出生年的AND定位也明确为事后诊断，非生产检索重放。

### 条件与原文定位

这些文档是离线诊断重新定位的证据，不代表历史模型已经看到；原模型可见范围以下表真实API行为为准。

| 条件 | 核查状态 | 语料定位（Unicode左闭右开） |
|---|---|---|
| 公司成立晚于给定年份 | 支持 | `44626:[0,750)` |
| 同名城市/创业者出生年代/随母迁居/应用业务 | 支持；post-hoc定位 | `66841:[0,1650)` |
| 运动员参与推广 | 支持；广告页面元数据日期异常，不能据此确认推广时段 | `51735:[0,900)` |
| 运动员出生年份 | 支持 | `82418:[1500,2400)` |
| 演出到场人数与政府官员 | 支持；North Coast地名不是原文明确beach词 | `72400:[1250,2200)` |
| 指定年度约十亿美元销售 | 部分：原文为本币31b；不能不查汇率就声称逐字USD一致 | `45782:[2850,3150)` |

### 历史每次API、决策和工具动作

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

### 百炼已完成基线对照

真实HTTP5次、工具8次、17820tokens，精确重复query3次；formal与引用错误均为空。
新模型首轮能正确列出公司—同名城市—创业者的关系，修正了历史公开检索措辞中的混合；但两条分支仍没有找到目标证据。后续切换演出/代言线索，又逐字重复，seq34因search_stalled收尾；真实模型输出空答，严格EM0。它说明关系重述正确本身还不足以解决召回。


### 百炼基线每次API、决策和工具动作

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

## ID 64

根据波黑大城市中的战难纪念物、艺术家出生年代和建成年代，回答被纪念事件发生的年份；需区分建成年和事件年。

**历史判断。** 原查询R1未送入关键纪念文档；更明确可定位的范围问题发生在seq39/46：同一原query历史top_k=5，固定BM25第13名是核心10744:0:900，第14名81158:750:900是城市排行桥接段。 原工具返回已有城市列表文档，但所取0:900与1500:2400并未完整包含前四名的中间段；模型也未open/find相邻正文。seq48因reserve_final_usage收尾，剩余7065tokens。恢复技能在seq25/26已加载并获得后续工具轮次，不能套用960/1035的首次加载即禁工具结论。

**原因边界。** 这证明原候选范围截断了可用证据，不证明扩大top_k后模型一定能解答。初轮的通用纪念物结果也不能单独判实现错误。

**离线对照。** 原query第13名直接包含核心身份、建造年和事件年；纯题面变体也在第4名返回同文档邻接片段、第9名返回核心首片。由正文设计者实体续搜后，出生年资料第1名出现。语义链在离线可闭合，未进行在线top20单变量复测。

### 条件与原文定位

这些文档是离线诊断重新定位的证据，不代表历史模型已经看到；原模型可见范围以下表真实API行为为准。

| 条件 | 核查状态 | 语料定位（Unicode左闭右开） |
|---|---|---|
| 纪念地点与城市 | 支持 | `10744:[0,900)` |
| 建成年早于阈值/设计者 | 支持 | `10744:[0,900)` |
| 遇难事件和年份 | 支持 | `10744:[750,1650)` |
| 2013人口城市/municipality前四 | 支持；来源以municipality口径列排名 | `81158:[750,1650)` |
| 艺术家出生年 | 支持；从已定位正文设计者实体离线续搜 | `50486:[0,127)` |

### 历史每次API、决策和工具动作

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

### 百炼已完成基线对照

真实HTTP7次、工具12次、26370tokens，精确重复query0次；formal与引用错误均为空。
新基线已在seq8第4名取回10744:0:900，seq13真实请求明确包含E4及被纪念事件年。因此这一轮已不属于“根本没召回”。seq20请求首次省去E4，保留E12=10744:5250:900的揭幕段；源码按题目词交集排序，E4始终11分，从seq10状态第7降至seq17状态第10，E12为13分。真实请求的变化与这一选择规则一致；随后seq21模型把“揭幕日期恰逢某起义纪念日”当成“碑本身纪念的遇难事件”，把另一个年份放进后续搜索。此后的请求没有再包含E4，虽然工具多次重新取回同一首片。

最终seq51只保留E28揭幕段、出生年E10及人口表尾部E30等；seq52原始模型自己输出错误年份，seq53解析/导出保留它，非程序把正确答案改错。E30位于81158:[1500,2400)，并不包含所称城市前四名；最终引用虽来自真原文，却不足以证明回答中的全部关系。首次可证明的程序侧选择损失是seq20；首次可见语义关系混淆是seq21。二者均有记录，但尚未通过单变量模型复测分离因果贡献。


### 百炼基线每次API、决策和工具动作

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

## E4单证据最终请求对照：真实响应已验证

针对新百炼64最终请求seq51，冻结context函数、seq47实际state和6个原始工具组重放出的控制messages与真实请求逐字相等。治疗只在同一证据位置将E7替换为已观察过的E4（10744:0:900），其余7个证据、顺序、技能、system/user、工具及采样参数保持一致；出生年证据E10仍保留。两者tool_choice均none、max_tokens均1024、enable_thinking均false。

冻结证据配额8758字符，控制使用8715、治疗8683；最终完整请求为14722/14716字符，均在同一24000预算内。E4早在seq8、15、22、29、36、45的真实工具返回中出现，因此没有注入未观察片段。选择E4是事后参考答案辅助诊断，标签字符串没有另加到模型输入；原文自身包含的事实属于已观察证据。

两份完整payload为私有`e4-counterfactual/control-request-private.json`和`treatment-request-private.json`，公开来源证明为`e4-counterfactual/provenance-public.json`。主任务已分别执行一次，实际发送body与准备文件完全一致；本子任务只做离线验证，未另发API。

| 最终请求条件 | HTTP/模型 | E4当前可见 | 模型非空回答 | 严格EM | final schema/生产原文引用/当前请求可见引用 | 新增实际tokens |
|---|---|---|---|---:|---|---:|
| control原选择 | 200 / 固定0731 | 否 | 是 | 0 | 全通过，引用E28/E10/E30 | 3,425 |
| treatment仅E7→E4 | 200 / 同模型 | 是 | 是 | 1 | 全通过，引用E4/E28/E10 | 3,474 |

这两条新调用合计6,899tokens；加入同一真实收尾前已用22,926tokens后，分别为26,351和26,400，均低于原30,000预算。prompt/completion分别3331/94和3357/117；没有把历史完整基线用量再次当本次新增消耗。两份原始响应及解析结果、精确答案、规范化和引用文本保存在私有附件，公开数值见`e4-counterfactual/paired-results-public.json`。

控制仍将揭幕纪念日关联的事件当作所问事件；治疗转而引用E4中的实际遇难事件并匹配参考答案。本对照支持“在这个固定最终请求中，保留已经观察到的关键事件片段可以纠正最终答案”。每个条件只有一次响应，而且E4是事后辅助选择；它不证明完整Agent能自主保留E4、不证明一般题目的准确率提升，也不等同部署了通用选择策略。原历史与本次完整百炼基线的EM仍为0，不能用这个局部pair的EM1替换它们。

## 复现与附件清单

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
