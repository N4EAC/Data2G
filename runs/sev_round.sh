#!/bin/bash
# Outcome model exposed to severe fading (ITU-R F.1487 severe profiles and
# 2-30 Hz Doppler; session_data --severe). Tree: this worktree
# (ade53f7 = master ad37335 + ITU presets + --severe). Steered by the
# installed model (cohc4, runs/sev/shipped_cohc4.npz), env runs/sev_env.sh
# (as runs/cohm/cohm_round.sh). Then twelve outcome-trained CNPs (--labels,
# seeds 1-12) on the cohm sets + the severe set, ensembled (sevle12), for
# routing at high spread_est (DATA2G_OUTCOME_FAST). Output in the main
# checkout's runs/sev.   runs/sev_round.sh [data|members|all]
set -euo pipefail
T=$(cd "$(dirname "$0")/.." && pwd)
cd $T
PY=/home/andrew/code/Data2G/.venv/bin/python
O=/home/andrew/code/Data2G/runs/sev
C=/home/andrew/code/Data2G/runs/cohm
J=${J:-8}
phase=${1:-all}
if [[ $phase == data || $phase == all ]]; then
  if ! grep -q "^done" $O/session_data_sev.log 2>/dev/null; then
    STEER=$O/shipped_cohc4.npz $T/runs/sev_env.sh $PY tools/with_native.py scripts/session_data.py --severe \
      --sessions 2000 --first 16000000 --jobs $J --out $O/session_data_sev.csv > $O/session_data_sev.log 2>&1
    echo done >> $O/session_data_sev.log
  fi
  date
fi
D=$C/session_data_cohm.csv,$C/session_data_cohm_slow.csv,$C/session_data_cohm_high.csv
D=$D,$C/session_data_cohm_awgnhigh.csv,$C/session_data_cohm_fastlow.csv,$C/session_data_cohm_floor.csv
D=$D,$C/outcome_data_general_cohm.csv,/home/andrew/code/Data2G/runs/outcome-data/outcome_data_n10top_gt.csv
D=$D,$O/session_data_sev.csv
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
if [[ $phase == members || $phase == all ]]; then
  for k in $(seq 1 12); do
    [ -s $O/sevl$k.npz ] || OMP_NUM_THREADS=4 $PY -m scripts.cnp_outcome "$D" --labels --seed $k --epochs 60 \
      --out $O/sevl$k.npz > $O/sevl$k.log 2>&1 &
    (( k % 3 == 0 )) && wait
  done
  wait
  M=$(for k in $(seq 1 12); do printf "%s," $O/sevl$k.npz; done)
  [ -s $O/sevle12.npz ] || $PY -m scripts.train_outcome x --ensemble ${M%,} --out $O/sevle12.npz
  date
fi
