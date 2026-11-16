#!/bin/bash
# Issue #207: SYMBOL_NOISE with a gate (scale only symbols > G x median), against loss_sym0.csv.
set -e
cd "$(dirname "$0")/../.."
export PYTHONPATH=$PWD DATA2G_PEP_REF_DB=5 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 DATA2G_SYMBOL_NOISE=1
P=${P:-/home/andrew/code/Data2G/.venv/bin/python}
CELLS=mpd:-4,mpd:0,mpd:8,mpd:0:slow,mpg:-4,mpg:4:mid,mpg:0:imp,awgn:4:imp_long,mpg:0:imp_long,mpp:0:imp_long,mpd:0:imp_long
for g in ${GATES:-2 4}; do
  DATA2G_SYMBOL_NOISE_GATE=$g $P scripts/loss_study.py --out runs/symnoise/loss_gate$g.csv --seeds 12 --horizon 600 \
    --jobs 8 --policy shift+cpm --cells $CELLS > runs/symnoise/loss_gate$g.log 2>&1
  $P scripts/paired_loss.py runs/symnoise/loss_sym0.csv runs/symnoise/loss_gate$g.csv > runs/symnoise/paired_gate$g.txt
done
