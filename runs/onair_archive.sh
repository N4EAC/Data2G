#!/bin/bash
# Copy the onair round's sets into main runs/outcome-data with MANIFEST.sha256 entries (sha256, rows); never overwrite. R=onair2 P=oa2 for the second round.
set -euo pipefail
O=/home/andrew/code/Data2G/runs/${R:-onair}
A=/home/andrew/code/Data2G/runs/outcome-data
for s in "" _slow _high _awgnhigh _fastlow _floor _sev _short _intf _intf_slow _intf_high; do
  set -- "$@" session_data_${P:-oa}$s.csv
done
for f in "$@" outcome_data_general_${P:-oa}.csv outcome_data_n10top_${P:-oa}.csv; do
  if [ -e $A/$f ]; then echo "exists: $f"; continue; fi
  cp $O/$f $A/$f
  echo "$(sha256sum < $A/$f | cut -d' ' -f1)  $(($(wc -l < $A/$f) - 1))  $f" >> $A/MANIFEST.sha256
done
tail -13 $A/MANIFEST.sha256
cd $A && tail -13 MANIFEST.sha256 | awk '{print $1"  "$3}' | sha256sum -c --quiet && echo "verified"
