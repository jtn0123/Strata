#!/bin/zsh
cd "${0:A:h}"
exec .venv/bin/python scripts/run.py flash --engine m5-top10 --m5-tuning top10 --tensor-api on --spec draft-mtp --draft-model mtp_shared_packed_q3 --draft 3 --draft-placement mixed --draft-threads 8 --draft-p-min 0.0 "$@"
