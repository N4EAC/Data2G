#!/bin/bash
# The outcome model on the lag-fit CPM spread_est (abdbef3: cpm.spread; every
# CPM-measured input moves off the old constant 3.0). Data: the cohm round's
# session kinds plus the severe set (session_data --severe) and the general
# offline set, on a frozen tree (main runs/spr/tree_new = abdbef3 + its native
# build), steered by the installed model (cohc4: it never saw a CPM spread
# other than 3.0, so its steering on CPM-measured rows is off-distribution;
# the labels are what matter). Then twelve outcome-trained CNPs (--labels,
# seeds 1-12) on all of it, ensembled (sprle12). Output in main runs/spr.
#   runs/spr_round.sh [data|members|all]
set -euo pipefail
O=${O:-/home/andrew/code/Data2G/runs/spr}
cd $O/tree_new
PY=/home/andrew/code/Data2G/.venv/bin/python
STEER=/home/andrew/code/Data2G/runs/sev/shipped_cohc4.npz  # == data2g/codes_data/outcome_predictor.npz at ad37335
ENV=$O/sev_env.sh
J=${J:-12}
phase=${1:-all}
if [[ $phase == data || $phase == all ]]; then
  for arm in "--severe" "--floor" "" "--slow" "--high" "--high --kinds awgn" "--fastlow"; do
    case $arm in
      "") n=2900 f=17000000 s="" ;;
      --slow) n=800 f=17100000 s=_slow ;;
      --high) n=1200 f=17200000 s=_high ;;
      "--high --kinds awgn") n=400 f=17300000 s=_awgnhigh ;;
      --fastlow) n=1200 f=17400000 s=_fastlow ;;
      --floor) n=3000 f=17500000 s=_floor ;;
      --severe) n=2000 f=17700000 s=_sev ;;
    esac
    grep -q "^done" $O/session_data_spr$s.log 2>/dev/null && continue
    STEER=$STEER $ENV $PY tools/with_native.py scripts/session_data.py $arm --sessions $n --first $f \
      --jobs $J --out $O/session_data_spr$s.csv > $O/session_data_spr$s.log 2>&1
    echo done >> $O/session_data_spr$s.log
    date
  done
  if ! grep -q "^done" $O/outcome_data_general_spr.log 2>/dev/null; then
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 DATA2G_PEP_REF_DB=5 \
      $PY tools/with_native.py scripts/outcome_data.py --samples 40000 --first 17600000 --jobs $J \
      --out $O/outcome_data_general_spr.csv > $O/outcome_data_general_spr.log 2>&1
    echo done >> $O/outcome_data_general_spr.log
  fi
  date
fi
D=$O/session_data_spr.csv,$O/session_data_spr_slow.csv,$O/session_data_spr_high.csv
D=$D,$O/session_data_spr_awgnhigh.csv,$O/session_data_spr_fastlow.csv,$O/session_data_spr_floor.csv
D=$D,$O/session_data_spr_sev.csv,$O/outcome_data_general_spr.csv
D=$D,/home/andrew/code/Data2G/runs/outcome-data/outcome_data_n10top_gt.csv
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
if [[ $phase == members || $phase == all ]]; then
  for k in $(seq 1 12); do
    [ -s $O/sprl$k.npz ] || OMP_NUM_THREADS=4 $PY -m scripts.cnp_outcome "$D" --labels --seed $k --epochs 60 \
      --out $O/sprl$k.npz > $O/sprl$k.log 2>&1 &
    (( k % 3 == 0 )) && wait
  done
  wait
  M=$(for k in $(seq 1 12); do printf "%s," $O/sprl$k.npz; done)
  [ -s $O/sprle12.npz ] || $PY -m scripts.train_outcome x --ensemble ${M%,} --out $O/sprle12.npz
  date
fi
