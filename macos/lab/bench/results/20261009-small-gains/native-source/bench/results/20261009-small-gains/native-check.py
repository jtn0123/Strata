#!/usr/bin/env python3
"""Check all combined-engine flag combinations with the original three probes."""
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from benchmark import Monitor
from engines import sha256,verify_engine
from metal_environment import configure,TUNING
from validate_offline import require_pass,fingerprint
from check_memory import assert_no_model_server
import benchmark_m5_compact as compact
import benchmark_m5_top10 as top10
import benchmark_m5_reduce as reduce

BUNDLE=Path(__file__).resolve().parent
WORK=ROOT/'bench/runtime/m5-small-stack'
RESULTS=BUNDLE/'native'


def main():
    require_pass();assert_no_model_server();WORK.mkdir(parents=True,exist_ok=True);RESULTS.mkdir()
    pin=verify_engine('m5-small-stack');source=fingerprint()
    sources={name:sha256(ROOT/f'native/m5_{name}_probe.cpp') for name in ('compact','top10','reduce')}
    archive=BUNDLE/'native-source';archive.mkdir()
    closure=list(source)+[f'native/m5_{kind}_probe.cpp' for kind in sources]+[str(Path(__file__).relative_to(ROOT)),
             'patches/mtp-m5-small-stack.patch','patches/mtp-m5-copy.patch','patches/mtp-m5-reduce.patch',
             'patches/mtp-m5-top10.patch','patches/mtp-m5-compact.patch']
    archived={}
    for name in closure:
        dest=archive/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
        archived[name]=sha256(dest)
        if sha256(ROOT/name)!=archived[name]:raise ValueError('Native source archive differs')
    profiles=['conv-direct']+[name for name in TUNING if name.startswith('small-')]
    receipt=dict(status='running',engine=pin,runner_sha256=sha256(__file__),source_pins=source,
                 sources=sources,archive=archived,profiles=profiles,builds=[],runs=[])
    def save():(BUNDLE/'native-checks.json').write_text(json.dumps(receipt,indent=2)+'\n')
    save()
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            binaries={}
            for kind in sources:
                for scope,engine in (('control','m5-top10' if kind=='top10' else 'm5-copy'),('stack','m5-small-stack')):
                    native=ROOT/verify_engine(engine)['directory'];binary=WORK/f'{kind}-{scope}-probe'
                    command=['/usr/bin/c++','-O3','-ffp-contract=off','-std=gnu++17','-arch','arm64',
                             '-I'+str(native/'ggml/include'),'-I'+str(native/'include'),'-I'+str(native/'vendor'),
                             str(ROOT/f'native/m5_{kind}_probe.cpp'),'-o',str(binary),'-Wl,-rpath,'+str(native/'build/bin'),
                             *[str(native/'build/bin'/name) for name in ('libggml.0.26.0.dylib','libggml-base.0.26.0.dylib')]]
                    if kind=='top10':command.append(str(native/'build/bin/libllama.0.6.0.dylib'))
                    with (WORK/f'{kind}-{scope}-build.log').open('w') as log:subprocess.run(command,stdout=log,stderr=log,check=True)
                    binaries[(kind,scope)]=binary
                    receipt['builds'].append(dict(kind=kind,scope=scope,engine=verify_engine(engine),binary_sha256=sha256(binary),command=command));save()
            controls={}
            for profile in ['original']+profiles:
                enabled={name for name,flag in [('compact','GGML_M5_LAB_COMPACT_TILES'),('top10','GGML_M5_LAB_TOP10'),('reduce','GGML_M5_LAB_REDUCE10')]
                         if profile!='original' and flag in TUNING[profile]}
                for kind in sources:
                    engine=('m5-top10' if kind=='top10' else 'm5-copy') if profile=='original' else 'm5-small-stack'
                    scope=('compact' if 'compact' in enabled else 'control') if kind=='compact' else ('candidate' if 'top10' in enabled else 'control')
                    folder=RESULTS/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+kind+'-'+profile);folder.mkdir()
                    binary=binaries[(kind,'control' if profile=='original' else 'stack')]
                    env,flags=configure(dict(os.environ),engine,'on','conv-direct' if profile=='original' else profile)
                    output=folder/('outputs.bin' if kind=='reduce' else 'outputs.jsonl')
                    command=[str(binary),'check',str(output)]+([] if kind=='reduce' else [scope])
                    record=dict(status='running',kind=kind,profile=profile,engine=verify_engine(engine),binary_sha256=sha256(binary),metal_environment=flags,command=command)
                    process=monitor=None
                    try:
                        with (folder/'native.log').open('w') as log:
                            baseline=Monitor.baseline();process=subprocess.Popen(command,stdout=log,stderr=log,env=env)
                            monitor=Monitor(process,folder/'memory.jsonl',0,1024**3,baseline=baseline);monitor.thread.start();code=process.wait(timeout=900)
                        memory=monitor.finish();record.update(native_returncode=code,memory=memory)
                        if code or memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
                            raise ValueError('Native probe/resource guard failed')
                        raw=(folder/'native.log').read_text()
                        if kind=='compact':
                            rows=compact.parse(raw,'check',scope)
                            evidence=[json.loads(line) for line in output.read_text().splitlines()]
                            if evidence!=rows+compact.markers(raw,'M5_COMPACT_DONE'):raise ValueError('Compact raw artifacts disagree')
                            if profile=='original':controls[kind]=rows
                            else:compact.compare_exact(controls[kind],rows)
                            encodings=sum(row['count_delta'] for row in rows)
                        elif kind=='top10':
                            rows,done,fixtures=top10.parse(raw,scope,'check')
                            evidence=[json.loads(line) for line in output.read_text().splitlines()]
                            # The inherited guard-stride test has a stdout receipt only.
                            # parse() still validates it; mirror the original JSONL inventory.
                            expected=[dict(id=row['id'],elements=row['elements'],sha256=row['output_sha256']) for row in rows]+[row for row in fixtures if row['id']!='guard-stride']
                            if evidence!=expected:raise ValueError('Top10 raw artifacts disagree')
                            comparable=[{key:row[key] for key in ('id','rows','k','m','input_sha256','weight_sha256','output_sha256')}|dict(consumers=[top10.comparable(x) for x in row['consumers']]) for row in rows]
                            comparable+= [top10.comparable(row) for row in fixtures]
                            if profile=='original':controls[kind]=comparable
                            elif comparable!=controls[kind]:raise ValueError('Top10 head/IDs/adversarial outputs changed')
                            encodings=None
                        else:
                            rows=reduce.parse(raw,'check');data=np.fromfile(output,dtype=np.uint32)
                            if output.stat().st_size!=4*sum(row['elements'] for row in rows):raise ValueError('Reduction output bytes incomplete')
                            if profile=='original':controls[kind]=(rows,data)
                            else:
                                original,old=controls[kind]
                                same=data==old;same|=np.isnan(data.view(np.float32))&np.isnan(old.view(np.float32))
                                if not same.all():raise ValueError('Reduction finite output bits changed')
                                for a,b in zip(original,rows):
                                    if any(a[key]!=b[key] for key in ('width','rows','experts','layout','elements','samples')):raise ValueError('Reduction fixture identity changed')
                                    eligible=b['experts']==10 and b['layout'] in ('plain','cancel','special') and 'reduce' in enabled
                                    label='MUL'+'+ADD'*9
                                    if b['fusions'].get(label,0)-a['fusions'].get(label,0)!=(10 if eligible else 0):raise ValueError('Reduction fusion count changed')
                                    if b['experts']==10 and b['layout']!='special' and (a['cpu_bit_differences'] or b['cpu_bit_differences']):raise ValueError('Reduction CPU finite reference differs')
                            encodings=None
                        record.update(status='passed',cases=len(rows),eligible_compact_encodings=encodings,
                                      native_log_sha256=sha256(folder/'native.log'),outputs_sha256=sha256(output),exact_original_outputs=True)
                    except Exception as error:record.update(status='failed',error=str(error));raise
                    finally:
                        if process and process.poll() is None:process.terminate();process.wait(timeout=10)
                        if monitor and 'memory' not in record:record['memory']=monitor.finish()
                        if (folder/'native.log').exists():record['native_log_sha256']=sha256(folder/'native.log')
                        if output.exists():record['outputs_sha256']=sha256(output)
                        (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
                        receipt['runs'].append(str(folder.relative_to(ROOT)));save()
                    if fingerprint()!=source or verify_engine('m5-small-stack')!=pin:raise ValueError('Source closure changed during native checks')
                    print(kind,profile,'exact outputs passed',flush=True)
            receipt['status']='passed';save()
        except Exception as error:receipt.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
