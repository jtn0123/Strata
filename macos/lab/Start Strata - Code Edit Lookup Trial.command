#!/bin/zsh
cd "${0:A:h}"
# Compatibility shortcut; the maintained profile lives in scripts/.
exec .venv/bin/python scripts/runtime_profiles.py --profile code-edit
