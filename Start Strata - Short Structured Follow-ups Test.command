#!/bin/zsh
cd "${0:A:h}"
exec .venv/bin/python scripts/run.py flash --engine mtp-mma --spec draft-mtp --draft-model mtp_shared_packed_q3 --draft 6 --draft-placement mixed --draft-threads 8 --draft-p-min 0 --tensor-api on "$@"
