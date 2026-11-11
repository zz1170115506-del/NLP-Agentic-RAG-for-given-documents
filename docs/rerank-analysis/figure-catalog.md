# 图目录

## figure-01-main-comparison.pdf / .png

- Purpose: 区分候选覆盖变化与同池重排变化。
- Data source: metrics.json/groups，原始运行路径和 manifest 校验值见 provenance。
- Variables: 横轴运行与配置；纵轴候选证据命中率、最终证据命中率和首证据 MRR。
- Caption: 固定样本，标注 k 与每组有效 n；误差线为已观察主题重抽样的 95% 条件区间。
- Key observation: dev:B−dev:A: +/=/− 0/10/0; dev:C−dev:B: +/=/− 1/9/0; dev_d:B−dev_d:A: +/=/− 0/10/0; dev_d:C−dev_d:B: +/=/− 1/9/0; heldout:B−heldout:A: +/=/− 1/9/0; heldout:C−heldout:B: +/=/− 0/9/1; heldout_d:B−heldout_d:A: +/=/− 1/9/0; heldout_d:C−heldout_d:B: +/=/− 0/9/1; dev_d:C−dev:C: +/=/− 0/10/0; heldout_d:C−heldout:C: +/=/− 0/10/0。
- Interpretation: 先检查候选覆盖，再用 C−B 判断排序；不能把候选扩大的效果归给重排。
- Decision: 结合配对改善/退化及耗时，在开发样本提出候选配置，再用保留样本复核。
- Caveats: 部分标签、少量人工诊断题；误差线不是总体置信区间。

## figure-02-rank-cost.pdf / .png

- Purpose: 找出具体变化题目，并检查排序代价。
- Data source: per-query.csv；每个格子和散点对应一次保存的运行。
- Variables: 热图颜色为倒数排名，格内文本为实际排名；miss 表示候选池中未含标注范围；灰色为不存在/失败的组合。
- Caption: 散点是单次预热后查询耗时，红线为中位数；不画重复运行误差条。
- Key observation: 对照中的进入/掉出数量为 dev:B−dev:A: +/=/− 0/10/0; dev:C−dev:B: +/=/− 1/9/0; dev_d:B−dev_d:A: +/=/− 0/10/0; dev_d:C−dev_d:B: +/=/− 1/9/0; heldout:B−heldout:A: +/=/− 1/9/0; heldout:C−heldout:B: +/=/− 0/9/1; heldout_d:B−heldout_d:A: +/=/− 1/9/0; heldout_d:C−heldout_d:B: +/=/− 0/9/1; dev_d:C−dev:C: +/=/− 0/10/0; heldout_d:C−heldout:C: +/=/− 0/10/0，具体 ID 在 metrics.json/comparisons。
- Interpretation: 相同均值可能掩盖不同题目的得失；先检查掉出题目，再检查是否发生窗口或预算截断。
- Decision: 选择最常见的失败原因或实际主要耗时因素，保持其他条件固定进行下一轮。
- Caveats: 回放复用检索耗时，总时间是组合估计；单次样本不足以推断尾延迟。

## figure-03-integrated-latency.pdf / .png

- Purpose: 以统一 search 的直接计时复核第二轮优化的系统成本。
- Data source: integrated-summary.json 的 per_query_medians 与来源哈希。
- Variables: 左侧每题 B/C30/D10 三次技术重复的中位数，红菱形为题目中位数的总体中位数；右侧逐题 D10/C30 比值。
- Key observation: D/C 配对比值中位数 0.547614，10/10 题更快；各配置的输出均与其冻结参考一致。
- Interpretation: 在已常驻模型和相同池的本机执行条件下，减少评分候选降低了实际查询耗时。
- Decision: 以直接计时描述性能收益；D10 保持为可选配置，不能用速度收益抵消未修复的证据退化。
- Caveats: n=10 查询，每题 3 次为技术重复；同一进程、单设备，没有总体置信区间或跨会话性能保证。
