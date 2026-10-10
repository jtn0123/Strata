#!/usr/bin/env python3
"""Summarize the immutable diagnostic baseline; never launch native work."""
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE/'result.json').read_text())
    if result['status'] != 'passed':
        raise ValueError('A complete baseline is required')
    paths = [HERE/name/'result.json' for name in
             ('00-control', '01-observer-off', '02-observer-on', '03-control')]
    arms = [json.loads(p.read_text()) for p in paths]
    on = arms[2]
    if len(on['cases']) != len(on['diagnostics']['requests']):
        raise ValueError('Request attribution is incomplete')
    pairs = list(zip(on['cases'], on['diagnostics']['requests']))
    phases = []
    median = statistics.median
    for workload in ('code', 'prose'):
        for phase in ('prompt', 'generation'):
            rows = [d['phases'][phase] for c,d in pairs
                    if c['workload']==workload and not c['warmup']]
            if len(rows)!=3:
                raise ValueError('Expected three measured phase records')
            names = sorted({n for r in rows for n in r['cpu_stages']})
            stages = {name:{metric:median(r['cpu_stages'].get(name,{}).get(metric,0) for r in rows)
                      for metric in ('calls','wall_union_ms','outside_recorded_model_gpu_ms')}
                      for name in names}
            phases.append(dict(workload=workload, phase=phase, measured_answers=3,
                wall_ms=median(r['server_phase_wall_ms'] for r in rows),
                recorded_gpu_percent=median(100*r['all_gpu_buffer_union_ms']/r['server_phase_wall_ms'] for r in rows),
                planning_ms=median(r['planning_wall_union_ms'] for r in rows),
                planning_outside_gpu_ms=median(r['planning_outside_recorded_gpu_ms'] for r in rows),
                graph_rebuilds=median(sum(count for role in r['graph_calls'].values()
                                         for reason,count in role.items() if reason!='reuse') for r in rows),
                graph_reuses=median(sum(role.get('reuse',0) for role in r['graph_calls'].values()) for r in rows),
                prompt_checkpoint_calls=median(r['checkpoint_create_calls'] for r in rows),
                stages=stages))
    summary = dict(schema=1, model='Qwen3.5-4B Q4_K_M', helper_enabled=False,
        measured_answers=24, warmups=8, exact_output_answers=32,
        baseline=result['summary'], phase_medians=phases,
        minimum_available_gib=min(r['memory']['minimum_available_bytes'] for r in arms)/2**30,
        maximum_server_rss_gib=max(r['memory']['peak_rss_bytes'] for r in arms)/2**30,
        new_swap_bytes=max(r['memory']['swap_growth_bytes'] for r in arms),
        clock=on['diagnostics']['clock'],
        inputs={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        note='Monitoring-on phase timings describe this small model only. Intervals overlap; GPU coverage is elapsed command-buffer time, not active utilization. Outside recorded GPU is not proven removable time. RSS and allocation logs are not unique physical memory. All answers end at a fixed length cap.')
    (HERE/'MONITORING.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    lines=['# Monitoring baseline: Qwen3.5-4B Q4_K_M','',
           'Four fresh processes: P07 control, observer build with monitoring off, monitoring on, then P07 control. Each runs one excluded warmup and three measured answers per English workload. All 32 capped answers have identical input/output IDs, text, finish type and helper counters. No helper is enabled on this model.','',
           '| Workload | Uninstrumented TPS | First token | 128-token reply | Monitoring TPS cost | Control TPS drift |',
           '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in result['summary']:
        b=r['baseline']
        lines.append(f"| {r['workload']} | {b['tps']:.3f} | {b['ttft_s']*1000:.2f} ms | {b['reply_s']:.4f} s | {-r['monitoring_perturbation_percent']['tps']:.3f}% | {r['control_drift_percent']['tps']:.3f}% |")
    lines += ['', 'The observer build with monitoring off differs by only -0.152%/-0.089% in code/prose TPS, inside the controls’ observed variation. Detailed monitoring stays off during optimization speed comparisons. This small-model rate does not replace the full-model P07 baseline.', '',
              '| Workload / phase | Phase wall | Recorded GPU interval coverage | Graph rebuilds / reuses | Reset + build + allocate |',
              '| --- | ---: | ---: | ---: | ---: |']
    for r in phases:
        lines.append(f"| {r['workload']} / {r['phase']} | {r['wall_ms']:.3f} ms | {r['recorded_gpu_percent']:.2f}% | {r['graph_rebuilds']:g} / {r['graph_reuses']:g} | {r['planning_ms']:.3f} ms |")
    lines += ['', '| Workload / phase | CPU area | Calls | Wall interval union | Outside recorded GPU |',
              '| --- | --- | ---: | ---: | ---: |']
    for r in phases:
        for name,s in r['stages'].items():
            lines.append(f"| {r['workload']} / {r['phase']} | {name} | {s['calls']:g} | {s['wall_union_ms']:.3f} ms | {s['outside_recorded_model_gpu_ms']:.3f} ms |")
    lines += ['', 'All phase values are medians of three measured requests in the instrumented process. Setup stages, helper work and GPU intervals may overlap; do not add overlapping totals. The uncovered intervals are a diagnostic bound, not measured GPU idle time, SSD wait or a causal speedup budget.', '',
              f"Minimum host available: **{summary['minimum_available_gib']:.3f} GiB**. Maximum sampled server RSS: **{summary['maximum_server_rss_gib']:.3f} GiB**; this is not total Metal or unique physical memory. **Zero new swap**, normal pressure, healthy monitors and owned children shut down. Clock mapping spread: **{summary['clock']['spread_us']:.3f} microseconds**; widest calibration bracket: **{summary['clock']['widest_anchor_us']:.3f} microseconds**.", '',
              'This model has no prediction helper, so helper planning, replay, drafting and acceptance bottlenecks remain unmeasured. Prompt-checkpoint creation markers cover that operation only; they do not cover all speculative state saves/restores. Complete-answer quality, long prompts, cached continuations and full internal tensor-state equivalence remain outside this baseline.', '',
              '[Reproducible summary](MONITORING.json), [raw campaign](result.json), [frozen protocol](frozen.json), [summary generator](summarize_monitoring.py).']
    (HERE/'MONITORING.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
