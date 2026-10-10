from pathlib import Path
import json,statistics,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from engines import verify_engine
from check_memory import assert_no_model_server,snapshot
from benchmark_m5_copy import verify
pin=verify();dest=ROOT/'bench/results/20261009T112641Z-m5-copy-resume'
d=json.loads((dest/'summary.json').read_text());tests=[];perf=[]
for path in sorted((ROOT/'bench/features').glob('*-m5-copy-*/probe.json')):
 r=json.loads(path.read_text())
 if r.get('probe')!=pin:continue
 if r['status']!='passed':raise RuntimeError(f'Post-run copy check failed: {path}')
 if r['mode']=='test':
  if r['cases_passed']!=56:raise RuntimeError('Missing tail checks')
  text=(path.parent/'native.log').read_text();shapes=[json.loads(s.split('M5_COPY_SHAPE ',1)[1]) for s in text.splitlines() if 'M5_COPY_SHAPE ' in s]
  eligible=[v for v in shapes if v['eligible'] and v['src_ne'][0] in (4097,4113,4132)]
  if r['metal_environment']['tuning'] in ('copy-v4','copy-v8') and len(eligible)!=9:raise RuntimeError('Aligned vector tails were not exercised')
  tests.append({'path':str(path.relative_to(ROOT)),'tuning':r['metal_environment']['tuning'],'cases':56,'eligible_tail_shapes':len(eligible),'new_swap_bytes':r['memory']['swap_growth_bytes']})
 else:perf.append({'path':str(path.relative_to(ROOT)),**r})
if len(tests)!=4 or len(perf)!=8:raise RuntimeError(f'Incomplete probes: {len(tests)}/{len(perf)}')
d.update(postrun_copy_tests=tests,bit_exact_copy_checks=224,postrun_probe_receipt=pin,copy_perf_artifacts=[p['path'] for p in perf],copy_perf_summary=[])
for rows in (1,4,5):
 for layout in ('contiguous','strided'):
  rates={}
  for mode in ('stock','copy-scalar','copy-v4','copy-v8'):
   values=[row['gpu_us'] for p in perf if p['metal_environment']['tuning']==mode for row in p['summary'] if row['rows']==rows and row['layout']==layout]
   if len(values)!=2:raise RuntimeError('Missing bracketed copy perf sample')
   rates[mode]=statistics.median(values)
  d['copy_perf_summary'].append({'rows':rows,'layout':layout,'median_gpu_us':rates,'copy_time_reduction_percent':{k:100*(1-v/rates['stock']) for k,v in rates.items()},'scope':'Isolated GPU graph, not model TPS; cache and clock state may change gains'})
old=json.loads((ROOT/'bench/features/m5-copy-original-engines.json').read_text());assert_no_model_server()
if any(verify_engine(n)!=p for n,p in old.items()):raise RuntimeError('Existing engine changed')
info=snapshot();d['final_resources']=info
(dest/'summary.json').write_text(json.dumps(d,indent=2,allow_nan=False)+'\n');(dest/'final-resources.json').write_text(json.dumps(info,indent=2)+'\n')
p=ROOT/'config/m5_pending_speed_plan.json';c=json.loads(p.read_text());c['testing_status']='Residual correctness and incremental copy comparisons complete; reproductions require explicit --run.';c['completed_results']={'metal-residual-correctness':'bench/results/20261009T085850Z-m5-metal-residual-correctness/comparison.json','copy-kernels':'bench/results/20261009T112641Z-m5-copy-resume/comparison.json'};p.write_text(json.dumps(c,indent=2)+'\n')
p=dest/'REPORT.md';s=p.read_text();s+='''
Post-run hardening: 224/224 bit-exact copy cases pass, including explicitly admitted aligned vector tails, strided convolution tails with and without CONT, unaligned/different-shape/transposed fallbacks, special F32 bit patterns, untouched destination padding and unchanged source bytes. Eight copy-only perf passes complete with microsecond artifact IDs. The earlier same-second collision is retained and excluded. The native model engine is unchanged. The exact 47-case probe/source/harness/build receipt used during model runs is archived in `probe-at-model-runs/`; the newer 56-case probe is supplementary validation after model timing.

The vector-only gain is not a model gain: the large state CPY is absent from normal dispatch. Cached-512 TPS control drift is 2.98%, larger than the measured 0.99% candidate change; no cached TPS gain is established. First-token reductions of 0.13-0.68% are too small for a strong latency claim. Fresh total-response time falls 0.75-1.59%. Initial Metal compilation/logging repairs, a trace-cap retry, the CPU-admission deferral and artifact-name collision are excluded from performance comparisons.

[Optional direct-copy launcher](../../../Start%20Strata%20-%20Direct%20Copy%20Trial.command) is syntax-checked and leaves ordinary launchers unchanged. It has not been left running. All eight existing engines are unchanged, T3/WiFiman remain open, and Chrome/Docker/VM remain stopped.
''';p.write_text(s)
print('Final checks:',len(tests),'x56 cases;',len(perf),'micro perf launches; RAM',round(info['memory']['available']/1024**3,2),'GiB')
