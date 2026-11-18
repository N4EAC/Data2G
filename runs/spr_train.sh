#!/bin/bash
# spr round students: from cohc4 (--init), cohc4's targets on the legacy CPM
# spread inputs (--legacy-cpm-spread: what it was trained on), every mode's
# targets from sprle12 (LCB 0.5) on rows measured fast, ramped by the row's
# spread_est:  sprs46 4..6 Hz,  sprs35 3..5 Hz.   runs/spr_train.sh
set -euo pipefail
cd "$(dirname "$0")/.."
O=${O:-/home/andrew/code/Data2G/runs/spr}
PY=/home/andrew/code/Data2G/.venv/bin/python
C4=/home/andrew/code/Data2G/runs/sev/shipped_cohc4.npz
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
D=$O/session_data_spr.csv,$O/session_data_spr_slow.csv,$O/session_data_spr_high.csv
D=$D,$O/session_data_spr_awgnhigh.csv,$O/session_data_spr_fastlow.csv,$O/session_data_spr_floor.csv
D=$D,$O/session_data_spr_sev.csv,$O/outcome_data_general_spr.csv
D=$D,/home/andrew/code/Data2G/runs/outcome-data/outcome_data_n10top_gt.csv
st() {
  local name=$1; shift
  [ -s $O/$name.npz ] || DATA2G_OUTCOME_LCB=0.5 OMP_NUM_THREADS=4 $PY -m scripts.cnp_outcome "$D" --teacher $C4 \
    --init $C4 --lr 2e-4 --epochs 20 --legacy-cpm-spread --teacher-fast $O/sprle12.npz "$@" --out $O/$name.npz \
    > $O/$name.log 2>&1
}
st sprs46 --fast-ramp 4:6 &
st sprs35 --fast-ramp 3:5 &
wait
date
