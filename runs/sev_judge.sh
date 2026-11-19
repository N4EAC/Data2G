#!/bin/bash
# Paired loss study: cohc4 alone (base) vs cohc4 with sevle12 routed where the
# peer's median spread_est >= SPREAD (DATA2G_OUTCOME_FAST, any SNR). PEP 5,
# shift+cpm, Python shifter (DATA2G_OUTCOME_MODEL set), seeds SEED0.. (fresh:
# 0-11 were the first severe study's).   SPREAD=2.6 runs/sev_judge.sh [arm...]
set -euo pipefail
T=$(cd "$(dirname "$0")/.." && pwd)
cd $T
PY=/home/andrew/code/Data2G/.venv/bin/python
O=/home/andrew/code/Data2G/runs/sev
SPREAD=${SPREAD:?set SPREAD}
SEED0=${SEED0:-1000}
SEEDS=${SEEDS:-24}
cells=""
for c in nvis-d lowlat-d hilat-m hilat-d; do for s in 0 10 20; do cells="$cells$c:$s,"; done; done
cells="${cells}mpd:0,mpd:10,mpd:20,mpp:-6,mpp:0,mpp:10,mpg:0,mpg:10,awgn:0,awgn:10,awgn:-14,mpp:-12"
for arm in ${@:-base routed}; do
  out=$O/judge_${arm}_s${SEED0} fast=""
  if [[ $arm == routed ]]; then
    out=${out}_sp$SPREAD fast="$O/sevle12.npz:$SPREAD:-99:99"
  fi
  if [ -s $out.log ] && grep -q "^wall" $out.log; then continue; fi
  DATA2G_OUTCOME_FAST=$fast /usr/bin/time -f "wall %e s" runs/sev_env.sh $PY tools/with_native.py \
    scripts/loss_study.py --out $out.csv --cells "$cells" --seeds $SEEDS --seed0 $SEED0 --horizon 600 --jobs 8 \
    --policy shift+cpm > $out.log 2>&1
done
