# ID 231：百炼独立基线追加复盘

这不是旧提供商轨迹的续写或同一实验条件。

新百炼运行3次HTTP200，使用4次工具、9687 token，以search_stalled进入最后轮次后由模型直接空答，解析/导出一致。与旧轨迹的区别是：本次原工具返回中没有参考串，也没有旧doc43835:0片段；不能套用旧E9在state到context丢失的诊断。已有定向hook严格要求片段先被观察到，因此对此运行是空操作；检索路线需要另行单变量复测，不应偷加旧轨迹的证据。

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
