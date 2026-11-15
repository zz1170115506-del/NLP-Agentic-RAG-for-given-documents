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
