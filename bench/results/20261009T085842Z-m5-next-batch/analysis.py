"""Summarize saved accepted trials; no models or GPU work are started."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,os

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'bench/results/20261009T085842Z-m5-next-batch'
def read(path):return json.loads((ROOT/path).read_text())
first=read('bench/results/20261009T085842Z-m5-next-batch/batch.json')
retry=read('bench/results/20261009T092635Z-m5-context-v2/batch.json')
assert first['status']=='partial' and retry['status']=='passed'
def artifact(batch,name):
    stage=next(s for s in batch['stages'] if s['name']==name)
    assert stage['status']=='passed' and len(stage['artifacts'])==1
    return stage['artifacts'][0]
residual_path=artifact(first,'metal-residual-correctness')
routes_path=artifact(first,'expert-reuse')
split_path=artifact(first,'split-gpu-cost')
lookup_path=artifact(first,'lookup-io')
context_path=artifact(retry,'context-8k-fixture-v2')
residual,context=read(residual_path),read(context_path)
routes,split,lookup=read(routes_path),read(split_path),read(lookup_path)
speed_runs=[read('bench/results/'+r['run_id']+'/result.json') for r in residual['runs']]+context['runs']
assert len(speed_runs)==8
assert all(r['status']=='passed' and r['memory']['swap_growth_bytes']==0 for r in speed_runs)
assert sum(len(r['checks']) for r in speed_runs)==262
assert all(c['passed'] is True for r in speed_runs for c in r['checks'])
assert first['engines']==retry['engines']
for model in first['model_provenance']['models']:
    a=first['model_provenance']['models'][model]
    b=retry['model_provenance']['models'][model]
    assert a['registry']==b['registry']
    assert [(f['path'],f['identity'],f['sha256']) for f in a['files']]==[(f['path'],f['identity'],f['sha256']) for f in b['files']]

route_rows=[];cost_rows=[];shape_rows=[];diagnostic_memories=[]
for depth in (3,4):
    route_capture=read(str(Path(routes_path).parent/f'depth{depth}-routes/capture.json'))
    split_capture=read(str(Path(split_path).parent/f'depth{depth}-split/capture.json'))
    for mode,path in (('routes',routes_path),('split',split_path)):
        for kind in ('control',mode):
            cap=read(str(Path(path).parent/f'depth{depth}-{kind}/capture.json'))
            assert cap['status']=='passed' and cap['memory']['swap_growth_bytes']==0
            diagnostic_memories.append(cap['memory'])
    for inp,request in zip(route_capture['requests'][1:],route_capture['diagnostics']['requests'][1:]):
        selected=next(r for r in request['expert_reuse'] if r['role']=='target' and r['rows']==depth+1)
        assert selected['layer_coverage']==list(range(48))
        route_rows.append({'depth':depth,'input_tokens':inp['prompt_tokens'],**selected})
    for inp,request in zip(split_capture['requests'][1:],split_capture['diagnostics']['requests'][1:]):
        for role in ('target','helper'):
            grouped=defaultdict(float)
            for item in request['split_costs']:
                if item['role']==role:grouped[item['family']]+=item['gpu_elapsed_sum_ms']
            total=sum(grouped.values())
            cost_rows.append({'depth':depth,'input_tokens':inp['prompt_tokens'],'role':role,
                              'total_split_gpu_ms':total,'family_percent':{k:100*v/total for k,v in grouped.items()}})
        grouped=defaultdict(float)
        for item in request['segments']:
            if item['role']=='target':grouped[(item['op'],item['src0_type'],tuple(item['src0'] or []))]+=item['gpu_ms']
        shape_rows.append({'depth':depth,'input_tokens':inp['prompt_tokens'],
                           'top_shapes':[{'op':k[0],'type':k[1],'src0':list(k[2]),'split_gpu_ms':v}
                                         for k,v in sorted(grouped.items(),key=lambda x:x[1],reverse=True)[:10]]})

initial=read('bench/results/20261009T092035Z-context-2-8192/result.json')
assert initial['status']=='completed-check-failure' and len(initial['retrieval_cases'])==1
case=initial['retrieval_cases'][0];text=case['response']['text'].strip()
assert text.startswith('```json\n') and text.endswith('\n```')
assert json.loads(text[len('```json\n'):-len('\n```')])==case['expected']
recall=[c for r in context['runs'] for c in r.get('retrieval_cases',[])]
assert len(recall)==6 and all(c['passed'] and c['fixture_version']==2 and c['prompt_tokens']==6144 for c in recall)
resources=read('bench/features/20261009-next-batch-final-resources.json')
assert resources['engines']==retry['engines']
summary={'schema':1,'status':'completed-with-retained-initial-format-failure',
         'accepted_answer_cache_recall_checks':262,'paired_diagnostic_responses':12,
         'accepted_full_model_launches':16,'accepted_timing_samples':168,
         'native_engines_and_models_unchanged':True,'default_launchers_changed':False,
         'residual_fix_gain_claim':False,'context_capacity_multiplier':2,
         'residual_summary':residual['summary'],'context_summary':context['summary'],
         'expert_reuse':route_rows,'split_costs':cost_rows,'split_top_shapes':shape_rows,
         'retained_initial_format_failure':{'run_id':initial['run_id'],'seed':7,'all_three_fact_values_correct':True,
                                           'strict_raw_json_failed':True,'later_seeds_not_run':True},
         'lookup':{'path':lookup_path,'cache_state_uncontrolled':True,
                   'total_bytes':sum(r['bytes'] for r in lookup['runs']),
                   'passes':[{k:r[k] for k in ('pass','bytes','median_read_us','p95_read_us')} for r in lookup['runs']]},
         'final_resources':resources,'evidence':{'first_batch':'bench/results/20261009T085842Z-m5-next-batch/batch.json',
         'context_retry':'bench/results/20261009T092635Z-m5-context-v2/batch.json',
         'residual':residual_path,'routes':routes_path,'split':split_path,'context':context_path,'lookup':lookup_path}}
summary['minimum_available_in_accepted_runs_bytes']=min(r['memory']['minimum_available_bytes'] for r in speed_runs)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
(OUT/'analysis.py').write_bytes(Path(__file__).read_bytes())
def link(label,path):return f'[{label}]({os.path.relpath(ROOT/path,OUT)})'
names={'synthetic':'Synthetic','code':'Code','prose':'Prose','chinese':'Chinese','cached-ledger':'Cached ledger'}
lines=['# Full-model GPU, context and SSD results — October 9, 2026','',
       'The prepared full-model queue is measured. The GPU correctness candidate passed without a useful speed gain. The full Qwen3.8-Flash-Next GSQ-RCO Q2_0 also passed a complete 4K/8K/8K/4K comparison: double the configured context, with fresh generation speed essentially unchanged, six exact-6144-token recall fixtures passing, and zero new swap. Normal launchers retain their existing engine and 4K default.','',
       'The first context trial remains failed because the model returned correct facts inside Markdown fences. Fixture v2 explicitly asks for raw JSON and forbids fences; the strict JSON grader is unchanged. The retry uses its own four fresh launches and is not pooled with that stopped trial.','',
       '## GPU correctness candidate','',
       'Control/fix/fix/control; three measured repeats plus one excluded warmup per workload per launch. Depth3 MTP, eight helper workers, F16, 4K, Tensor API on, batch/ubatch512 and 128 fresh output tokens are fixed. Both engines pass 572 general CPU-reference GPU cases; the fixed engine also passes 16 residual reproducer cases. All 128 model answer/cache checks pass.','',
       '| Workload | Control TPS | Fixed TPS | Change |','|---|---:|---:|---:|']
for row in residual['summary']:
    if row['cached']:continue
    label=names[row['workload']]+(f" / {row['input_budget']}" if row['workload']=='synthetic' else '')
    lines.append(f"| {label} | {row['profiles']['m5-lab']['generation_tok_s']:.2f} | {row['profiles']['m5-correctness']['generation_tok_s']:.2f} | {row['vs_control']['m5-correctness']['generation_increase_percent']:+.2f}% |")
lines+=['','Fresh changes are -0.22% to +0.16%, with control generation drift below 0.50%. There is no useful TPS gain. Passing the backport does not establish that this Qwen graph exposes the original faulty fusion. '+link('Matched candidate evidence',residual_path)+'.','',
        '## 8K capacity and speed','',
        'Same native mtp-mma engine and short speed prompts at both contexts. Three 6144-token recall fixtures are capacity checks only, with facts near the beginning, middle and end. Each 8K launch passes 35 checks; each 4K launch passes 32. All 134 checks pass.','',
        '| Workload | 4K TPS | 8K TPS | Change | Reply-time reduction |','|---|---:|---:|---:|---:|']
for row in context['summary']:
    if row['cached']:continue
    label=names[row['workload']]+(f" / {row['input_budget']}" if row['workload']=='synthetic' else '')
    lines.append(f"| {label} | {row['profiles']['4096']['generation_tok_s']:.2f} | {row['profiles']['8192']['generation_tok_s']:.2f} | {row['vs_4k']['generation_increase_percent']:+.2f}% | {row['vs_4k']['total_time_reduction_percent']:+.2f}% |")
lines+=['','Fresh generation differences are -0.18% to +0.20%, with fresh control drift below 0.36%. Whole-reply differences are below 0.36%. The short cached2048 reply has 5.84% control drift, so its apparent -2.24% generation difference is not a reliable context penalty. Cached replies are short structured answers and are not general writing TPS.','',
        '| Launch | Context | Checks | Minimum available RAM | New swap | Logged private buffers |','|---|---:|---:|---:|---:|---:|']
for i,r in enumerate(context['runs'],1):
    lines.append(f"| {i} | {r['settings']['context']} | {len(r['checks'])}/{len(r['checks'])} | {r['memory']['minimum_available_bytes']/1024**3:.2f} GiB | 0 | {r['allocation_budget']['known_private_buffer_bytes']/1024**2:.2f} MiB |")
lines+=['','Both 8K passes retained at least 2.32 GiB available. Process RSS is not total unique Metal memory. The private-buffer report was corrected after replaying real logs: attention and indexer KV caches had shared backend/kind labels and were overwritten. The 4K report now retains 96+24+8+2=130 MiB of KV, recovering an omitted 104 MiB; repeated compute reservations still count once. A failing regression was reproduced before the fix. All 91 maintained offline tests pass. Logged allocations remain component estimates, not physical peak RAM. '+link('Full context comparison',context_path)+'.','',
        '## Expert weights and broader GPU costs','',
        'All 48 target expert layers and the helper layer are captured. Both depth3/4 captures match greedy control text and token IDs, including warmups; the routing and split suites provide 12 paired responses. Each token still needs its own calculation; repeated selections could share weight reads.','',
        '| Draft depth | Prompt | Verification rows | Unique experts, median | Repeated selection share |','|---|---:|---:|---:|---:|']
for r in route_rows:
    lines.append(f"| {r['depth']} | {r['input_tokens']} | {r['rows']} | {r['unique_experts_median']:.0f} | {r['reused_assignment_percent_mean']:.2f}% |")
lines+=['','Dominant target batches repeat about 31% of assignments at depth3 and 35% at depth4. This is within a layer/verification batch, with no cross-session cache or reusable output claim. '+link('Routing evidence',routes_path)+'.','',
        '| Depth / prompt | Expert matrix | Other matrix | Other operations | Attention/state | Vocabulary |','|---|---:|---:|---:|---:|---:|']
for r in cost_rows:
    if r['role']!='target':continue
    p=r['family_percent']
    lines.append(f"| {r['depth']} / {r['input_tokens']} | {p['expert-matrix']:.1f}% | {p['other-matrix']:.1f}% | {p['other-ops']:.1f}% | {p['attention/state']:.1f}% | {p['vocabulary']:.1f}% |")
lines+=['','These are split-diagnostic GPU intervals. Callbacks synchronize operations and prevent fusion; their overhead inflates small operations. They rank investigation targets and cannot establish normal kernel percentages, accelerator occupancy or a whole-model speedup. Helper vocabulary math accounts for about 56-61% of its split GPU interval. Large recurrent-state CPY nodes and BF16 matrices [320,10240] / [10240,320] are concrete additional targets alongside Q2_0 expert matrices. '+link('Validated split evidence',split_path)+'.','',
        '## Bounded lookup-file reads','',
        f"128 offsets, three read-only passes; {summary['lookup']['total_bytes']/1024**2:.2f} MiB total. Digests and file identity match. Cache state is uncontrolled. No writes, preloads or full-table locking were performed.",'',
        '| Pass | Median read | P95 read |','|---|---:|---:|']
for r in lookup['runs']:lines.append(f"| {r['pass']} | {r['median_read_us']:.3f} microseconds | {r['p95_read_us']:.3f} microseconds |")
lines+=['','This measures sampled pread latency, not native mmap fault time, sequential SSD bandwidth, RAM-equivalent performance or an inference TPS gain. Prefetch still requires native wait/miss evidence. '+link('Read probe',lookup_path)+'.','',
        '## Current state and next useful work','',
        'Sixteen accepted full-model launches provide 262 answer/cache/recall checks, 168 measured speed samples and 12 paired diagnostic outputs. The original two-launch context trial is retained separately; its first 4K launch passed and its 8K launch failed raw-JSON formatting at seed7, before later seeds were attempted. All eight native engines and exact model files remain unchanged. The benchmark harness is unchanged within each batch; only the documented fixture/reporting changes separate the batches.','',
        f"The model servers are stopped. A read-only reset of idle owned model pages restored {resources['available_after_bytes']/1024**3:.2f} GiB available. T3 and WiFiman remain running; no VM, Docker or Chrome was restarted. Available memory varies with subsequent activity.",'',
        'Next, validate the shared-matrix and large-state-copy shapes in bounded isolated tests, then compare one candidate in the normal fused runtime. A grouped expert-weight-read prototype can use the measured repeat distribution. Prefetch and larger-model paging still need actual native lookup waits and broader hot-set/capacity evidence. Quantized KV is unnecessary for this validated 8K/F16 fit and remains a separate later correctness task. No new kernel, pager, prefetcher or speed preset was adopted by these measurements.','',
        link('Combined summary','bench/results/20261009T085842Z-m5-next-batch/summary.json')+', '+link('Original batch','bench/results/20261009T085842Z-m5-next-batch/batch.json')+', '+link('Context retry','bench/results/20261009T092635Z-m5-context-v2/batch.json')+'.']
(OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
print('Report:',OUT/'REPORT.md')
print('Accepted checks:',summary['accepted_answer_cache_recall_checks'],'measured timing samples:',summary['accepted_timing_samples'])
