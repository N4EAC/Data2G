#!/bin/bash
# The onair round (#262): the outcome data regenerated on the integration of
# #263-#269 + false-lock-not-reported, where every input moved (snr_est noise
# #258, NoiseProfile mutes #255, energy AGC gauge #257, passband #260). The
# spr4/spr5 mix's kinds and sizes, plus --short (#261), interference sets on
# the onair draws (#260, a third of their clean sets' size), the on-air
# presets through KINDS (#259); --agc on every session set (#257); passband
# on (default). Steered by the installed sprs46f (Python shifter). Sequential,
# 6 workers (shared machine; pilot: 0.32 GB peak per worker, ~28 CPU-h).
# Output in main runs/onair.   runs/onair_round.sh
set -euo pipefail
cd "$(dirname "$0")/.."
O=/home/andrew/code/Data2G/runs/onair
PY=/home/andrew/code/Data2G/.venv/bin/python
E=runs/onair_env.sh
J=${J:-6}
for arm in "" "--slow" "--high" "--high --kinds awgn" "--fastlow" "--floor" "--severe" "--short" \
           "--interference" "--interference --slow" "--interference --high"; do
  case $arm in
    "") n=2900 f=19000000 s="" ;;
    --slow) n=800 f=19100000 s=_slow ;;
    --high) n=1200 f=19200000 s=_high ;;
    "--high --kinds awgn") n=400 f=19300000 s=_awgnhigh ;;
    --fastlow) n=1200 f=19400000 s=_fastlow ;;
    --floor) n=3000 f=19500000 s=_floor ;;
    --severe) n=2000 f=19700000 s=_sev ;;
    --short) n=800 f=19800000 s=_short ;;
    --interference) n=1000 f=20000000 s=_intf ;;
    "--interference --slow") n=300 f=20100000 s=_intf_slow ;;
    "--interference --high") n=400 f=20200000 s=_intf_high ;;
  esac
  grep -q "^done" $O/session_data_oa$s.log 2>/dev/null && continue
  /usr/bin/time -v $E $PY tools/with_native.py scripts/session_data.py $arm --agc --sessions $n --first $f --jobs $J \
    --out $O/session_data_oa$s.csv > $O/session_data_oa$s.log 2>&1
  echo done >> $O/session_data_oa$s.log
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
off outcome_data_general_oa --samples 40000 --first 19600000
off outcome_data_n10top_oa --cands n10-64l-r3/4,n10-256l-r3/4 --samples 8000 --first 20300000
