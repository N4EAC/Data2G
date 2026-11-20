#!/bin/bash
# Paired loss study for the onair round (PEP 5, shift+cpm, Python shifter with
# DATA2G_OUTCOME_MODEL, offsets as shipped, same seeds every arm), on the
# integration tree (this checkout). Arms: base = the installed sprs46f, <name>
# = main runs/onair/<name>.npz. SET: grid (awgn/mpg/mpp/mpd -8..+20 by 4, the
# CPM floor and edge cells, the on-air presets mpa/mpl, two severe profiles) or
# pb (--passband: clean and onair-interfered cells).
#   SEED0=2000 SET=grid runs/onair_judge.sh base onb   (R=onair2: models and output in main runs/onair2)
set -euo pipefail
cd "$(dirname "$0")/.."
O=/home/andrew/code/Data2G/runs/${R:-onair}
PY=/home/andrew/code/Data2G/.venv/bin/python
SEED0=${SEED0:-2000}
SEEDS=${SEEDS:-12}
SET=${SET:-grid}
cells="" extra=()
if [[ $SET == grid ]]; then
  for c in awgn mpg mpp mpd; do for s in -8 -4 0 4 8 12 16 20; do cells="$cells$c:$s,"; done; done
  cells="${cells}awgn:-18,awgn:-14,mpp:-14,mpp:-12,mpd:-13,mpg:-12,"
  for c in mpa mpl; do for s in -8 -4 0 4 8 12 16 20; do cells="$cells$c:$s,"; done; done
  cells="${cells}nvis-d:0,nvis-d:10,hilat-d:0,hilat-d:10"
else
  for c in awgn mpg mpp mpa; do for s in 0 8; do cells="$cells$c:$s,$c:$s:onair,"; done; done
  cells=${cells%,}
  extra=(--passband)
fi
for arm in "$@"; do
  case $arm in
    base) model=/home/andrew/code/Data2G/runs/onair/shipped_sprs46f.npz ;;
    *) model=$O/$arm.npz ;;
  esac
  out=$O/judge_${arm}_${SET}_s$SEED0
  if [ -s $out.log ] && grep -q "^wall" $out.log; then continue; fi
  STEER=$model /usr/bin/time -f "wall %e s" runs/onair_env.sh $PY tools/with_native.py scripts/loss_study.py \
    --out $out.csv --cells "$cells" --seeds $SEEDS --seed0 $SEED0 --horizon 600 --jobs ${J:-6} --policy shift+cpm \
    "${extra[@]}" > $out.log 2>&1
done
