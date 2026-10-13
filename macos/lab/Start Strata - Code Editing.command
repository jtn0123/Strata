#!/bin/zsh
cd "${0:A:h}"
exec .venv/bin/python scripts/runtime_profiles.py --profile code-edit
