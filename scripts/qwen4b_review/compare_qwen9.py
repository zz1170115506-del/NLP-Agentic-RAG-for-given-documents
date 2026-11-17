"""Compare nine completed trajectories offline; never used for retrieval or prompting.

The older run's hand-reviewed diagnostic coordinates are evaluated symmetrically.
The public JSON contains counts, coordinates and model identities. The separate
owner-readable worksheet contains exact source passages for the semantic review.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path

from retrieval_binding import verify_retrieval


CASE_IDS = {'960', '1035', '64', '231', '390', '58', '1155', '1066', '788'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_EXCL | os.O_CREAT, 0o600), 'w') as writer:
        json.dump(data, writer, ensure_ascii=False, indent=2)
        writer.write('\n')


def import_audit(repo):
    path = repo / 'scripts/audit_evidence_retention.py'
    spec = importlib.util.spec_from_file_location('retention_audit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluated_em(predictions, records):
    directory = predictions.parent / 'evaluation'
    if not (directory / 'per-question-private.json').exists():
        return {}
    identity = read(directory / 'evaluation-identity.json')
    if not identity['evaluated_after_run_completed'] or identity['prediction_sha256'] != sha(predictions):
        raise ValueError('Evaluation was not attached to these completed prediction bytes')
    rows = {r['id']: r for r in read(directory / 'per-question-private.json')}
    for record in records:
        if rows[record['id']]['answer'] != record['answer']:
            raise ValueError('Scored answer does not match trajectory export')
    return {case_id: int(row['em']) for case_id, row in rows.items()}


def usage_counts(record):
    rows = [(e.get('response') or {}).get('usage') or {} for e in record['trajectory'] if e.get('event') == 'api_attempt']
    summary = {}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        summary[key] = sum(u[key] for u in rows) if all(type(u.get(key)) is int for u in rows) else None
    cached = [(u.get('prompt_tokens_details') or {}).get('cached_tokens') for u in rows]
    summary['cached_prompt_tokens'] = sum(cached) if all(type(t) is int for t in cached) else None
    summary['unknown_total_usage_attempts'] = sum(type(u.get('total_tokens')) is not int for u in rows)
    return summary


def tool_identity(record):
    methods = Counter()
    events = []
    for event in record['trajectory']:
        if event.get('role') != 'tool' or event.get('name') != 'search':
            continue
        envelope = json.loads(event['content'])
        data = envelope.get('data') or {}
        hits = data.get('results') or []
        present = Counter(str(h.get('method', 'unknown')) for h in hits)
        methods.update(present)
        events.append({'sequence': event['sequence'], 'succeeded': envelope.get('ok') is True,
                       'returned_rows': len(hits), 'method_counts': dict(present)})
    return {'search_calls': events, 'returned_method_counts': dict(methods)}


def summarize_target(audit, target, private):
    observed = [span for t in private['tools'] if t['ok'] for span in t['returned_spans']]
    source_coverage = audit.coverage(target, observed, require_id=False)
    final = target['api_views'][-1]
    related = [t['sequence'] for t in private['tools'] if t['ok'] and audit.coverage(
        target, t['returned_spans'], require_id=False)['visible_chars']]
    return {'doc_id': target['doc_id'], 'offset': target['offset'], 'end': target['end'],
            'basis': target['selection_basis'], 'source_union': source_coverage['visibility'],
            'source_chars': source_coverage['visible_chars'], 'tool_sequences': related,
            'max_visible_chars_in_one_request': max(v['visible_chars'] for v in target['api_views']),
            'final_request_sequence': final['api_sequence'], 'final_request': final['visibility'],
            'final_request_chars': final['visible_chars']}


def summarize_case(audit, record, coords, em):
    public, private = audit.audit_record(record, coords)
    checks = ('all_actual_requests_within_context_budget', 'within_total_token_budget',
              'reported_usage_matches_prediction', 'all_tool_groups_paired')
    actual = private['requests']
    if not actual:
        raise ValueError('Missing actual API attempt')
    start = next(e for e in record['trajectory'] if e.get('event') == 'run_start')
    answer = next((e for e in reversed(record['trajectory']) if e.get('event') == 'answer'), {})
    anchors = [summarize_target(audit, t, private) for t in public['retrospective_targets']]
    last = actual[-1]
    ids = answer.get('supporting_evidence', [])
    visible_ids = {v['evidence_id'] for v in last['visible_spans']}
    support = {'cited_ids': ids, 'cited_id_count': len(ids),
               'cited_ids_explicitly_in_final_request': [i for i in ids if i in visible_ids]}
    latency = record['trajectory'][-1].get('elapsed_seconds')
    row = {'id': record['id'], 'em': em, 'has_answer': public['has_answer'], 'status': public['status'],
           'finalization': public['finalizations'], 'api_calls': len(actual), 'tools': record['tool_calls'],
           'reported_usage': usage_counts(record), 'http_status_counts': public['http_status_counts'],
           'elapsed_seconds': latency, 'host': public['provider_host'], 'model_request': sorted({a['requested_model'] for a in actual}),
           'model_response': sorted({a['response_model'] for a in actual if a['response_model']}),
           'thinking_off_all': all(a['enable_thinking'] is False for a in actual),
           'config_id': public['config_id'], 'config_method': start['config'].get('method'),
           'historical_coordinate_results': anchors, 'max_actual_input_chars': max(a['message_characters'] for a in actual),
           'source_unobserved_in_messages_count': public['unobserved_view_spans'], 'checks': {k: public[k] for k in checks},
           'all_tools_ever_seen_span_count': public['observed_span_count'], 'all_tools_never_reexposed_content_spans': public['never_visible_observed_content_spans'],
           'exact_repeated_searches': public['exact_repeated_search_queries'], 'search': tool_identity(record), 'citations': support}
    actions = [{'sequence': t['sequence'], 'tool': t['tool_name'], 'ok': t['ok'], 'arguments': t['arguments'],
                'new_span_count': t['new_observed_spans'], 'hit_rows': len(t['returned_spans'])} for t in private['tools']]
    worksheet = {'id': record['id'], 'question': record['question'], 'prediction': record['answer'],
                 'model_explanation': answer.get('explanation'), 'actual_answer_event': answer, 'tool_actions': actions,
                 'all_observed_spans': private['evidence_lifetimes'], 'actual_final_visible_spans': last['visible_spans'],
                 'final_api_sequence': last['sequence'], 'historical_coordinate_results': anchors}
    return row, worksheet


def aggregate(cases):
    tokens = [c['reported_usage']['total_tokens'] for c in cases]
    hits = [c['em'] for c in cases]
    return {'cases': len(cases), 'em_correct': sum(hits) if all(h is not None for h in hits) else None,
            'nonempty': sum(c['has_answer'] for c in cases), 'total_reported_tokens': sum(tokens) if all(t is not None for t in tokens) else None,
            'api_calls': sum(c['api_calls'] for c in cases), 'tool_calls': sum(c['tools'] for c in cases),
            'unknown_usage_attempts': sum(c['reported_usage']['unknown_total_usage_attempts'] for c in cases)}



def compare_controls(before, after, base_meta, new_meta):
    before_by_id = {r['id']: r for r in before}
    treatment_fields = {'method', 'instruction_model', 'instruction_revision', 'candidate_depth', 'batch_size', 'device',
                        'max_seq_length', 'qwen4b_compare_floats', 'qwen4b_dimension'}
    fields_changed = set()
    old_ids = set()
    new_ids = []
    first_calls_equal = []
    for new in after:
        old = before_by_id[new['id']]
        old_cfg, new_cfg = (r['trajectory'][0]['config'] for r in (old, new))
        fields_changed.update(k for k in set(old_cfg) | set(new_cfg) if old_cfg.get(k) != new_cfg.get(k))
        old_calls, new_calls = ([e for e in r['trajectory'] if e.get('event') == 'api_attempt'] for r in (old, new))
        first_calls_equal.append(old_calls[0]['request']['messages'] == new_calls[0]['request']['messages'])
        old_ids.update(e['response']['id'] for e in old_calls if e.get('http_status') == 200)
        for event in new_calls:
            req = event['request']
            if not (req.get('model') == 'deepseek-v4-flash-0731' and req.get('temperature') == 0
                    and req.get('enable_thinking') is False and req.get('stream') is False
                    and 0 < req['max_tokens'] <= new_cfg['max_output_tokens']):
                raise ValueError('QA request parameters changed')
            if event.get('http_status') == 200:
                resp = event['response']
                if resp['model'] != req['model'] or not resp.get('id'):
                    raise ValueError('Unexpected successful QA response identity')
                new_ids.append(resp['id'])
        if not old_cfg['agent_engine'] == new_cfg['agent_engine'] == 'baseline':
            raise ValueError('Unexpected agent engine')
    unexpected = fields_changed - treatment_fields
    controls = ('source_sha256', 'corpus_fingerprint', 'document_count', 'chunk_count', 'index_identity_sha256', 'skills_identity_sha256')
    equality = {k: base_meta.get(k) is not None and base_meta.get(k) == new_meta.get(k) for k in controls}
    if unexpected or not all(equality.values()) or not all(first_calls_equal):
        raise ValueError('Unmatched fixed input, corpus, skills, first messages or configuration: ' + str(sorted(unexpected)))
    if len(set(new_ids)) != len(new_ids) or set(new_ids) & old_ids:
        raise ValueError('Reused response identifiers in independent rerun')
    return {'same_initial_messages_all_nine': all(first_calls_equal), 'qa_model': 'deepseek-v4-flash-0731',
            'qa_request_temperature': 0, 'thinking': False, 'stream': False, 'fresh_success_response_ids': len(new_ids),
            'equal_metadata': equality, 'changed_config_fields': sorted(fields_changed)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True, help='Checkout that contains the independent visibility audit')
    parser.add_argument('--baseline', type=Path, required=True, help='Previous sparse-v2 prediction.jsonl')
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--coordinates', type=Path, required=True, help='Frozen pre-run diagnostic anchors')
    parser.add_argument('--output', type=Path, required=True, help='New directory; public summary and sensitive worksheet are separate')
    args = parser.parse_args()
    audit = import_audit(args.repo)
    previous, candidate = [audit.load_records(path) for path in (args.baseline, args.candidate)]
    if {r['id'] for r in previous} != CASE_IDS or {r['id'] for r in candidate} != CASE_IDS:
        raise ValueError('Need all nine ended unique case records per run')
    if {r['id']: r['question'] for r in previous} != {r['id']: r['question'] for r in candidate}:
        raise ValueError('Question texts differ between runs')
    targets, target_sha = audit.load_targets(args.coordinates, CASE_IDS)
    if set(targets) != CASE_IDS:
        raise ValueError('Specify at least one diagnostic anchor for every case')
    summary = {'comparison_scope': 'the nine selected historical failures', 'coordinates_sha256': target_sha,
               'currency_charge': None, 'currency_note': 'Provider usage logs preserve tokens; no actual invoice or tariff supplied.',
               'visibility_note': 'Coordinates come from pre-existing analyses and are diagnostic. Alternative sources can support the same condition. A visible or matching answer may still contradict original text. Semantic decisions require direct inspection.'}
    worksheets = {}
    for name, path, records in [('baseline_sparse_v2', args.baseline, previous), ('candidate', args.candidate, candidate)]:
        em = evaluated_em(path, records)
        paired = [summarize_case(audit, r, targets[r['id']], em.get(r['id'])) for r in records]
        cases = [v[0] for v in paired]
        summary[name] = {'sha256': sha(path), 'identity': audit.metadata(path), 'totals': aggregate(cases), 'cases': cases}
        worksheets[name] = [v[1] for v in paired]
    if any(c['config_method'] == 'qwen4b_candidates' for c in summary['candidate']['cases']):
        summary['run_controls'] = compare_controls(previous, candidate, summary['baseline_sparse_v2']['identity'],
                                                   summary['candidate']['identity'])
        summary['qwen_search_binding'] = verify_retrieval(args.candidate.parent, candidate, targets)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write(args.output / 'comparison-public.json', summary)
    write(args.output / 'worksheet-private.json', worksheets)
    print(json.dumps({name: summary[name]['totals'] for name in worksheets}))


if __name__ == '__main__':
    main()
