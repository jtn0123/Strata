# Account for weights and saved allocations

Status: prepared; testing is on hold.

Saved-header/log accounting tool is ready. Mapped spans are kept separate from estimated components; 8K allocation measurements remain held.

Hypothesis: Explicit accounting helps distinguish disk capacity from physical RAM needs.

Only change: Read saved GGUF header inventory and historical logs; allocate no model memory.

## Before testing

- Explicit testing go-ahead for any --run command
- Offline validation receipt matches current sources
- Quiet host; leave unrelated VM/build work alone

## Required evidence

- Target and helper file bytes separate from lazy lookup mapping
- Repeated reservations counted once per role/backend/type
- Unknown resident pages, driver/QSA/scratch and background footprint stated

## Stop conditions

- Invalid evidence or source drift
- Unexpected quality failure or new swap

## Record results

Use `result-template.json`; all numbers remain empty until measured.

TPS gain = 100*(candidate/control-1). Time reduction = 100*(1-candidate/control). Requires finite positive matched metrics. Do not add percentages from separate experiments.

At least 5 percent median complete-task improvement on the chosen workload, or useful capacity gain with an explicitly accepted speed tradeoff; no unexplained quality failure or new swap. Report control drift and all raw passes.

Historical results are reference only. Record a new complete matched baseline for a speed candidate.

## Limits

Component sums are estimates, not measured RSS/peak RAM or proof that 8K fits.

Plan-only command:

```sh
.venv/bin/python scripts/memory_budget.py
```

The accounting command reads saved headers/logs only. Model-dependent allocations are collected by the later context trial.
