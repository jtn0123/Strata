"""Load-free acceptance checks for the warmed paged MLX cache comparison."""
import math
import statistics


def schedule(plan):
    names = list(plan['prompts'])
    return ([{'id': f'warmup-{name}', 'workload': name, 'warmup': True} for name in names]
            + [{'id': f'measured-{repeat}-{name}', 'workload': name, 'warmup': False}
               for repeat in range(plan['measured_repeats']) for name in names])


def validate_launch(output, plan, inputs, budget):
    if (output.get('phase') != 'complete' or output.get('status') != 'passed'
            or output.get('expert_budget_bytes') != budget * 1_000_000_000
            or output.get('dtype') != plan['dtype'] or output.get('adoption') is not False):
        raise ValueError('Incomplete or changed MLX launch scope')
    expected = schedule(plan)
    rows = output.get('cases', [])
    if len(rows) != len(expected):
        raise ValueError('Missing or extra warmup/measured answers')
    for row, spec in zip(rows, expected):
        if any(row.get(key) != value for key, value in spec.items()):
            raise ValueError('Answer inventory/order changed')
        ids = row.get('output_ids', [])
        if (row.get('input_ids') != inputs[spec['workload']]['tokens']
                or len(ids) < 2 or len(ids) > plan['output_limit']
                or row.get('output_tokens') != len(ids)
                or any(type(token) is not int or token < 0 for token in ids)
                or any(token in plan['stop_ids'] for token in ids[:-1])):
            raise ValueError('Invalid full input/output token inventory')
        finish = 'stop' if ids[-1] in plan['stop_ids'] else 'length'
        if row.get('finish_reason') != finish or (finish == 'length' and len(ids) != plan['output_limit']):
            raise ValueError('Finish reason or output limit changed')
        if len(row['input_ids']) + len(ids) > plan['max_context_tokens']:
            raise ValueError('Context budget exceeded')
        n = len(ids) - 1
        for metric in ('ttft_s', 'decode_s', 'reply_s', 'decode_tok_s'):
            value = row.get(metric)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('Missing/nonpositive/nonfinite timing')
        if (row.get('decode_tokens') != n
                or not math.isclose(row['decode_tok_s'], n / row['decode_s'], rel_tol=1e-9)
                or not math.isclose(row['reply_s'], row['ttft_s'] + row['decode_s'], rel_tol=1e-9)):
            raise ValueError('Inconsistent timing/token numerator')
        if (row.get('conversation_was_reset') is not True
                or row.get('expert_cache_retained_on_reset') is not True
                or row.get('decoded_state_tokens') != len(row['input_ids']) + n
                or row.get('pending_token') != ids[-1]
                or row.get('drafted') != 0 or row.get('lookup_steps') != 0
                or row.get('decode_steps') != n
                or not 0 <= row.get('expert_cache_held_bytes', -1) <= budget * 1_000_000_000):
            raise ValueError('State, cache budget or disabled acceleration scope changed')
    return rows


def compare_exact(groups):
    expected = {}
    for group in groups:
        for row in group:
            key = row['workload']
            signature = (row['input_ids'], row['output_ids'], row['finish_reason'],
                         row['decoded_state_tokens'], row['pending_token'])
            if key in expected and signature != expected[key]:
                raise ValueError(f'Full token/finish/state mismatch for {key}')
            expected[key] = signature


def summarize(groups, plan):
    if len(groups) != 4:
        raise ValueError('Complete four-launch ABBA comparison required')
    compare_exact(groups)
    summaries = []
    for name in plan['prompts']:
        medians = []
        for group in groups:
            rows = [row for row in group if row['workload'] == name and not row['warmup']]
            if len(rows) != plan['measured_repeats']:
                raise ValueError('Measured repetition inventory incomplete')
            medians.append({key: statistics.median(row[key] for row in rows)
                            for key in ('decode_tok_s', 'ttft_s', 'reply_s')})
        metrics = {}
        for key in medians[0]:
            values = [row[key] for row in medians]
            control = (values[0] + values[3]) / 2
            candidate = (values[1] + values[2]) / 2
            drift = 100 * abs(values[3] - values[0]) / control
            higher = key == 'decode_tok_s'
            gain = 100 * (candidate / control - 1) if higher else 100 * (1 - candidate / control)
            both = min(values[1:3]) > max(values[0], values[3]) if higher else max(values[1:3]) < min(values[0], values[3])
            metrics[key] = dict(control=control, candidate=candidate, launch_medians=values,
                                improvement_percent=gain, control_drift_percent=drift,
                                qualifies=gain > 2 * drift and both,
                                no_material_regression=gain >= -max(1.0, 2 * drift))
        primary = metrics[plan['primary_metric']]
        summaries.append(dict(workload=name, metrics=metrics,
                              qualifies=primary['qualifies'] and all(m['no_material_regression'] for m in metrics.values())))
    return dict(workloads=summaries, qualifies_for_native_followup=all(row['qualifies'] for row in summaries),
                exact_output_finish_state_parity=True, adoption=False, added_P07_TPS=None,
                scope='Warmed MLX 12 GB versus fresh matched MLX 6 GB cache; native parity not established')
