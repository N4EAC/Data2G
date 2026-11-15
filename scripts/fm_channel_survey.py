"""FM plan M1/M0: what the FM channel simulator says, two parts.

    python scripts/fm_channel_survey.py obw            # Q17: drive under the 15 kHz occupied limit
    python scripts/fm_channel_survey.py loss [--trials 20] [--workers 8]

`obw`: band-limited Gaussian audio (what OFDM looks like) with top edges of
3.15, 4.6 and 5.7 kHz, flat and with a +3 dB/octave tilt, through a flat
(9600) port at 16 kHz: the largest rms drive whose RF signal stays within
15 kHz occupied (99% power and -26 dB, the worse), and the peak deviation
that drive makes. Also the mic path for the narrow band (pre-emphasis and
the radio's 5 kHz limiter in the loop).

`loss`: today's ladder (the HF profile's modes, unchanged: the plan's M0
baseline, simulated half) through every fmchannel condition at 146 and
440 MHz, mic and flat radios, the drive set by the 15 kHz limit. Codeword
failure against CNR, seeded per trial (every CNR sees the same fading), and
the CNR where each reaches 10% failure. Writes runs/fm_survey/loss.csv.
"""

import argparse
import csv
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from data2g import codes, fmchannel as F, modem
from data2g.config import FS, SUBMODES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "fm_survey"
CNRS = (4, 6, 8, 10, 12, 14, 17, 20, 24, 28, 33, 40)
MODES = ("qpsk-r1/2", "16qam-r1/2", "w48-16qam-r1/2", "w48-64l-r3/4")
N_CW = 3


# --- obw -----------------------------------------------------------------------------------


def gaussian_band(lo, hi, tilt_db_oct, fs, seconds=4.0, seed=0):
    """Gaussian audio flat (or tilted, dB/octave above lo) between lo and hi Hz."""
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    f = np.fft.rfftfreq(n, 1 / fs)
    a = ((f >= lo) & (f <= hi)) * (np.maximum(f, lo) / lo) ** (tilt_db_oct / 6.02)
    return np.fft.irfft((rng.normal(size=len(f)) + 1j * rng.normal(size=len(f))) * a, n)


def obw(target=15_000.0):
    fs = 16_000
    print(f"rms drive (Hz) for {target / 1e3:g} kHz occupied; peak = 99.99th percentile |deviation|")
    print(f"{'band':>14} {'path':>5} {'tilt':>5} {'drive':>6} {'peak':>6} {'obw99':>6} {'-26dB':>6}")
    cases = [(450, 3150, 0, "mic"), (450, 3150, 0, "flat"), (300, 4600, 0, "flat"), (300, 4600, 3, "flat"),
             (300, 5700, 0, "flat"), (300, 5700, 3, "flat")]
    for lo, hi, tilt, radio in cases:
        x = gaussian_band(lo, hi, tilt, fs)
        d, w = F.drive_for_bandwidth(x, radio, target, fs=fs)
        r = F.RADIOS[radio]
        dev = F.tx_audio(x / np.sqrt(np.mean(x**2)) * d, r, fs)
        peak = np.percentile(np.abs(dev), 99.99)
        print(f"{lo:>6}-{hi:<6} {radio:>5} {tilt:>4}d {d:6.0f} {peak:6.0f} {w['obw99']:6.0f} {w['db26']:6.0f}")


# --- loss ----------------------------------------------------------------------------------


def burst(spec, seed):
    rng = np.random.default_rng(seed)
    sent = [rng.bytes(codes.payload_bytes(spec)) for _ in range(N_CW)]
    return sent, np.concatenate([np.zeros(FS // 2), modem.modulate(sent, spec), np.zeros(FS // 2)])


def drive(mode, radio):
    """Each (mode, radio)'s rms drive under 15 kHz occupied (one burst's audio)."""
    _, x = burst(SUBMODES[mode], 0)
    return F.drive_for_bandwidth(x[np.abs(x) > 0], radio, 15_000.0)[0]


def job(args):
    mode, radio, cond, mhz, trial, d = args
    spec = SUBMODES[mode]
    sent, x = burst(spec, 1000 + trial)
    out = []
    for cnr in CNRS:
        ch = F.FmChannel(cond, radio, cnr, seed=trial, duration_s=len(x) / FS + 2, carrier_mhz=mhz, drive_dev_hz=d)
        try:
            b = modem.demodulate(ch.apply(x))
            ok = sum(p == s and c for p, s, c in zip(b.payloads, sent, b.crc_ok))
        except Exception:  # SyncError and its kin: nothing received
            ok = 0
        out.append((mode, radio, cond, mhz, trial, cnr, N_CW - ok))
    return out


def knee(cnrs, fail, level=0.1):
    """Lowest CNR above which failure stays at or under `level` (interpolated)."""
    cnrs, fail = np.asarray(cnrs, float), np.asarray(fail, float)
    bad = np.nonzero(fail > level)[0]
    if len(bad) == 0:
        return float(cnrs[0])
    i = bad[-1]
    if i == len(cnrs) - 1:
        return float("nan")
    return float(np.interp(level, [fail[i + 1], fail[i]], [cnrs[i + 1], cnrs[i]]))


def loss(trials, workers):
    OUT.mkdir(parents=True, exist_ok=True)
    drives = {(m, r): drive(m, r) for m in MODES for r in ("mic", "flat")}
    for k, v in drives.items():
        print(f"drive {k}: {v:.0f} Hz rms")
    jobs = [(m, r, c, mhz, t, drives[(m, r)]) for m in MODES for r in ("mic", "flat") for c in F.CONDITIONS
            for mhz in F.CARRIERS_MHZ for t in range(trials)]
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for res in ex.map(job, jobs, chunksize=4):
            rows += res
    path = OUT / "loss.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mode", "radio", "condition", "mhz", "trial", "cnr", "lost"])
        w.writerows(rows)
    report(rows, trials)
    print(f"wrote {path}")


def report(rows, trials):
    from collections import defaultdict

    lost = defaultdict(int)
    for mode, radio, cond, mhz, _, cnr, n in rows:
        lost[(mode, radio, cond, mhz, cnr)] += n
    print(f"\nCNR (dB, 15 kHz) for 10% codeword failure; '>40': not reached; {trials} bursts x {N_CW} a point")
    for mode in MODES:
        for radio in ("mic", "flat"):
            print(f"\n{mode} / {radio}")
            print(f"{'condition':>18} " + " ".join(f"{m:>6.0f}" for m in F.CARRIERS_MHZ))
            for cond in F.CONDITIONS:
                ks = []
                for mhz in F.CARRIERS_MHZ:
                    fail = [lost[(mode, radio, cond, mhz, c)] / (trials * N_CW) for c in CNRS]
                    k = knee(CNRS, fail)
                    ks.append(">40" if np.isnan(k) else f"{k:.1f}")
                print(f"{cond:>18} " + " ".join(f"{k:>6}" for k in ks))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["obw", "loss"])
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(v, "1")
    obw() if a.part == "obw" else loss(a.trials, a.workers)


if __name__ == "__main__":
    main()
