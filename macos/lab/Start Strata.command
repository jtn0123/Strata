#!/bin/zsh
cd "${0:A:h}"
# Explicit CLI arguments retain the original generic launcher behavior, including the small model.
if (( $# )); then
  exec .venv/bin/python scripts/run.py "$@"
fi
exec .venv/bin/python scripts/run.py flash --engine m5-small-stack --m5-tuning small-reduce --tensor-api on --context 4096 --ubatch 512 --cache-type f16 --spec draft-mtp --draft-model mtp_shared_packed_q3 --draft 3 --draft-placement mixed --draft-threads 8 --draft-p-min 0.0
