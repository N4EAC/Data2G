#!/bin/bash
# Environment of the severe round (as runs/cohm/cohm_round.sh), then exec "$@".
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export DATA2G_PEP_REF_DB=5 DATA2G_SPREAD_CARRY=1
export DATA2G_LOGIT_OFFSETS=w48-16qam-r1/2:-1.0,n10-256l-r3/4:-0.5
export DATA2G_OUTCOME_MODEL=${STEER:-/home/andrew/code/Data2G/runs/sev/shipped_cohc4.npz}
exec "$@"
