"""Bounded MLX GPU/import smoke; no model, session, sampler or throughput claim."""
import importlib.metadata
import json
import time

import mlx.core as mx

started = time.monotonic()
assert mx.is_available(mx.gpu), 'MLX GPU backend unavailable'
mx.set_default_device(mx.gpu)
mx.set_memory_limit(512 * 1024**2)  # Allocator guideline, not a hard resource bound.
mx.set_cache_limit(16 * 1024**2)
mx.reset_peak_memory()

from strata_mlx.engine import Engine
from strata_mlx.load import load

x = mx.arange(1024, dtype=mx.float32).reshape(32, 32)
y = mx.matmul(x, mx.eye(32, dtype=mx.float32)) + 1
mx.eval(y)
mx.synchronize()
assert y.dtype == mx.float32
assert y.reshape(-1).tolist() == list(range(1, 1025)), 'F32 GPU output changed'
peak = mx.get_peak_memory()
assert peak < 128 * 1024**2, 'Tiny device check exceeded its measured array budget'
print(json.dumps(dict(status='passed', device=mx.device_info(mx.gpu),
    dependencies={n: importlib.metadata.version(n) for n in ('mlx', 'mlx-metal', 'mlx-lm')},
    engine_imported=Engine.__module__, loader_imported=load.__module__,
    dtype=str(y.dtype), exact_checked_values=1024, peak_mlx_bytes=peak,
    active_mlx_bytes=mx.get_active_memory(), elapsed_s=time.monotonic()-started,
    models_loaded=False, throughput_measured=False, sampler_state_parity=False)), flush=True)
