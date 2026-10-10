from pathlib import Path
original=Path(__file__).with_name('m5-copy-incremental-20261009.py').read_text()
prefix=original[:original.index('done=threading.Event()\nwatcher=')]
prefix=prefix.replace("'-m5-copy-incremental'","'-m5-copy-resume'")
exec(compile(prefix,str(Path(__file__)), 'exec'),globals())
import shutil
previous_folder=ROOT/'bench/results/20261009T111729Z-m5-copy-incremental'
previous=json.loads((previous_folder/'batch.json').read_text())
original_comparison=ROOT/'bench/results/20261009T111751Z-m5-copy-kernels/comparison.json'
comparison=json.loads(original_comparison.read_text())
comparison.update(status='running', resumed_from=str(original_comparison.relative_to(ROOT)),
                  previous_error=comparison.pop('error',None), resume_runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
records=[json.loads((ROOT/'bench/results'/r['run_id']/'result.json').read_text()) for r in comparison['runs']]
spec=comparison['experiment']
if [r['value'] for r in comparison['runs']]!=benchmark_m5.plan(spec)[:3] or len(records)!=3 or any(r['status']!='passed' for r in records):raise RuntimeError('Resume prefix is not the exact accepted protocol prefix')
record.update(status='running',prior_batch=str((previous_folder/'batch.json').relative_to(ROOT)),
              runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),incremental_runner_sha256=hashlib.sha256(Path(__file__).with_name('m5-copy-incremental-20261009.py').read_bytes()).hexdigest())
(folder/'runner.py').write_bytes(Path(__file__).read_bytes())
(folder/'incremental-runner.py').write_bytes(Path(__file__).with_name('m5-copy-incremental-20261009.py').read_bytes())
shutil.copytree(previous_folder/'shape-inventory',folder/'shape-inventory')

def resume():
    for index,value in enumerate(benchmark_m5.plan(spec)[3:],4):
        verify_all()
        # Retest the unchanged quiet-host admission before the ordinary preflight.
        for attempt in range(6):
            cpu=[psutil.cpu_percent(interval=1) for _ in range(3)]
            if max(cpu)<=25 and statistics.mean(cpu)<=15:break
            print(f'CPU admission deferred, attempt {attempt+1}: {cpu}',flush=True)
            time.sleep(3)
        else:raise RuntimeError('Host remains busy; no model launched')
        args=benchmark_m5.settings(spec,value,f'm5-copy-kernels-resume-{index}-{value}',3)
        result=benchmark.run(args)
        if result['status']!='passed' or result['selected_engine']!=record['engines'][args.engine] or result['memory']['swap_growth_bytes']:
            raise RuntimeError('Resume run failed acceptance')
        records.append(result);comparison['runs'].append({'value':value,'run_id':result['run_id'],'status':result['status']})
        (folder/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    comparison['summary']=benchmark_m5.compare(records,spec,3)
    comparison['status']='passed'
    (folder/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    (folder/'COMPARISON.md').write_text(benchmark_m5.render(comparison))

done=threading.Event();watcher=threading.Thread(target=watch_resources,args=(folder/'resources.jsonl',done),daemon=True)
print(f'RESUME BATCH {folder}',flush=True);save()
try:
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record.update(offline_gate=require_pass(),harness_sources=fingerprint(),engines={n:verify_engine(n) for n in ENGINES},diagnostic=benchmark_m5_copy.verify(),model_provenance=verify_models(['flash','mtp_shared_packed_q3']))
        if previous['harness_sources']!=record['harness_sources'] or previous['engines']!=record['engines'] or previous['model_provenance']!=record['model_provenance'] or previous['diagnostic']!=record['diagnostic']:raise RuntimeError('Sources, model or probe changed across the resumed protocol')
        if len(comparison['math_checks'])!=4 or any(json.loads((ROOT/p).read_text())['status']!='passed' for p in comparison['math_checks']):raise RuntimeError('Missing prior GPU prerequisites')
        record['prior_math_checks']=comparison['math_checks'];record['prior_accepted_runs']=comparison['runs'].copy();save();watcher.start()
        with patch.object(benchmark,'Monitor',GuardedMonitor),patch.object(profile_m5_routes,'Monitor',GuardedMonitor),patch.object(profile_m5_routes,'preflight',guarded_preflight),patch.object(benchmark_m5,'settings',guarded_settings):
            stage('copy-kernels-resumed',resume)
        verify_all();record['status']='passed' if all(s['status']=='passed' for s in record['stages']) else 'partial'
except BaseException as error:
    record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
finally:
    done.set()
    if watcher.ident is not None:watcher.join(timeout=3)
    record['final_available_bytes']=psutil.virtual_memory().available;record['final_swap_bytes']=psutil.swap_memory().used;record['final_pressure_level']=pressure();record['harness_unchanged']=fingerprint()==record.get('harness_sources');save()
    print(f'RESUME COMPLETE {record["status"]}: {folder}',flush=True)
