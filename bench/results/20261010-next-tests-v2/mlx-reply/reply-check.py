"""One cold paged F32 English answer; feasibility evidence, not a matched speed gain."""
import json
from pathlib import Path
import subprocess
import sys
import time

import mlx.core as mx
from strata_mlx.engine import Engine
from strata_mlx.load import load
from strata_mlx.sampler import Sampling

HERE=Path(__file__).resolve().parent
STOP=(248044,248046)

def main():
    plan=json.loads((HERE/'plan.json').read_text())
    model_path,helper=sys.argv[1:]
    def vocab(record):
        p=subprocess.run([helper,model_path],input=json.dumps(record),capture_output=True,text=True,check=True,timeout=30)
        d=json.loads(p.stdout)
        assert d['vocabulary_only'] and d['weights_loaded'] is False
        return d
    prompt=vocab({'text':plan['rendered_prompt']})
    ids=prompt['tokens']
    assert prompt['text']==plan['rendered_prompt'] and 0<len(ids)+plan['output_limit']<=plan['max_context_tokens']
    mx.set_default_device(mx.gpu)
    mx.set_memory_limit(20*1024**3)  # Allocator guideline, external resource guard remains authoritative.
    mx.set_cache_limit(512*1024**2); mx.reset_peak_memory()
    print(json.dumps({'phase':'starting-load','prompt_ids':ids}),flush=True)
    start=time.monotonic()
    model,metadata=load(model_path,dtype=mx.float32,expert_memory=plan['expert_budget_decimal_GB'])
    engine=Engine(model,mtp=None,drafts=0,lookup=False,chunk=plan['prompt_chunk_tokens'],checkpoints=2,guess_rows=False)
    engine.sampling=Sampling(temperature=0,seed=1234)
    assert engine.paged and engine.mtp is None and engine.drafts==0 and engine.lookup is None and engine.rows is None
    store=model.expert_store
    assert store.held==0 and store.budget==6_000_000_000
    loaded=time.monotonic()
    print(json.dumps({'phase':'loaded','load_s':loaded-start,'active_mlx_bytes':mx.get_active_memory()}),flush=True)
    store.reset_stats()
    began=time.monotonic()
    tokens=[engine.read(ids)]
    mx.synchronize()
    first=time.monotonic()
    prompt_stats=dict(hits=store.hits,misses=store.misses,bytes_read=store.bytes_read,read_s=store.read_s)
    print(json.dumps({'phase':'first-token','token':tokens[0],'ttft_s':first-began}),flush=True)
    store.reset_stats()
    while len(tokens)<plan['output_limit'] and tokens[-1] not in STOP:
        tokens+=engine.step(1,STOP)
        if len(tokens)%4==0: print(json.dumps({'phase':'generating','output_tokens':len(tokens)}),flush=True)
    mx.synchronize()
    ended=time.monotonic()
    reply_stats=dict(hits=store.hits,misses=store.misses,bytes_read=store.bytes_read,read_s=store.read_s)
    assert len(ids)+len(tokens)<=plan['max_context_tokens'] and store.held<=store.budget
    assert engine.stats.drafted==0 and engine.stats.lookup_steps==0
    text=vocab({'tokens':tokens})['text']
    n=len(tokens)-1
    print(json.dumps(dict(phase='complete',status='passed',model_architecture=metadata['general.architecture'],
        dtype='float32',prompt_tokens=len(ids),tokens=tokens,text=text,output_tokens=len(tokens),
        finish_reason='stop' if tokens[-1] in STOP else 'length',load_s=loaded-start,
        ttft_s=first-began,decode_s=ended-first,decode_tokens=n,decode_tok_s=n/(ended-first) if n else None,
        reply_s=ended-began,prompt_pager=prompt_stats,reply_pager=reply_stats,
        expert_budget_bytes=store.budget,expert_cache_held_bytes=store.held,
        active_mlx_bytes=mx.get_active_memory(),peak_mlx_bytes=mx.get_peak_memory(),cache_mlx_bytes=mx.get_cache_memory(),
        models_loaded=True,generation_run=True,matched_speed_gain=None,exact_native_output_parity=False,adoption=False,
        scope='One cold, 16-token greedy answer; includes lazy GPU compilation/paging, no warmup/control/helper. Not comparable with the keeper cohort.')),flush=True)

if __name__=='__main__': main()
