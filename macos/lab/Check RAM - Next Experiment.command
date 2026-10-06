#!/bin/zsh
cd "${0:A:h}"
exec .venv/bin/python scripts/benchmark_q2.py
