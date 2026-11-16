#!/bin/bash
# Issue #207: per-symbol noise (DATA2G_SYMBOL_NOISE) on HF, paired loss study.
set -e
cd "$(dirname "$0")/../.."
export PYTHONPATH=$PWD DATA2G_PEP_REF_DB=5 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
P=${P:-/home/andrew/code/Data2G/.venv/bin/python}
C9=awgn:0,mpg:0,mpg:8,mpp:-4,mpp:0,mpp:8,mpd:-4,mpd:0,mpd:8
EDGE=awgn:-4,mpg:-4,mpp:-8,mpd:-6,awgn:15,mpp:15,mpd:20
IMP=awgn:4:imp,mpg:0:imp,mpp:0:imp,mpd:0:imp,awgn:4:imp_long,mpg:0:imp_long,mpp:0:imp_long,mpd:0:imp_long
QRM=mpg:4:edge,mpg:4:mid,mpg:4:carriers,mpg:4:qrm_wide
MISC=awgn:4:rec,mpg:0:rec,mpp:0:slow,mpd:0:slow
for s in 0 1; do
  DATA2G_SYMBOL_NOISE=$s $P scripts/loss_study.py --out runs/symnoise/loss_sym$s.csv --seeds 12 --horizon 600 \
    --jobs 8 --policy shift+cpm --cells $C9,$EDGE,$IMP,$QRM,$MISC --recordings /home/andrew/code/Data2G/recordings \
    > runs/symnoise/loss_sym$s.log 2>&1
done
$P scripts/paired_loss.py runs/symnoise/loss_sym0.csv runs/symnoise/loss_sym1.csv > runs/symnoise/paired.txt
