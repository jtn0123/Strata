#!/bin/zsh
set -e
cd "$(dirname "$0")"
exec .venv/bin/python scripts/benchmark_m5.py "$@"
