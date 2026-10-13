#!/bin/zsh
cd "${0:A:h}"
# Explicit CLI arguments retain the original generic launcher behavior, including the small model.
if (( $# )); then
  exec .venv/bin/python scripts/run.py "$@"
fi
exec .venv/bin/python scripts/runtime_profiles.py --profile balanced
