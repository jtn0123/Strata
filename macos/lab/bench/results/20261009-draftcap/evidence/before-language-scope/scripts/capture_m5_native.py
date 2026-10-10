#!/usr/bin/env python3
"""Normal-fusion model evidence for next candidates; diagnostics are not TPS gains."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import math
import os
import socket
import subprocess
import time

from benchmark import Monitor,stream_completion,wait_ready
from check_memory import assert_no_model_server
from engines import ROOT,sha256,verify_engine
from lab import request,server_command
from metal_environment import configure
from model_provenance import assert_unchanged,verify_models
from profile_m5_routes import preflight
from validate_offline import require_pass

TRACE={'gate':'GGML_M5_LAB_GATE_TRACE','gdn':'GGML_M5_LAB_GDN_TRACE','lookup':'GGML_M5_LAB_LOOKUP_TRACE'}
PROMPTS={
 'prose':'Explain how to fairly compare local AI model speed and memory usage. Discuss warmup, input length, repeated trials, background programs, first-token delay, output speed, accuracy, and practical examples. Write about eight hundred words.',
 'code':'Write a Python command-line program that compares two JSON benchmark reports. Validate their model and workload identities, calculate throughput and latency changes, reject missing values and zero denominators, and print a clear table. Explain the edge cases and include examples.',
 'chinese':'请用中文详细解释如何公平比较两个本地人工智能模型运行程序的性能。讨论预热、输入长度、重复测试、后台程序、首字延迟、生成速度和内存，给出具体例子，写约八百字。',
}


def monotonic_us(): return time.clock_gettime_ns(time.CLOCK_MONOTONIC)//1000


def markers(text,name):
    return [json.loads(line.split(name+' ',1)[1]) for line in text.splitlines() if name+' ' in line]


def parse_lookup(text,requests):
    mappings=markers(text,'M5_LOOKUP_MAPPING');ops=markers(text,'M5_LOOKUP_OP')
    if not mappings or not ops: raise ValueError('Missing native lookup mapping or operation evidence')
    lookup={}
    for m in mappings:
        addr=int(m['tensor_address'],16);base=int(m['mapping_base'],16)
        if (m['role']!='lookup' or m['tensor']!='per_layer_token_embd.weight' or m['lazy'] is not True
            or type(m['shard'])!=int or m['shard']!=1
            or m['file_offset']!=192 or m['tensor_bytes']!=28800138240 or m['row_bytes']!=90
            or addr-base!=m['file_offset']): raise ValueError('Lookup mapping attribution differs')
        if addr in lookup and lookup[addr]!=m: raise ValueError('Conflicting lookup mapping')
        lookup[addr]=m
    pools=defaultdict(list)
    for op in ops:
        addr=int(op['tensor_address'],16)
        fields=('begin_us','end_us','envelope_us','worker_sum_us','threads','rows','unique_rows','logical_bytes',
                'pages','page_bytes','page_size','metadata_rows','ordinal')
        if (addr not in lookup or any(type(op[f])!=int or op[f]<0 for f in fields)
            or not op['begin_us']<=op['end_us'] or op['envelope_us']!=op['end_us']-op['begin_us']
            or not 1<=op['threads']<=64 or not 1<=op['unique_rows']<=op['rows']
            or op['logical_bytes']!=90*op['unique_rows'] or op['page_bytes']!=op['pages']*op['page_size']
            or op['page_size']!=16384 or not 1<=op['pages']<=2*op['unique_rows']
            or op['metadata_complete'] is not True or op['metadata_rows']!=op['rows']
            or op['worker_sum_us']>op['threads']*op['envelope_us']):
            raise ValueError('Incomplete or invalid native lookup timing/rows/pages')
        samples=op['demand_samples']
        if len(samples)>4 or (op['ordinal']>=4 and samples): raise ValueError('Unbounded lookup address samples')
        for sample in samples:
            if (type(sample['row'])!=int or not 0<=sample['row']<320001536
                or sample['tensor_offset']!=sample['row']*90 or int(sample['address'],16)!=addr+sample['tensor_offset']):
                raise ValueError('Lookup demand sample lacks exact mapping attribution')
        pools[op['pool']].append(op)
    for records in pools.values():
        records.sort(key=lambda x:x['ordinal'])
        if [o['ordinal'] for o in records]!=list(range(len(records))): raise ValueError('Missing or duplicated lookup invocations')
        if any(b['begin_us']<a['end_us'] for a,b in zip(records,records[1:])): raise ValueError('Lookup pool operations overlap')
    summaries=[];previous_end=-1
    for req in requests:
        if (type(req['begin_us'])!=int or type(req['end_us'])!=int
            or req['begin_us']>=req['end_us'] or req['begin_us']<previous_end):
            raise ValueError('Invalid or overlapping request intervals')
        previous_end=req['end_us']
        overlapping=[o for o in ops if o['begin_us']<req['end_us'] and o['end_us']>req['begin_us']]
        selected=[o for o in ops if req['begin_us']<=o['begin_us'] and o['end_us']<=req['end_us']]
        if any(o not in selected for o in overlapping): raise ValueError('Lookup operation crosses request boundary')
        if not selected: raise ValueError('A request has no native lookup coverage')
        wall=req['end_us']-req['begin_us'];total=sum(o['envelope_us'] for o in selected)
        summaries.append(dict(workload=req['workload'],warmup=req['warmup'],invocations=len(selected),
            request_wall_us=wall,lookup_envelope_sum_us=total,upper_bound_percent=100*total/wall,
            worker_sum_us=sum(o['worker_sum_us'] for o in selected),rows=sum(o['rows'] for o in selected),
            unique_rows_within_ops=sum(o['unique_rows'] for o in selected),
            page_bytes_within_ops=sum(o['page_bytes'] for o in selected)))
    return dict(mappings=mappings,operation_count=len(ops),requests=summaries,
                measured_SSD_wait=False,prefetch_worth_investigating=any(s['upper_bound_percent']>=2 for s in summaries if not s['warmup']),
                limitation='Envelope sum includes CPU dequantization, scheduling, overlapping target/helper work and trace perturbation. It is a conservative lookup-cost screen, not attributed SSD delay. Page counts deduplicate within each op only; warm cache state is uncontrolled.')


def parse_native(text,trace,tuning,requests):
    if trace=='lookup': return parse_lookup(text,requests)
    if trace=='gate':
        routes=markers(text,'M5_GATE_ROUTE');actual=[r for r in routes if r['phase']=='dispatch']
        if tuning.startswith('gate-up'):
            tile=8 if tuning=='gate-up8' else 4
            if not actual or any(r['k']!=2560 or r['m']!=640 or r['rows'] not in (4,5) or r['tile']!=tile or r['nodes']!=3 for r in actual):
                raise ValueError('Normal model gate fusion did not fire at expected shapes')
        elif actual: raise ValueError('Disabled gate candidate dispatched')
        return dict(routes=routes,normal_candidate_dispatches=len(actual),timings_excluded=True)
    if trace=='gdn':
        shapes=markers(text,'M5_GDN_SHAPE')
        actual=[s for s in shapes if s['K']==4 and s['v_ne'][1]==48 and s['q_ne'][1]==16 and s['q_ne'][0]==128 and s['v_ne'][2] in (1,2,3,4,5)]
        if not actual or not any(s['fused'] for s in actual): raise ValueError('Missing normal target GDN/cache-fusion shape proof')
        variant=int(tuning[-1]) if tuning.startswith('gdn-row') else 0
        if any(s['variant_rows']!=variant for s in actual): raise ValueError('Normal GDN selection differs')
        return dict(shapes=shapes,target_shapes=actual,timings_excluded=True)
    if trace!='off': raise ValueError('Unknown native trace')
    if any(markers(text,name) for name in ('M5_GATE_ROUTE','M5_GDN_SHAPE','M5_LOOKUP_OP')):
        raise ValueError('Control unexpectedly enabled native diagnostics')
    return dict(timings_excluded=True)


def capture(engine,tuning='conv-direct',trace='off',predict=128):
    require_pass();assert_no_model_server();pin=verify_engine(engine)
    proof=verify_models(['flash','mtp_shared_packed_q3']);runner=sha256(__file__)
    folder=ROOT/'bench/features'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-m5-native-'+engine+'-'+tuning+'-'+trace)
    folder.mkdir();env,flags=configure(os.environ,engine,'on',tuning)
    if trace!='off': env[TRACE[trace]]='1';flags['variables'][TRACE[trace]]='1'
    record=dict(schema=1,status='running',engine=pin,model_proof=proof,runner_sha256=runner,metal_environment=flags,
                models_loaded=True,requests=[],timings_excluded_from_speed_results=True,normal_fusion=True,
                request_policy=dict(predict=predict,warmup_predict=8,ignore_eos=True,temperature=0,seed=1234,cache_prompt=False,enable_thinking=False))
    process=monitor=None
    try:
        record['preflight']=preflight(False)
        with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        command=server_command('flash',port,4096,512,512,'draft-mtp',3,draft_placement='mixed',
                               draft_model='mtp_shared_packed_q3',engine=engine,draft_threads=8,draft_p_min=0.0)
        record['command']=command;assert_unchanged(proof)
        with (folder/'native.log').open('w') as log:
            baseline=Monitor.baseline();process=subprocess.Popen(command,env=env,stdout=log,stderr=log)
            monitor=Monitor(process,folder/'memory.jsonl',128*1024**2,1024**3,baseline=baseline);monitor.thread.start()
            base=f'http://127.0.0.1:{port}';record['ready_s']=wait_ready(process,base)
            for name,warmup in [('prose',True),*[(k,False) for k in PROMPTS]]:
                prompt=request(base,'/apply-template',dict(messages=[dict(role='user',content=PROMPTS[name])],chat_template_kwargs={'enable_thinking':False}))['prompt']
                tokens=request(base,'/tokenize',dict(content=prompt,add_special=False,parse_special=True))['tokens']
                count=8 if warmup else predict
                begin=monotonic_us()
                response=stream_completion(base,dict(prompt=tokens,n_predict=count,ignore_eos=True,temperature=0,seed=1234,cache_prompt=False,return_tokens=True,stream=True))
                end=monotonic_us();timings=response['final']['timings']
                if timings['predicted_n']!=count or timings['prompt_n']!=len(tokens) or len(response['generated_token_ids'])!=count:
                    raise RuntimeError('Native capture token counts differ')
                record['requests'].append(dict(workload=name,warmup=warmup,begin_us=begin,end_us=end,
                    prompt_sha256=hashlib.sha256(json.dumps(tokens).encode()).hexdigest(),response=response))
        record['status']='completed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}');raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        if monitor: record['memory']=monitor.finish()
        try:
            assert_no_model_server()
            if record['status']=='completed':
                memory=record['memory']
                if memory['guard'] or memory['swap_growth_bytes'] or not memory['monitor_healthy'] or not memory['child_exited']:
                    raise RuntimeError('Native capture memory/cleanup gate failed')
                if verify_engine(engine)!=pin or sha256(__file__)!=runner: raise RuntimeError('Capture provenance changed')
                assert_unchanged(proof);require_pass()
                record['native']=parse_native((folder/'native.log').read_text(),trace,tuning,record['requests'])
                record['status']='passed'
        except BaseException as error:
            record.update(status='failed',error=f'{type(error).__name__}: {error}')
        (folder/'capture.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
        print('Native capture',engine,tuning,trace,record['status'],folder,flush=True)
    if record['status']!='passed': raise RuntimeError(record.get('error','Native capture failed'))
    return folder


def compare(control,candidate):
    a,b=[json.loads((p/'capture.json').read_text()) for p in (control,candidate)]
    signature=lambda r:[(c['workload'],c['warmup'],c['prompt_sha256'],c['response']['generated_token_ids'],c['response']['text']) for c in r['requests']]
    if (a['status']!='passed' or b['status']!='passed' or a['model_proof']!=b['model_proof'] or signature(a)!=signature(b)
        or normalized_command(a['command'])!=normalized_command(b['command']) or a['request_policy']!=b['request_policy']
        or a['metal_environment']['tensor_api']!=b['metal_environment']['tensor_api']
        or a['metal_environment']['profile'] or b['metal_environment']['profile']
        or a['metal_environment']['tuning']!='conv-direct'
        or b['metal_environment']['tuning'] not in ('conv-direct','gate-up8','gate-up4','gdn-row1','gdn-row2','gdn-row4')):
        raise ValueError('Native capture tokens/text or model identity changed')
    result=dict(status='passed',control=str(control.relative_to(ROOT)),candidate=str(candidate.relative_to(ROOT)),
                outputs_identical=len(a['requests']),tps_gain_measured=False)
    (candidate/'parity.json').write_text(json.dumps(result,indent=2)+'\n');return result


def normalized_command(command):
    normalized=list(map(str,command));normalized[0]='<engine>'
    if normalized.count('--port')!=1: raise ValueError('Command must have one explicit server port')
    normalized[normalized.index('--port')+1]='<port>'
    return normalized


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--engine',required=True)
    ap.add_argument('--tuning',default='conv-direct');ap.add_argument('--trace',choices=(*TRACE,'off'),default='off')
    ap.add_argument('--predict',type=int,default=128);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    if args.predict<32: ap.error('Use at least32 measured output tokens')
    configure({},args.engine,'on',args.tuning)
    if not args.run: print('Prepared normal-fusion native capture; no model loaded.');return
    with (ROOT/'bench/.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);capture(args.engine,args.tuning,args.trace,args.predict)


if __name__=='__main__': main()
