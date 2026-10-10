"""One fresh MLX process; fixed warmups then alternating English answers."""
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    import mlx.core as mx
    from strata_mlx.engine import Engine
    from strata_mlx.load import load
    from strata_mlx.sampler import Sampling
    from mlx.utils import tree_flatten

    frozen_path, model_path, vocab_binary, budget_text = sys.argv[1:]
    frozen = json.loads(Path(frozen_path).read_text())
    plan, inputs = frozen['plan'], frozen['inputs']
    budget = int(budget_text)
    mx.set_default_device(mx.gpu)
    mx.set_memory_limit(plan['mlx_memory_limit_gib'] * 2**30)
    mx.set_cache_limit(plan['mlx_allocator_cache_mib'] * 2**20)
    mx.reset_peak_memory()
    began_load = time.perf_counter()
    print(json.dumps({'phase': 'loading', 'expert_budget_decimal_GB': budget}), flush=True)
    model, metadata = load(model_path, dtype=mx.float32, expert_memory=budget)
    engine = Engine(model, mtp=None, drafts=0, lookup=False, chunk=plan['prompt_chunk_tokens'], checkpoints=2, guess_rows=False)
    engine.sampling = Sampling(temperature=plan['temperature'], seed=plan['seed'])
    store = model.expert_store
    assert metadata['general.architecture'] == 'qwen4exp'
    floating = [array for _, array in tree_flatten(model.parameters())
                if array.dtype in (mx.float16, mx.bfloat16, mx.float32)]
    assert len(floating) == 1298 and all(array.dtype == mx.float32 for array in floating)
    del floating
    assert len(engine.m.layers) == 48 and metadata['qwen4exp.expert_count'] == 512 and metadata['qwen4exp.expert_used_count'] == 10
    assert engine.paged and engine.mtp is None and engine.drafts == 0 and engine.lookup is None and engine.rows is None
    assert store.held == 0 and store.budget == budget * 1_000_000_000
    mx.synchronize()
    load_s = time.perf_counter() - began_load
    print(json.dumps({'phase': 'loaded', 'load_s': load_s, 'active_mlx_bytes': mx.get_active_memory()}), flush=True)
    rows = []
    for spec in frozen['schedule']:
        prompt = inputs[spec['workload']]['tokens']
        assert len(prompt) + plan['output_limit'] <= plan['max_context_tokens']
        held = store.held
        engine.reset()
        assert engine.tokens == [] and engine.next_token is None and engine.stats.steps == 0
        assert store.held == held
        mx.synchronize()
        store.reset_stats()
        started = time.perf_counter()
        tokens = [engine.read(prompt)]
        mx.synchronize()
        first = time.perf_counter()
        prompt_stats = dict(hits=store.hits, misses=store.misses, bytes_read=store.bytes_read, read_s=store.read_s)
        store.reset_stats()
        while len(tokens) < plan['output_limit'] and tokens[-1] not in plan['stop_ids']:
            next_ids = engine.step(1, tuple(plan['stop_ids']))
            assert len(next_ids) == 1
            tokens.extend(next_ids)
            if len(tokens) % 32 == 0:
                print(json.dumps({'phase': 'generating', 'id': spec['id'], 'output_tokens': len(tokens)}), flush=True)
        mx.synchronize()
        ended = time.perf_counter()
        decode = ended - first
        raw = subprocess.run([vocab_binary, model_path], input=json.dumps({'tokens': tokens}),
                             text=True, capture_output=True, check=True, timeout=30)
        decoded = json.loads(raw.stdout)
        assert decoded['vocabulary_only'] and decoded['weights_loaded'] is False and decoded['tokens'] == tokens
        row = dict(**spec, input_ids=prompt, output_ids=tokens, text=decoded['text'], output_tokens=len(tokens),
                   finish_reason='stop' if tokens[-1] in plan['stop_ids'] else 'length',
                   ttft_s=first-started, decode_s=decode, decode_tokens=len(tokens)-1,
                   decode_tok_s=(len(tokens)-1)/decode, reply_s=ended-started,
                   conversation_was_reset=True, expert_cache_retained_on_reset=True,
                   decoded_state_tokens=len(engine.tokens), pending_token=engine.next_token,
                   decode_steps=engine.stats.steps, drafted=engine.stats.drafted, lookup_steps=engine.stats.lookup_steps,
                   prompt_pager=prompt_stats, decode_pager=dict(hits=store.hits, misses=store.misses,
                       bytes_read=store.bytes_read, read_s=store.read_s),
                   expert_cache_held_bytes=store.held, active_mlx_bytes=mx.get_active_memory(),
                   peak_mlx_bytes=mx.get_peak_memory(), allocator_cache_bytes=mx.get_cache_memory())
        rows.append(row)
        print(json.dumps({'phase': 'answer', 'case': row}), flush=True)
    print(json.dumps(dict(phase='complete', status='passed', cases=rows, dtype=plan['dtype'],
                         expert_budget_bytes=store.budget, load_s=load_s, adoption=False,
                         peak_mlx_bytes=mx.get_peak_memory())), flush=True)


if __name__ == '__main__':
    main()
