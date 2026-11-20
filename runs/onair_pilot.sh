#!/bin/bash
# Sizing pilot for runs/onair_round.sh: 12 sessions of each kind (--agc,
# passband default) and 120 offline samples, 6 workers, timed (CPU, peak RSS).
# Seeds 19900000+ (pilot only, not in any set).   runs/onair_pilot.sh
set -euo pipefail
cd "$(dirname "$0")/.."
O=/home/andrew/code/Data2G/runs/onair/pilot
PY=/home/andrew/code/Data2G/.venv/bin/python
E=runs/onair_env.sh
f=19900000
for arm in "" "--slow" "--high" "--high --kinds awgn" "--fastlow" "--floor" "--severe" "--short" "--interference" \
           "--interference --slow"; do
  tag=$(echo "x$arm" | tr -c 'a-z0-9\n' '_')
  /usr/bin/time -v $E $PY tools/with_native.py scripts/session_data.py $arm --agc --sessions 12 --first $f --jobs 6 \
    --out $O/s$tag.csv > $O/s$tag.log 2>&1
  f=$((f + 1000))
done
/usr/bin/time -v $E $PY tools/with_native.py scripts/outcome_data.py --samples 120 --first 19990000 --jobs 6 \
  --out $O/o_general.csv > $O/o_general.log 2>&1
/usr/bin/time -v $E $PY tools/with_native.py scripts/outcome_data.py --cands n10-64l-r3/4,n10-256l-r3/4 --samples 120 \
  --first 19995000 --jobs 6 --out $O/o_n10top.csv > $O/o_n10top.log 2>&1
for l in $O/*.log; do
  printf "%-40s %s\n" "$(basename $l)" "$(grep -E 'User time|System time|Elapsed|Maximum resident' $l | awk -F': ' '{printf "%s ", $2}') rows $(($(wc -l < ${l%.log}.csv) - 1))"
done
