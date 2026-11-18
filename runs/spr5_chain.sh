#!/bin/bash
# spr5: spr4 (robust mode by spread, 9f2314e) + the #244 fix (54f4c62: Doppler
# spill counted in the CPM tone metric). The fix changes fsk16r25 on ~30 Hz
# fading only (unchanged within one trial on the AWGN/MPP/MPD floors and the
# 10 Hz profiles), so only the severe set is regenerated; spr4's other sets
# are linked. Base arm: cohc4 on spr3's tree_old (926d92d + #243) + #244.
#   runs/spr5_chain.sh
set -euo pipefail
cd "$(dirname "$0")/.."
R=/home/andrew/code/Data2G/runs
export O=$R/spr5
cp -n $R/spr/sev_env.sh $O/
# 1. the severe set on the fixed tree (spr_round.sh's --severe arm alone)
(cd $O/tree_new && STEER=$R/sev/shipped_cohc4.npz $O/sev_env.sh /home/andrew/code/Data2G/.venv/bin/python \
  tools/with_native.py scripts/session_data.py --severe --sessions 2000 --first 17700000 --jobs ${J:-8} \
  --out $O/session_data_spr_sev.csv > $O/session_data_spr_sev.log 2>&1)
echo done >> $O/session_data_spr_sev.log
date
# 2. spr4's other sets, once its offline set is done
until grep -q "^done" $R/spr4/outcome_data_general_spr.log 2>/dev/null; do sleep 120; done
for f in session_data_spr session_data_spr_slow session_data_spr_high session_data_spr_awgnhigh \
         session_data_spr_fastlow session_data_spr_floor outcome_data_general_spr; do
  ln -sf $R/spr4/$f.csv $O/$f.csv
  ln -sf $R/spr4/$f.log $O/$f.log
done
date
# 3. members, students, judge, after spr4's students: the GPU is shared (12% per
# process, three at a time), so the two rounds must not train at once
until [ -s $R/spr4/sprs35f.npz ]; do sleep 120; done
runs/spr_round.sh members > $O/spr_round.log 2>&1
runs/spr_train.sh > $O/spr_train.log 2>&1
J=12 runs/spr_judge.sh base sprs46 sprs35 sprs46f sprs35f
date
