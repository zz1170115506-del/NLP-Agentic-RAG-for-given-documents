# 第二类三题逐题复盘（可并入总回传）

公开版仅概述题意和证据坐标，不包含原题全文、原始标签或长篇原文。原题、规范化标签、原始API/工具正文及详细中文叙述均单独保留在private。

旧历史条件：冻结代码 `dab7646158fef729c3bf3e0f37b7f302727fc568`、config `61d7cc3701b2a42a`、官方兼容请求模型名与实际返回模型名有区别。新百炼条件：基线代码 `8c8e545126e329919d2c16b18cacea6e139ebb29`、config `900fc3b95b775d2a`，请求与成功响应均为 `deepseek-v4-flash-0731`。两者是不同运行，不能把相同ID下的证据编号或故障类别直接互换。

以下每张时间线使用原始0起点sequence，列出所有记录事件，因此每一次真实API、模型assistant决策、工具调用都各有一行。完整旧历史共123事件，当前有效百炼三题共116事件；合计239事件、29次API尝试、29次assistant响应、46次工具返回。旧58账户中断的23事件独立保存，不计入这239条有效历史。

| 题目ID | 旧EM | 新百炼EM | 新有效状态 | 新报告token/工具/API |
|---|---:|---:|---|---|
| 231 | 0 | 0 | insufficient_evidence | 9687 / 4 / 3 |
| 390 | 0 | 0 | insufficient_evidence | 23082 / 10 / 6 |
| 58 | 0 | 0 | insufficient_evidence | 19081 / 8 / 5 |

## ID 231

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

## ID 390

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

## ID 58

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

## 共性结论与验证范围

旧运行的字面证据确实完整到达内部state，随后因快照配额、整项跳过和整组历史删除而对模型不可见；15个原请求已逐条重放，与真实api_attempt.request.messages全等。两种hook在30个离线对照构造上也完全一致。此处的“成功”只指证据进入构造请求，不能当作模型回答成功。

通用对照的边界已实际检查：聚焦open/find窗口优先只恢复旧58最后一次定位片段；每doc最高词重合片段优先也仅在旧58最后阶段恢复短窗口，对旧231/390无效。新百炼231和58未取得相同目标，390最后已看到歌名，因此历史保留实验不能被包装成对三个新完整运行的统一修复。

成对实时诊断需另存双方实际百炼请求/响应，并在相同提供商映射后比较。引用核验使用原成功工具历史、该臂真实messages、原state及只读语料；分别记录raw final、解析/导出、引用有效性、规范化EM和语义核验。来源通过不代表满足全部题意，尤其390还必须确认合辑第三轨。前文EM表只统计完整旧/新基线；下文单列已完成的成对API结果，不能混入盲测基线得分。

可复现文件：`group-b-replay-summary.json`、`bailian-addendum.json`、`verification-result.json`、`ARTIFACT_HASHES.json`；成对输入及核验方法在`../paired-final-diagnostics/README.md`。私密原始记录和payload不随本公开正文展开。


## 历史最终轮次的真实API成对结果

在上述239个原始轨迹事件之外，本节另列6个真实诊断API记录及6个对应assistant响应字段，共12行；没有为它们伪造历史sequence，也没有新工具调用。

# 历史最终轮次：三组成对API结果

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
