#!/bin/bash
# The onair round again (runs/onair_round.sh) after the passband draw was
# revised (27a4f88: a drawn 2.7-3.1 kHz SSB filter 85%, narrow 5%, flat 10%):
# every set drew a passband, so every set is regenerated. Same kinds, sizes and
# flags; seeds +2000000. Steered by the installed sprs46f. Output in main runs/onair2.
#   runs/onair2_round.sh
set -euo pipefail
cd "$(dirname "$0")/.."
O=/home/andrew/code/Data2G/runs/onair2
PY=/home/andrew/code/Data2G/.venv/bin/python
E=runs/onair_env.sh
J=${J:-6}
for arm in "" "--slow" "--high" "--high --kinds awgn" "--fastlow" "--floor" "--severe" "--short" \
           "--interference" "--interference --slow" "--interference --high"; do
  case $arm in
    "") n=2900 f=21000000 s="" ;;
    --slow) n=800 f=21100000 s=_slow ;;
    --high) n=1200 f=21200000 s=_high ;;
    "--high --kinds awgn") n=400 f=21300000 s=_awgnhigh ;;
    --fastlow) n=1200 f=21400000 s=_fastlow ;;
    --floor) n=3000 f=21500000 s=_floor ;;
    --severe) n=2000 f=21700000 s=_sev ;;
    --short) n=800 f=21800000 s=_short ;;
    --interference) n=1000 f=22000000 s=_intf ;;
    "--interference --slow") n=300 f=22100000 s=_intf_slow ;;
    "--interference --high") n=400 f=22200000 s=_intf_high ;;
  esac
  grep -q "^done" $O/session_data_oa2$s.log 2>/dev/null && continue
  /usr/bin/time -v $E $PY tools/with_native.py scripts/session_data.py $arm --agc --sessions $n --first $f --jobs $J \
    --out $O/session_data_oa2$s.csv > $O/session_data_oa2$s.log 2>&1
  echo done >> $O/session_data_oa2$s.log
  date
done
off() {  # name, args...
  local name=$1; shift
  grep -q "^done" $O/$name.log 2>/dev/null && return
  /usr/bin/time -v env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 DATA2G_PEP_REF_DB=5 \
    $PY tools/with_native.py scripts/outcome_data.py "$@" --jobs $J --out $O/$name.csv > $O/$name.log 2>&1
  echo done >> $O/$name.log
  date
}
off outcome_data_general_oa2 --samples 40000 --first 21600000
off outcome_data_n10top_oa2 --cands n10-64l-r3/4,n10-256l-r3/4 --samples 8000 --first 22300000
