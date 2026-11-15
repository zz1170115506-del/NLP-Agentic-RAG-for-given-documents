# 验证题 788 逐题复盘

识别清真寺，核对竣工年代、容量、室内面积，与另一清真寺及医院的步行关系和成立年代。

历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。

## 可证实的结论

主要指标可见，关键条件片段未保留；离线还发现面积来源冲突及候选医院年代反证，不能认定所有条件原已满足。

首次问题：seq15在候选主要指标已进入seq13请求后继续重复该指标；程序层更明确的问题为seq29遗漏seq25第8名返回的竣工年份E20。

工具12次（全部search，open/find均0），真实API7次，总usage=26364。收尾前余额：{'tokens': 7086, 'tools': 12, 'steps': 6, 'stalled_searches': 3}。

## 按序时间线

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

## 下一步单变量与未确认项

优先只保留已观察E20，检查该条件进入实际请求后是否被确认；不同时改查询、医院假设、预算。下一独立对照可核查候选医院成立年，观察是否避免把扩建年当创立年。

百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。

<!-- BAILIAN-APPENDIX -->

## 充值后百炼基线对照

百炼仍弃答，且再次出现可直接定位的证据保留问题：完工年份片段在seq15/24/31/39工具结果出现，实际seq22及随后请求均未保留；邻近对象片段也未保留。最终模型据其实际输入说缺年份是可解释的，但固定语料仍存在面积口径冲突与邻近医院成立时间缺口，因此保留年份本身尚不能证明全部条件或保证答对。

本次有效运行：配置`900fc3b95b775d2a`，6个HTTP200、11次search、usage总计22139；严格EM=0。没有open/find，所有search使用配置默认top5。

首次问题：seq15已返回完工年份与邻近对象，紧接实际seq22却排除E12与E8；seq23因此继续查询同一缺失条件。

### 初次账户错误尝试：全部事件

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

### 充值后有效运行：全部事件

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

### 本次逐条件语义核查

|条件|判定|支持/反证定位|缺口与实际可见性|
|---|---|---|---|
|条件1（对应历史条件表）|新工具已回，实际请求遗失|支持 doc70534[622:642]; 支持 doc70534[1930:2032]; 支持 doc56202[3638:3756]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件2（对应历史条件表）|新实际输入有支持|支持 doc96357[297:341]; 支持 doc70534[643:673]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件3（对应历史条件表）|新实际输入有支持，固定原文存在口径冲突|支持 doc96357[245:295]; 反证 doc70534[674:697]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件4（对应历史条件表）|新工具局部出现，实际输入未保留；条件仍不完备|支持 doc6743[409:431]; 支持 doc95802[120:182]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件5（对应历史条件表）|新工具局部出现，实际输入未保留；条件仍不完备|支持 doc56188[875:932]; 反证 doc57904[586:735]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
### 可复测项及解释边界

只把新运行seq22一个低相关片段换为已观察E12，保持预算与其他输入固定，可测年份使用/继续查询选择；完整答案仍需另证面积口径、步行关系及医院成立年。不得将附近医院扩建年误当创办年，不应因容量/面积两项匹配就自动答题。

本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。
