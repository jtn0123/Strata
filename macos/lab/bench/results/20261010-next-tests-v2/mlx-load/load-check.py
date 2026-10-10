"""F32 full-model/base-state admission check; expert cache remains empty, no decode."""
import json
from pathlib import Path
import sys
import time

import mlx.core as mx
from mlx.utils import tree_flatten

from strata_mlx.engine import Engine
from strata_mlx.load import load

def main():
    mx.set_default_device(mx.gpu)
    mx.set_memory_limit(20 * 1024**3)  # An allocator guideline; external monitor provides the stop guard.
    mx.set_cache_limit(512 * 1024**2)
    mx.reset_peak_memory()
    start = time.monotonic()
    print(json.dumps({'phase':'starting-load','dtype':'float32','expert_budget_decimal_GB':12}),flush=True)
    model, metadata = load(sys.argv[1],dtype=mx.float32,expert_memory=12.0)
    mx.eval(model.parameters())
    loaded = time.monotonic()
    engine = Engine(model,mtp=None,drafts=0,lookup=False,chunk=32,checkpoints=2,guess_rows=False)
    mx.eval(engine.context, list(engine.gdn.values()))
    mx.synchronize()
    assert metadata['general.architecture']=='qwen4exp'
    assert len(engine.m.layers)==48
    assert engine.m.args.num_experts==512
    assert engine.m.args.num_experts_per_tok==10
    assert engine.paged and engine.mtp is None and engine.drafts==0 and engine.lookup is None and engine.rows is None
    assert model.expert_store.budget==12_000_000_000 and model.expert_store.held==0
    floats=[(name,a) for name,a in tree_flatten(model.parameters()) if mx.issubdtype(a.dtype,mx.floating)]
    assert floats and all(a.dtype==mx.float32 for name,a in floats), 'Floating model weights are not all F32'
    print(json.dumps(dict(phase='complete',status='passed',architecture=metadata['general.architecture'],
        layers=len(engine.m.layers),experts=engine.m.args.num_experts,selected_experts=engine.m.args.num_experts_per_tok,
        floating_parameter_arrays=len(floats),dtype='float32',load_s=loaded-start,total_s=time.monotonic()-start,
        active_mlx_bytes=mx.get_active_memory(),peak_mlx_bytes=mx.get_peak_memory(),cache_mlx_bytes=mx.get_cache_memory(),
        expert_budget_bytes=model.expert_store.budget,expert_cache_held_bytes=model.expert_store.held,
        models_loaded=True,generation_run=False,throughput_measured=False,adoption=False,
        limit='Empty expert cache and initial state only; filled-cache fit, prompt scratch, answers and parity remain untested.')),flush=True)

if __name__=='__main__': main()
