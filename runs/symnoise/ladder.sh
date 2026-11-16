#!/bin/bash
# Issue #207: paired 10% ladder (same --seed), DATA2G_SYMBOL_NOISE 0 vs 1, clean channels.
set -e
cd "$(dirname "$0")/../.."
export PYTHONPATH=$PWD OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
P=${P:-/home/andrew/code/Data2G/.venv/bin/python}
M="ack-4f qpsk-r1/5 16qam-r1/2 n10-qpsk-r1/2 n10-16qam-r3/4 w48-qpsk-r1/5 w48-qpsk-r1/2 w48-16qam-r1/2 w48-64l-r3/4"
for s in 0 1; do
  DATA2G_SYMBOL_NOISE=$s $P scripts/ladder_study.py --fail 0.1 --seed 0 --start runs/ladder_10pct.csv \
    --out runs/symnoise/ladder_sym$s.csv --modes $M > runs/symnoise/ladder_sym$s.log 2>&1
done
