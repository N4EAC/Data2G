#!/usr/bin/env bash
# PR #232 rerun on master merged in: sessions first, then burst level.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=/home/andrew/code/Data2G/.venv/bin/python
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 DATA2G_PEP_REF_DB=5
# scripts/ goes first on sys.path, and the venv's editable install points data2g at the main checkout
export PYTHONPATH="$PWD"
(cd scripts && $PY -c "import data2g; print('data2g from', data2g.__file__)")
O=runs/onod232
mkdir -p $O
CELLS=awgn:-10,awgn:-6,awgn:-4,awgn:5,mpp:-6,mpp:-3,mpp:0,mpd:-6,mpd:-3,mpd:0
for arm in 0 1; do
  echo "== bulk ONOD=$arm $(date)"
  DATA2G_ONOD=$arm nice $PY scripts/loss_study.py --policy shift+cpm --seeds 16 --horizon 300 --jobs 8 \
    --cells $CELLS --out $O/bulk_onod$arm.csv > $O/bulk_onod$arm.log 2>&1
done
for arm in 0 1; do
  echo "== winlink ONOD=$arm $(date)"
  DATA2G_ONOD=$arm CHAT_PROBE_WORKLOAD=winlink CHAT_PROBE_POLICY=shift+cpm CHAT_PROBE_OUT=$O/winlink_onod$arm.json \
    nice $PY -m scripts.chat_probe 24 awgn:10 awgn:-4 mpp:0 mpd:-3 > $O/winlink_onod$arm.log 2>&1
done
echo "== detect $(date)"
nice $PY scripts/onod_study.py --detect --trials 300 --jobs 8 \
  --at awgn:-8 awgn:-6 awgn:-4 mpp:-4 mpp:0 mpp:3 mpd:-4 mpd:0 mpd:3 > $O/detect.log 2>&1
echo "== false $(date)"
nice $PY scripts/onod_study.py --false 20000 --jobs 8 > $O/false.log 2>&1
echo "== noise $(date)"
nice $PY scripts/onod_study.py --noise 100000 --jobs 8 > $O/noise.log 2>&1
echo "== done $(date)"
