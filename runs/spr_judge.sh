#!/bin/bash
# Paired loss study for the spr round (PEP 5, shift+cpm, Python shifter with
# DATA2G_OUTCOME_MODEL, offsets as shipped; seeds SEED0..). Arms:
#   base    cohc4 on main runs/spr/tree_old (926d92d: the old CPM spread) = master's behaviour
#   c4new   cohc4 on tree_new (abdbef3): the measurement change alone
#   <name>  main runs/spr/<name>.npz on tree_new
#   runs/spr_judge.sh base c4new sprs46 ...
set -euo pipefail
O=${O:-/home/andrew/code/Data2G/runs/spr}
PY=/home/andrew/code/Data2G/.venv/bin/python
C4=/home/andrew/code/Data2G/runs/sev/shipped_cohc4.npz
SEED0=${SEED0:-1000}
SEEDS=${SEEDS:-24}
cells=""
for c in nvis-d lowlat-d hilat-m hilat-d; do for s in 0 10 20; do cells="$cells$c:$s,"; done; done
cells="${cells}mpd:0,mpd:10,mpd:20,mpp:-6,mpp:0,mpp:10,mpg:0,mpg:10,awgn:0,awgn:10"
cells="${cells},awgn:-18,awgn:-14,mpp:-14,mpp:-12,mpp:-8,mpd:-13,mpg:-8,awgn:-8"
for arm in "$@"; do
  case $arm in
    base) tree=$([ -d $O/tree_old ] && echo $O/tree_old || echo /home/andrew/code/Data2G/runs/spr/tree_old) model=$C4 ;;
    c4new) tree=$O/tree_new model=$C4 ;;
    *) tree=${TREE:-$O/tree_new} model=$O/$arm.npz ;;
  esac
  out=$O/judge_${arm}${TAG:-}_s$SEED0
  if [ -s $out.log ] && grep -q "^wall" $out.log; then continue; fi
  (cd $tree && STEER=$model /usr/bin/time -f "wall %e s" $O/sev_env.sh $PY tools/with_native.py \
    scripts/loss_study.py --out $out.csv --cells "$cells" --seeds $SEEDS --seed0 $SEED0 --horizon 600 --jobs ${J:-12} \
    --policy shift+cpm > $out.log 2>&1)
done
