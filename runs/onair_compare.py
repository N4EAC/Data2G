"""Paired loss-study comparison in dB (the onair round's judge):
  per cell   delivered bps A/B, %, SE, seeds B>A/B<A; burst loss and first-transmission codeword failure
  per curve  the SNR where each arm first delivers R bps (rate points; shift > 0: B gets there at lower SNR),
             and the SNR where its burst loss / codeword failure falls through 10% (10% failure points)

    python runs/onair_compare.py A.csv B.csv
"""
import csv
import sys
from collections import defaultdict

import numpy as np

RATES = (10, 25, 50, 100, 250, 500, 1000, 2000, 4000)


def load(path):
    bps = defaultdict(dict)
    burst = defaultdict(lambda: [0, 0])
    cw = defaultdict(lambda: [0, 0])
    for r in csv.DictReader(open(path)):
        k = (r["channel"], float(r["snr"]))
        bps[k][int(r["seed"])] = max(bps[k].get(int(r["seed"]), 0.0), float(r["delivered_Bps"]) * 8)
        if r["submode"] == "nod":
            continue
        burst[k][0] += r["outcome"] != "ok"
        burst[k][1] += 1
        if r["data_sent"] not in ("", "0"):
            cw[k][0] += int(r["data_sent"]) - int(r["data_ok"])
            cw[k][1] += int(r["data_sent"])
    return bps, burst, cw


def cross_up(snr, y, level):
    """The lowest SNR where the curve (made non-decreasing from the top down) reaches level; None if never/always."""
    y = np.minimum.accumulate(np.asarray(y)[::-1])[::-1]  # the curve as reachable from above
    if y[-1] < level or len(y) < 2:
        return None
    if y[0] >= level:
        return f"<={snr[0]:+.0f}"
    i = int(np.argmax(y >= level))
    a, b = np.log(max(y[i - 1], 1e-3)), np.log(y[i])
    return snr[i - 1] + (snr[i] - snr[i - 1]) * (np.log(level) - a) / (b - a) if b > a else snr[i]


def cross_down(snr, f, level=0.10):
    """The lowest SNR from which the failure fraction stays at or under level (linear interpolation)."""
    f = np.asarray(f)
    ok = f <= level
    if not ok[-1]:
        return None
    i = len(f) - 1
    while i > 0 and ok[i - 1]:
        i -= 1
    if i == 0:
        return f"<={snr[0]:+.0f}"
    return snr[i - 1] + (snr[i] - snr[i - 1]) * (f[i - 1] - level) / (f[i - 1] - f[i])


def fmt(v):
    return "   -  " if v is None else (f"{v:>6s}" if isinstance(v, str) else f"{v:+6.1f}")


def shift(a, b):
    return "" if a is None or b is None or isinstance(a, str) or isinstance(b, str) else f"{a - b:+5.1f}"


def main(pa, pb):
    (A, LA, CA), (B, LB, CB) = load(pa), load(pb)
    print(f"{'cell':16s} {'A bps':>8s} {'B bps':>8s} {'%':>7s} {'+-SE':>6s}  B>A/B<A  burst loss A/B  cw fail A/B")
    for k in sorted(A, key=lambda k: (k[0], k[1])):
        seeds = sorted(set(A[k]) & set(B.get(k, {})))
        if not seeds:
            continue
        x, y = np.array([A[k][s] for s in seeds]), np.array([B[k][s] for s in seeds])
        d = y - x
        se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else float("nan")
        m = max(x.mean(), 1e-9)
        la, lb = LA[k][0] / max(LA[k][1], 1), LB[k][0] / max(LB[k][1], 1)
        ca, cb = CA[k][0] / max(CA[k][1], 1), CB[k][0] / max(CB[k][1], 1)
        print(f"{k[0]:8s}{k[1]:+4.0f} dB {x.mean():8.0f} {y.mean():8.0f} {100 * d.mean() / m:+6.1f}% {100 * se / m:5.1f}%"
              f"  {np.sum(d > 0):2d}/{np.sum(d < 0):<2d}   {la:5.1%} {lb:5.1%}   {ca:5.1%} {cb:5.1%}")
    chans = defaultdict(list)
    for k in A:
        chans[k[0]].append(k[1])
    print("\nrate points: SNR (dB) where mean delivered bps first reaches R, A / B (shift A-B: + is B better)")
    print(f"{'curve':10s}" + "".join(f"{r:>18d}" for r in RATES))
    for c, snrs in sorted(chans.items()):
        snrs = sorted(s for s in snrs if (c, s) in B)
        if len(snrs) < 3:
            continue
        line = f"{c:10s}"
        for r in RATES:
            a = cross_up(snrs, [np.mean(list(A[(c, s)].values())) for s in snrs], r)
            b = cross_up(snrs, [np.mean(list(B[(c, s)].values())) for s in snrs], r)
            line += f" {fmt(a)}/{fmt(b)} {shift(a, b):>4s}"
        print(line)
    print("\n10% failure points: SNR (dB) from which burst loss / first-transmission codeword failure stays <= 10%, A / B")
    for c, snrs in sorted(chans.items()):
        snrs = sorted(s for s in snrs if (c, s) in B)
        if len(snrs) < 3:
            continue
        out = []
        for L in ((LA, LB), (CA, CB)):
            a = cross_down(snrs, [L[0][(c, s)][0] / max(L[0][(c, s)][1], 1) for s in snrs])
            b = cross_down(snrs, [L[1][(c, s)][0] / max(L[1][(c, s)][1], 1) for s in snrs])
            out.append(f"{fmt(a)}/{fmt(b)} {shift(a, b):>5s}")
        print(f"{c:10s} burst {out[0]}   codeword {out[1]}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
