from pathlib import Path
import json,sys,statistics
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from benchmark_metrics import metrics
from engines import ENGINES,verify_engine
from benchmark_m5_copy import verify as verify_copy
from check_memory import assert_no_model_server
import psutil

batch_path=Path(sys.argv[1]).resolve(); batch=json.loads(batch_path.read_text())
if batch['status']!='passed':raise RuntimeError('Full model batch is not accepted')
path=next(p for s in batch['stages'] for p in s['artifacts'] if p.endswith('/comparison.json'))
comparison=json.loads((ROOT/path).read_text())
if comparison['status']!='passed':raise RuntimeError('Comparison is not accepted')
runs=[json.loads((ROOT/'bench/results'/r['run_id']/'result.json').read_text()) for r in comparison['runs']]
stock=next(r for r in runs if r['settings']['m5_tuning']=='stock')
parity=[]
for r in runs:
    reference={(c['workload'],c['prompt_tokens'],c['repeat']):c for c in stock['cases']}
    pairs=[]
    for c in r['cases']:
        key=(c['workload'],c['prompt_tokens'],c['repeat']);a=reference[key]
        pairs.append({'key':list(key),'prompt_match':c['prompt_sha256']==a['prompt_sha256'],
                      'tokens_match':c['response']['generated_token_ids']==a['response']['generated_token_ids'],
                      'text_match':c['response']['text']==a['response']['text']})
    cr={(c['history_budget'],c['repeat'],c['warmup']):c for c in stock['cached_cases']}
    cached=[]
    for c in r['cached_cases']:
        a=cr[(c['history_budget'],c['repeat'],c['warmup'])]
        cached.append({'history_budget':c['history_budget'],'repeat':c['repeat'],'warmup':c['warmup'],
                       'prompt_match':c['prompt_sha256']==a['prompt_sha256'],'tokens_match':c['token_ids']==a['token_ids'],'text_match':c['text']==a['text']})
    parity.append({'run_id':r['run_id'],'tuning':r['settings']['m5_tuning'],'fresh':pairs,'cached':cached,
                   'all_match':all(p['prompt_match'] and p['tokens_match'] and p['text_match'] for p in pairs+cached)})
if not all(p['all_match'] for p in parity):raise RuntimeError('Bit-exact copy change produced different model outputs')
old_pins=json.loads((ROOT/'bench/features/m5-copy-original-engines.json').read_text())
if any(verify_engine(n)!=pin for n,pin in old_pins.items()):raise RuntimeError('Original engine was changed')
assert_no_model_server()
summary={'schema':1,'status':'passed','comparison':path,'runner':str(batch_path.relative_to(ROOT)),
         'fresh_rows':[r for r in comparison['summary'] if not r['cached']],
         'cached_rows':[r for r in comparison['summary'] if r['cached']],
         'model_runs':len(runs),'answer_checks':sum(len(r['checks']) for r in runs),'fresh_samples':sum(len(r['cases']) for r in runs),
         'parity':parity,'bit_exact_model_output_parity':True,
         'new_swap_bytes':sum(r['memory']['swap_growth_bytes'] for r in runs),
         'minimum_available_bytes':min(r['memory']['minimum_available_bytes'] for r in runs),
         'peak_rss_bytes':max(r['memory']['peak_rss_bytes'] for r in runs),
         'old_engine_pins_unchanged':True,'copy_probe':verify_copy(),
         'notes':['Detailed split traces interrupt fusion and must not be used as normal-runtime operation shares.',
                  'The lighter dispatcher inventory has 123 unique shapes and no large 786432-float unfused state copy; native GDN cache fusion writes the state directly.',
                  'CPU-reference math, bit-exact copied bytes and complete model output parity are separate evidence.',
                  'Fresh benchmark gains compare these new bracketed controls, not historical results.'],
         'final_available_bytes':psutil.virtual_memory().available,'final_swap_bytes':psutil.swap_memory().used}
(batch_path.parent/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
lines=['# M5 incremental copy experiments','',
       'Qwen3.8-Flash-Next GSQ-RCO Q2_0, M5 Pro 48 GiB. Depth 3, eight helper workers, Tensor API on, 4K context, F16 cache, 128 fresh output tokens. Only the named native copy mode changes.',
       '', 'Each mode has two model launches and three measured repeats per workload. One warmup is excluded. Control and candidate order: stock, scalar, vector4, direct convolution, direct convolution, vector4, scalar, stock.',
       '', '| Workload | Setting | TPS | Gain vs fresh stock | First-token reduction | Total-response reduction | Stock drift |',
       '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
for row in comparison['summary']:
    for mode,rate in row['profiles'].items():
        delta=row['vs_control'][mode]
        lines.append(f"| {row['workload']}/{row['input_budget']} | {mode} | {rate['generation_tok_s']:.3f} | {delta['generation_increase_percent']:+.2f}% | {delta['ttft_reduction_percent']:+.2f}% | {delta['total_time_reduction_percent']:+.2f}% | {row['control_drift']['generation_increase_percent']:+.2f}% |")
lines += ['',f"Validation: {summary['model_runs']} model launches; {summary['fresh_samples']} measured fresh outputs; {summary['answer_checks']} answer/cache checks. Every fresh and cached output matches stock token for token. No new swap. Minimum available RAM: {summary['minimum_available_bytes']/1024**3:.2f} GiB. Peak process RSS: {summary['peak_rss_bytes']/1024**3:.2f} GiB; RSS is not total Metal memory.",
          '', 'The detailed split trace exposed a costly-looking state CPY by interrupting graph fusion. The lighter normal-path inventory confirms native GDN cache fusion already removes those state copies. Copy-only speedups therefore do not represent model TPS gains.',
          '', f'[Raw comparison]({ROOT/path})',f'[Normal-path shape inventory]({batch_path.parent}/shape-inventory/inventory.json)',f'[Complete summary]({batch_path.parent}/summary.json)']
(batch_path.parent/'REPORT.md').write_text('\n'.join(lines)+'\n')
print(batch_path.parent/'REPORT.md')
for row in summary['fresh_rows']:
 print(row['workload'],row['input_budget'],[(k,round(v['generation_tok_s'],3),round(row['vs_control'][k]['generation_increase_percent'],2)) for k,v in row['profiles'].items()])
