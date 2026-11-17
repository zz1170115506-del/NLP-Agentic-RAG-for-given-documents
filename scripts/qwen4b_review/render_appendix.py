"""Render descriptive tables and a paired nine-question figure from the completed audit."""
import argparse
import hashlib
import json
from pathlib import Path


CONTRASTS = {'bm25_vs_int8': 'BM25 → 256维 int8', 'native_vs_prefix': '原始2560维 → 前256维浮点',
             'prefix_vs_int8': '前256维浮点 → 256维 int8', 'native_vs_int8': '原始2560维 → 256维 int8'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def printable_fraction(n, d):
    return f'{n}/{d} ({100*n/d:.1f}%)' if d else '0/0'


def values(events, contrast):
    stages = [event['ranking_comparison'][contrast] for event in events]
    return (sum(e['overlap'] for e in stages), sum(e['k'] for e in stages),
            sum(e['top1_same'] is True for e in stages), sum(e['top1_same'] is not None for e in stages),
            sum(e['sum_absolute_rank_change'] for e in stages), sum(e['compared_pool_rows'] for e in stages))


def plot(cases, search, base, candidate, dest):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import numpy as np

    matrix = []
    for qid in cases:
        cells = []
        for name in CONTRASTS:
            n, d, *_ = values(search[qid], name)
            cells.append(n / d if d else np.nan)
        matrix.append(cells)
    figure = Figure(figsize=(10, 5.8), layout='constrained')
    FigureCanvasAgg(figure)
    ax, cost = figure.subplots(1, 2, width_ratios=(1.2, 1))
    ax.imshow(matrix, vmin=0, vmax=1, cmap='Blues', aspect='auto')
    for row, cells in enumerate(matrix):
        for col, frac in enumerate(cells):
            ax.text(col, row, f'{frac:.0%}' if np.isfinite(frac) else '—', ha='center', va='center',
                    color='white' if frac > .62 else '#162b40', size=9)
    ax.set_xticks(range(4), ['BM25 vs\nINT8', 'Full vs\n256-float', '256-float\nvs INT8', 'Full vs\nINT8'])
    ax.set_yticks(range(len(cases)), cases)
    ax.set_ylabel('Validation question ID')
    ax.set_title('A. Top-k membership overlap', loc='left', fontweight='bold', size=11)
    for row, qid in enumerate(cases):
        before = base[qid]['reported_usage']['total_tokens'] / 1000
        after = candidate[qid]['reported_usage']['total_tokens'] / 1000
        cost.plot([before, after], [row, row], color='#8794a0', linewidth=1.3, zorder=1)
        cost.scatter(before, row, s=40, color='#b45e1f', marker='o', label='Sparse v2' if row == 0 else None, zorder=2)
        cost.scatter(after, row, s=38, color='#09647b', marker='D', label='Qwen rerank' if row == 0 else None, zorder=3)
    cost.set_ylim(len(cases)-.5, -.5)
    cost.set_yticks(range(len(cases)), cases)
    cost.set_xlabel('Reported API input + output tokens (thousands)')
    cost.set_title('B. Full QA cost per question', loc='left', fontweight='bold', size=11)
    cost.grid(axis='x', color='#e6e8ea', zorder=0)
    cost.legend(loc='upper center', bbox_to_anchor=(.5, -.12), ncol=2, frameon=False)
    figure.savefig(dest, dpi=160, facecolor='white')


def render(data, paths, out):
    base = {c['id']: c for c in data['baseline_sparse_v2']['cases']}
    candidate = {c['id']: c for c in data['candidate']['cases']}
    bound = data['qwen_search_binding']
    searches = bound['cases']
    ids = list(base)
    rows = ['# 九题统计附录', '', '每题对应两条独立的完整问答轨迹。输入为同一组九道历史失败题，每种配置每题一次。前后检索动作可随模型回复变化。单次检索内的压缩比较，则固定该次查询和同一份 BM25 候选再比较不同表示。', '',
            '## 完整问答的配对结果', '', '| 题号 | 答案匹配（旧→新） | 非空（旧→新） | API（旧→新） | 工具（旧→新） | 问答总 token（旧→新） | 新输入／输出／其中缓存输入 |', '|---|---|---|---:|---:|---:|---:|']
    for q in ids:
        b, a = base[q], candidate[q]
        t = a['reported_usage']
        rows.append(f"| {q} | {b['em']}→{a['em']} | {int(b['has_answer'])}→{int(a['has_answer'])} | {b['api_calls']}→{a['api_calls']} | {b['tools']}→{a['tools']} | {b['reported_usage']['total_tokens']:,}→{t['total_tokens']:,} | {t['prompt_tokens']:,}／{t['completion_tokens']:,}／{t['cached_prompt_tokens'] if t['cached_prompt_tokens'] is not None else '未返回'} |")
    paired = {(b, a): sum(base[q]['em'] == b and candidate[q]['em'] == a for q in ids) for b in (0, 1) for a in (0, 1)}
    rows += ['', f"配对变化为原错→新对 {paired[0,1]}，原对→新错 {paired[1,0]}，两次均对 {paired[1,1]}，两次均错或弃答 {paired[0,0]}。一条轨迹内多次请求、一次请求里的多行结果共享题目及查询，因此没有用这些行扩大独立样本量。九题是目的性选样，未采集多次重复运行，无法从这项设计估计独立题集的置信区间或稳定的模型优劣。", '',
             '## 同池排序变化', '', '每次调用的 k 取工具实际返回数。集合重合把两种排名前 k 名的共同片段数除以 k，再在所列范围内按位置累加；数值只度量排序一致性。平均位移以所有池内片段在两个完整排序中的绝对名次差之和，除以这些“查询 × 片段”记录数。', '',
             '| 同次查询、同池比较 | 前 k 重合 | 第1名相同 | 绝对名次位移总和／池行数 | 平均位移 |', '|---|---:|---:|---:|---:|']
    all_searches = [s for q in ids for s in searches[q]]
    for contrast, label in CONTRASTS.items():
        n, d, top, trials, dist, pool = values(all_searches, contrast)
        rows.append(f'| {label} | {printable_fraction(n,d)} | {printable_fraction(top,trials)} | {dist}/{pool} | {dist/pool:.3f} |')
    rows += ['', '| 题号 | 搜索次数 | BM25→int8 | 全维→前缀浮点 | 前缀浮点→int8 | 全维→int8 |', '|---|---:|---:|---:|---:|---:|']
    for q in ids:
        cells = [printable_fraction(*values(searches[q], k)[:2]) for k in CONTRASTS]
        rows.append('| ' + ' | '.join([q, str(len(searches[q])), *cells]) + ' |')
    rows += ['', '九题中每次搜索的 BM25 候选池由全量语料索引生成，向量排序只调整池内顺序。原始浮点和前缀浮点仅用于同池诊断，真实返回给问答模型的是压缩排序。三种向量表示未各自从头运行整套问答，因此重合率无法推导单独降维或量化导致的 EM 变化。重复查询按真实次数计入。', '', '## 主要输入的 SHA-256', '', '| 对象 | SHA-256 |', '|---|---|']
    rows += [f'| {name} | `{sha(path)}` |' for name,path in paths.items()]
    rows += ['', '完整坐标及原文进入模型前后的可见性和工具约束核对见同次运行的 comparison-public.json。原文、提问、答案及长轨迹保存在私有证据中。']
    out.mkdir(parents=True, exist_ok=True)
    (out/'stats-appendix.md').write_text('\n'.join(rows)+'\n')
    figures = out/'figures'
    figures.mkdir(exist_ok=True)
    plot(ids, searches, base, candidate, figures/'paired-nine.png')
    n,d,*_ = values(all_searches,'prefix_vs_int8')
    (out/'figure-catalog.md').write_text(f'''# 九题比较图说明

![同池排名的重合与逐题真实用量](figures/paired-nine.png)

左侧每格对应一个题号的全部真实搜索和一组同池排名比较，显示前 k 名成员重合的百分比，分母为该题实际返回结果位置总数。原始向量为 2,560 维，前缀浮点与 int8 均为 256 维。前缀浮点与 int8 的总体重合为 {printable_fraction(n,d)}。颜色越深表示前 k 名的组成越接近，不能据此判定回答正确。

右侧每一行对应同一道完整问答，圆点为历史 sparse v2，菱形为本次 Qwen 候选重排，横轴以千为单位表示服务商报告的输入和输出 token 之和。相连点之间的距离取决于问答路径与实际输入长度。两幅图均为已观测值，每种配置每题一次，没有重复运行可用于画误差条。准确分子、分母、逐题原始值和文件校验值见[统计附录](stats-appendix.md)。
''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('comparison', 'baseline', 'candidate', 'coordinates', 'output'):
        parser.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args()
    paths={'原稀疏 v2 预测':args.baseline, '本次预测':args.candidate, '逐事件独立记录':args.candidate.parent/'events.jsonl',
           '各次检索排名':args.candidate.parent/'retrieval.jsonl','事前冻结的诊断坐标':args.coordinates,'本次独立审计':args.comparison}
    render(json.loads(args.comparison.read_text()), paths, args.output)
