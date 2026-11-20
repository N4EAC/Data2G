#!/bin/bash
# The onair round's model, cnpd's recipe (runs/cnple_round.sh, runs/cnpd_round.sh) on the onair mix: five CNPs on
# the outcomes (--labels, seeds 1-5, 60 epochs), ensembled (onle5), distilled into one CNP with LCB 0.5 and
# qpsk-r1/5 -1.0 on fast fading under -2 dB (onb). GPU shared: 12% per process (cnp_outcome), two at a time.
#   runs/onair_train.sh   (R=onair2 P=oa2: the second round, on the revised passband draw)
set -euo pipefail
cd "$(dirname "$0")/.."
O=/home/andrew/code/Data2G/runs/${R:-onair}
A=/home/andrew/code/Data2G/runs/outcome-data
PY=/home/andrew/code/Data2G/.venv/bin/python
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
D=""
for s in "" _slow _high _awgnhigh _fastlow _floor _sev _short _intf _intf_slow _intf_high; do D="$D$A/session_data_${P:-oa}$s.csv,"; done
D="$D$A/outcome_data_general_${P:-oa}.csv,$A/outcome_data_n10top_${P:-oa}.csv"
for k in 1 2 3 4 5; do
  [ -s $O/onl$k.npz ] || $PY -m scripts.cnp_outcome "$D" --labels --seed $k --epochs 60 --out $O/onl$k.npz \
    > $O/onl$k.log 2>&1 &
  (( k % 2 == 0 )) && wait
done
wait
[ -s $O/onle5.npz ] || $PY -m scripts.train_outcome x --ensemble $O/onl1.npz,$O/onl2.npz,$O/onl3.npz,$O/onl4.npz,$O/onl5.npz \
  --out $O/onle5.npz
[ -s $O/onb.npz ] || DATA2G_OUTCOME_LCB=0.5 $PY -m scripts.cnp_outcome "$D" --teacher $O/onle5.npz \
  --cond "0.7:-2:qpsk-r1/5:-1.0" --epochs 40 --out $O/onb.npz > $O/onb.log 2>&1
date
