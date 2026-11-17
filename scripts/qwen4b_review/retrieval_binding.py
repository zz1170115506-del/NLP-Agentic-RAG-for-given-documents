"""Join actual tool results to the separately saved Qwen ranking diagnostics."""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path


METHOD = 'qwen4b_candidates'
MODEL = 'Qwen/Qwen3-Embedding-4B'
REVISION = '5cf2132abc99cad020ac570b19d031efec650f2b'


def groups(path, name):
    result = defaultdict(list)
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            result[row['id'], row['attempt_id']].append(row[name] if name else row)
    return result


def ordered_chunks(rankings, rank_name):
    if not rankings:
        return []
    if not all(rank_name in r for r in rankings):
        raise ValueError('Missing ' + rank_name + ' comparison ranks')
    if sorted(r[rank_name] for r in rankings) != list(range(1, len(rankings) + 1)):
        raise ValueError(rank_name + ' order is not a complete permutation')
    return [r['chunk_id'] for r in sorted(rankings, key=lambda r: r[rank_name])]


def compute_overlap(first, second, k):
    size = min(k, len(first), len(second))
    if not size:
        return {'k': 0, 'overlap': 0, 'top1_same': None, 'compared_pool_rows': 0, 'sum_absolute_rank_change': 0}
    ranks = {chunk: rank for rank, chunk in enumerate(second)}
    distance = sum(abs(rank - ranks[chunk]) for rank, chunk in enumerate(first))
    return {'k': size, 'overlap': len(set(first[:size]) & set(second[:size])), 'top1_same': first[0] == second[0],
            'compared_pool_rows': len(first), 'sum_absolute_rank_change': distance}


def overlap_targets(pool, coords):
    found = []
    for target in coords:
        matches = []
        for row in pool:
            if row['doc_id'] != target['doc_id']:
                continue
            doc, left, length = row['chunk_id'].rsplit(':', 2)
            if doc != row['doc_id']:
                raise ValueError('Chunk identifier differs from document identifier')
            start, end = int(left), int(left) + int(length)
            if end > target['offset'] and start < target['end']:
                matches.append({'chunk_id': row['chunk_id'], 'overlap_chars': min(end, target['end']) - max(start, target['offset']),
                                **{k: row[k] for k in ('bm25_rank', 'full_rank', 'prefix_rank', 'int8_rank')}})
        if matches:
            found.append({'doc_id': target['doc_id'], 'offset': target['offset'], 'end': target['end'], 'overlapping_pool_chunks': matches})
    return found


def check(ok, what):
    if not ok:
        raise ValueError('Retrieval identity check failed: ' + what)


def verify_search(run_row, tool, coords):
    diag = run_row['diagnostics']
    core = diag['qwen4b']
    model = core['encoder_identity']
    check(diag['status'] == 'success' and diag['method'] == run_row['method'] == METHOD, 'success/method')
    check(core['fallback'] is False and model['snapshot_verified'] is True, 'no fallback/pinned weights')
    check((model['model_id'], model['revision'], model['native_dimension'], core['dimension']) == (MODEL, REVISION, 2560, 256), 'model identity or dimensions')
    check(core['compression'] == 'mrl-prefix-l2-symmetric-int8-per-row-float32-scale-v1', 'int8 formula')
    envelope = json.loads(tool['content'])
    if not envelope['ok']:
        raise ValueError('Expected an executed successful search call')
    query = envelope['data']['query']
    real_hits = envelope['data']['results']
    query_hash = hashlib.sha256(query.encode()).hexdigest()
    check(query_hash == run_row['query_sha256'] == core['query_sha256'], 'actual query binding')
    check(all(h['method'] == METHOD for h in real_hits), 'method in actual tool response')
    actual_pairs = [[h['doc_id'], h['chunk_id']] for h in real_hits]
    check(actual_pairs == diag['final_ids'], 'final identities in real tool output')
    found = [h['chunk_id'] for h in real_hits]
    check(found == run_row['returned_chunk_ids'], 'returned chunk order')
    ranking = core['rankings']
    check(len(ranking) == core['pool_size'] == diag['candidate_count'] <= diag['candidate_depth'], 'pool size')
    check(len({h['chunk_id'] for h in ranking}) == len(ranking), 'pool contains duplicate chunks')
    bm25 = ordered_chunks(ranking, 'bm25_rank')
    int8 = ordered_chunks(ranking, 'int8_rank')
    native = ordered_chunks(ranking, 'full_rank')
    prefix = ordered_chunks(ranking, 'prefix_rank')
    check(bm25 == [chunk for _, chunk in diag['candidate_ids']], 'BM25 pool order')
    physical = sorted(diag['routes']['sparse']['hits'], key=lambda h: h['rank'])
    check([[h['doc_id'], h['chunk_id']] for h in physical] == diag['candidate_ids'], 'sparse route candidates')
    for source, order in [('full', native), ('prefix', prefix), ('int8', int8)]:
        scores = [v[source + '_score'] for v in ranking]
        check(all(math.isfinite(s) and -1.00001 <= s <= 1.00001 for s in scores), source + ' cosine limits')
        ordered = sorted(ranking, key=lambda v: (-v[source + '_score'], v['bm25_rank']))
        check(order == [v['chunk_id'] for v in ordered], source + ' score order and tie breaks')
    indexed = {r['chunk_id']: r for r in ranking}
    for hit in real_hits:
        source = indexed[hit['chunk_id']]
        meta = hit['metadata']
        check(meta['bm25_rank'] == source['bm25_rank'] and meta['qwen4b_rank'] == source['int8_rank'], 'tool hit rank metadata')
        check(hit['score'] == source['int8_score'], 'actual returned similarity score')
    check(core['compressed_cache_bytes'] == core['cache_entries'] * (core['dimension'] + 4), 'compressed vector payload bytes')
    check(core['reference_cache_bytes'] == core['cache_entries'] * 2560 * 4, 'float cache payload bytes')
    check(int8[:run_row['top_k']] == found, 'actual response vs int8 order')
    k = run_row['top_k']
    changes = {'bm25_vs_int8': compute_overlap(bm25, int8, k), 'native_vs_prefix': compute_overlap(native, prefix, k),
               'prefix_vs_int8': compute_overlap(prefix, int8, k), 'native_vs_int8': compute_overlap(native, int8, k)}
    return {'search_index': run_row['search_index'], 'tool_sequence': tool['sequence'], 'query_sha256': query_hash,
            'requested_k': k, 'returned_k': len(found), 'candidate_count': len(ranking), 'candidate_depth': diag['candidate_depth'],
            'elapsed_retrieval_seconds': diag.get('total_seconds'), 'encoded_passages': core['encoded_passages'],
            'cache_hits': core['cache_hits'], 'compressed_cache_bytes': core['compressed_cache_bytes'],
            'reference_cache_bytes': core['reference_cache_bytes'], 'encoding_seconds': core['encoding_seconds'],
            'ranking_seconds': core['ranking_seconds'], 'ranking_comparison': changes,
            'historical_anchors_in_candidate_pool': overlap_targets(ranking, coords)}


def verify_retrieval(run_dir, records, coordinates):
    run_dir = Path(run_dir)
    attempts = groups(run_dir / 'events.jsonl', 'record')
    logs = groups(run_dir / 'retrieval.jsonl', None)
    storage = Counter()
    comparisons = defaultdict(Counter)
    selected = set()
    by_case = {}
    for record in records:
        matching = [key for key, traj in attempts.items() if key[0] == record['id'] and traj == record['trajectory']]
        check(len(matching) == 1, 'attempt event stream must match exported prediction bytes structurally')
        attempt = matching[0]
        selected.add(attempt)
        executed = [e for e in record['trajectory'] if e.get('role') == 'tool' and e.get('name') == 'search' and json.loads(e['content']).get('ok') is True]
        rows = logs[attempt]
        check(len(rows) == len(executed) > 0, 'backend executions vs successful real search requests')
        check([row['search_index'] for row in rows] == list(range(1, len(rows) + 1)), 'backend execution order')
        summaries = []
        for row, tool in zip(rows, executed):
            event = verify_search(row, tool, coordinates[record['id']])
            summaries.append(event)
            for key in ('encoded_passages', 'cache_hits', 'elapsed_retrieval_seconds', 'encoding_seconds', 'ranking_seconds'):
                storage[key] += event[key]
            for k, v in event['ranking_comparison'].items():
                comparisons[k]['positions'] += v['k']
                comparisons[k]['shared_members'] += v['overlap']
                comparisons[k]['compared_pool_rows'] += v['compared_pool_rows']
                comparisons[k]['sum_absolute_rank_change'] += v['sum_absolute_rank_change']
                if v['top1_same'] is not None:
                    comparisons[k]['nonempty_searches'] += 1
                    comparisons[k]['same_top1'] += int(v['top1_same'])
        by_case[record['id']] = summaries
    extra = sorted(set(attempts) - selected)
    discarded_calls = [e for key in extra for e in attempts[key] if e.get('event') == 'api_attempt']
    reported = [(e.get('response') or {}).get('usage', {}).get('total_tokens') for e in discarded_calls]
    excluded = {'count': len(extra), 'api_calls': len(discarded_calls), 'known_tokens': sum(t for t in reported if type(t) is int),
                'unknown_usage_attempts': sum(type(t) is not int for t in reported), 'search_backend_executions': sum(len(logs.get(key, [])) for key in extra)}
    return {'backend_identity_verified': True, 'retrieval_mode': 'bounded BM25 candidates; 4B ranks these candidates only',
            'selected_attempts': len(selected), 'selected_search_calls': sum(map(len, by_case.values())), 'excluded_attempts': excluded,
            'collection_costs_selected': dict(storage), 'rank_agreement_selected': {k: dict(v) for k, v in comparisons.items()}, 'cases': by_case}
