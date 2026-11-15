# 验证题 1155 逐题复盘

寻找属于指定历史地标的古村落，同时核对建村年代、步道长度、机场空中距离和时间截点。

历史定位：`outputs/acceptance-validation100-v1/validation_prediction.jsonl`，按ID定位；下表seq与`trajectory[index]`的index相同，零起算。所有坐标均为Python Unicode字符，右端不含。

## 可证实的结论

候选与步道信息可见，但重复查询触发提前收尾；离线找到年代支持及冲突，机场距离仍未闭环。

首次问题：seq12完整重复首轮两条查询，而seq11已见候选村落和步道片段；seq13–14新增证据均为0，停滞计数升至2。seq18在仍有大量预算时禁用工具收尾。

工具4次（全部search，open/find均0），真实API3次，总usage=8679。收尾前余额：{'tokens': 24555, 'tools': 20, 'steps': 10, 'stalled_searches': 2}。

## 按序时间线

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

## 下一步单变量与未确认项

只替换第二轮第一条重复查询为历史候选名+缺失年代，其他设置不动；分别测新片段是否召回、是否进入实际请求。机场距离和年代来源冲突若仍未解决，仍可能弃答；没有已证实EM提升。

百炼初次失败尝试：首请求HTTP400 Arrearage，工具0次、usage0；没有模型答题过程，EM未测。充值后有效基线另见追加章节；本报告生成脚本不执行模型调用。

<!-- BAILIAN-APPENDIX -->

## 充值后百炼基线对照

百炼本次输出非空，但严格EM仍为0。固定语料把输出候选与参考候选放在不同遗址，未发现可把两者视为拼写或别名的证据。最终引用里的同名步道长度与题意区间不符，机场距离仅以宽泛地区描述代替验证。属于条件未核实的候选输出；解析、引用定位和导出均保留原答。

本次有效运行：配置`900fc3b95b775d2a`，5个HTTP200、8次search、usage总计16671；严格EM=0。没有open/find，所有search使用配置默认top5。

首次问题：seq19重复一条宽泛查询；此前实际seq18已含另一遗址候选及其步道长度。seq36原始回答仍将该候选视为符合全部线索，缺少机场距离支持且忽略步道长度不合。

### 初次账户错误尝试：全部事件

|seq/index|事件|定位与结果|
|---|---|---|
|0|run_start|启动baseline；config_id=900fc3b95b775d2a；sparse，固定语料。|
|1|user|Question(id, question)进入Agent；原题仅保留在私有附件。|
|2|context|上下文选择；移除历史组0，选证据0，2354字符。该事件是程序摘要，实际输入以随后api_attempt为准。|
|3|request|程序准备请求事件；不把此副本当成实际模型输入证据。|
|4|api_attempt|首请求HTTP400，Arrearage；无模型答题回复，usage_unknown=True。实际输入只认本事件request.messages。|
|5|error|服务商账户错误被记录；没有Agent答题决定。|
|6|run_end|provider_error结束，reported_tokens=0，工具0，EM未测；不与充值后运行拼接。|

### 充值后有效运行：全部事件

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

### 本次逐条件语义核查

|条件|判定|支持/反证定位|缺口与实际可见性|
|---|---|---|---|
|条件1（对应历史条件表）|不同候选；别名关系无支持|支持 doc69407[11620:11912]; 反证 doc34133[753:922]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件2（对应历史条件表）|部分相关，起止语义不同|支持 doc44164[1484:1626]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件3（对应历史条件表）|所引用同名步道出现反证|反证 doc69407[11921:12125]|完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
|条件4（对应历史条件表）|未证明||完整条件语义与逐字原文仅见加密附件；不能把工具返回等同于实际模型可见。|
### 可复测项及解释边界

保持预算与检索方法不变，在历史或新运行的同一候选节点只替换一条重复查询为“该候选+尚缺距离/步道条件”核查，分别报告找回反证与是否改变输出；不把尚未执行的效果写作提升。

本次是独立完整运行；不能把历史或事后离线查询得到的证据冒充为这次API输入。
