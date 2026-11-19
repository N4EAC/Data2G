"""Paired chat_probe latency (CHAT_PROBE_OUT json, same seeds): per cell, per-seed mean
latency of delivered messages, B - A, SE, seeds better/worse; undelivered counted apart.

    python scratch/paired_latency.py runs/onod232/winlink_onod0.json runs/onod232/winlink_onod1.json
"""
import json
import sys
from collections import defaultdict

import numpy as np


def load(path):
    out = defaultdict(dict)
    for c, s, k, lat, *_ in json.load(open(path)):
        ok = [x for x in lat if x is not None]
        out[(c, s)][k] = (np.mean(ok) if ok else np.nan, len(lat) - len(ok), len(lat))
    return out


A, B = load(sys.argv[1]), load(sys.argv[2])
print(f"{'cell':11s} {'A s':>7s} {'B s':>7s} {'B-A':>7s} {'SE':>5s}  better/worse  undelivered A/B of n")
for cell in sorted(A):
    seeds = sorted(set(A[cell]) & set(B[cell]))
    a = np.array([A[cell][k][0] for k in seeds])
    b = np.array([B[cell][k][0] for k in seeds])
    d = b - a
    se = d.std(ddof=1) / np.sqrt(len(d))
    ua, ub = sum(A[cell][k][1] for k in seeds), sum(B[cell][k][1] for k in seeds)
    n = sum(A[cell][k][2] for k in seeds)
    print(f"{cell[0]:5s}{cell[1]:+4.0f} {np.nanmean(a):7.2f} {np.nanmean(b):7.2f} {np.nanmean(d):+7.2f} {se:5.2f}"
          f"  {np.sum(d < 0):2d}/{np.sum(d > 0):2d}         {ua}/{ub} of {n}")
