#!/bin/zsh
cd "${0:A:h}"
exec .venv/bin/python scripts/run.py flash --spec draft-mtp --draft-model mtp_q3 --draft 2 --draft-placement output "$@"
