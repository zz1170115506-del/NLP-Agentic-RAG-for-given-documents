# 验证题 1066 逐题复盘

识别一部短片，并核对年份、片长、乡村新教师情节、导演第一学历、剪辑师与指定战争片的关联。

历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。

## 可证实的结论

曾出现参考文字不等于最后仍有候选证据。关键片段后续被上下文选择丢失，且电影关联条件尚未全部验证。

首次问题：seq18构建上下文、seq20实际请求首次遗漏E12；E12仍在完整state，seq13曾可见，seq14也已发出包含候选及导演的查询。

工具8次（全部search，open/find均0），真实API5次，总usage=17843。收尾前余额：{'tokens': 15590, 'tools': 16, 'steps': 8, 'stalled_searches': 3}。

## 按序时间线

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

## 下一步单变量与未确认项

最小对照仅优先保留历史已经观察到的E12，维持同一证据字符预算。离线已证实seq20/29/37可重入且总字符<24000；不同时加入新导演/剪辑证据。真实模型回答和EM尚未测试。

百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。

<!-- BAILIAN-APPENDIX -->

## 充值后百炼基线对照

百炼本次在两个相同宽泛查询各重复一次后弃答。候选定位页从未进入这次工具结果或实际模型输入，因此本次首要问题在候选发现/查询恢复；历史那次则已经发现候选、后来从输入中消失。两条轨迹不能混成同一种“看见答案还不答”。原始模型直接空答，解析和导出没有清空非空内容。

本次有效运行：配置`900fc3b95b775d2a`，3个HTTP200、4次search、usage总计9082；严格EM=0。没有open/find，所有search使用配置默认top5。

首次问题：seq14把首轮两条查询原样重发，seq15/16无新证据；seq20 search_stalled收尾时仍余24193 tokens、20工具、10步骤。

### 初次账户错误尝试：全部事件

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

### 充值后有效运行：全部事件

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

### 本次逐条件语义核查

|条件|判定|支持/反证定位|缺口与实际可见性|
|---|---|---|---|
|条件1（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc61101[1546:1578]; 支持 doc61101[577:599]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件2（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc61101[601:615]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件3（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc26814[66:149]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件4（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc26814[330:726]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件5（对应历史条件表）|本次未观察支持；历史/离线原文保留供对照|支持 doc61101[222:247]; 支持 doc77139[80:193]; 支持 doc77139[2369:2533]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
### 可复测项及解释边界

1066历史seq20严格E9→E12单片段替换对照用于检验“保留已观察候选”影响，由主任务以相同服务商适配执行；它不是本次百炼seq20（本次seq20是finalization）的替换，也不是完整新基线重跑。另可针对新运行单独替换一次重复查询，仅测候选发现，不与保留片段实验合并。

本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。

<!-- RETENTION-PAIR-APPENDIX -->

## 1066 严格单片段保留：真实下一动作对照

保留历史候选片段后，处理组第二条查询使用候选及导演，对照组第二条仍是问题词泛搜。固定BM25离线执行显示：对照组第二条也找回doc26814:0（排名2），处理组排名1，并额外在排名4返回doc61101:1500的年份片目。不能说对照组未找到候选。两边第一条相同且前5均无该候选；这轮都没有片长和剪辑师战争片时长的完整支持。只能确认局部下一动作与检索排序差异，终局EM未测。

固定节点是历史轨迹api seq20。对照请求为原始完整请求；处理请求只把证据列表第7位E9换为此前已经观察到的E12(doc26814:0)。不是充值后新基线的seq20，也不是重新选取全部证据。原question、tools、其他八片段及顺序、非证据状态均不变。

两臂统一改为百炼0731、enable_thinking=false，去掉旧thinking字段。已用完整JSON对象比较证明实际请求只作了这些相同适配；max_tokens均1024、证据预算9568字符、消息上限24000字符。处理片段稍短，实际输入字符及prompt token可不同；预算一致不等于输入长度相同。

没有新增检索证据进入API输入，未用标签选片段。两臂各只有一次API调用、一次模型下一动作回复；后续工具调用仅由离线复放执行，没有把结果回传模型，也没有运行到最终答案。

|臂|HTTP/响应身份|prompt/completion/total token|两条查询结果|终局EM|
|---|---|---|---|---|
|control|200/deepseek-v4-flash-0731|4074/105/4179|第二条候选排名2|未测|
|treatment|200/deepseek-v4-flash-0731|4023/117/4140|第二条候选排名1；年份片目排名4|未测|

### 两臂完整事件表

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

### 逐条件解释

两臂的候选页均覆盖乡村学校教师情节以及导演学习经历；学习经历措辞仍不足以精确证明题目所问的第一学历。处理组多返回年份片目，但没有因此获得片长或完整剪辑师链条。命中现有注释片段不等于该条件已经严格成立，尤其是带有未解决限定的学历条件。

这是一次局部、单样本对照。temperature相同也不保证模型服务完全无随机差异；没有重复样本或完整续跑，不能外推出准确率改善、显著性、召回率全局提升或预算节省。四条离线查询的耗时受缓存和执行顺序影响，不作为两臂速度优劣结论。
