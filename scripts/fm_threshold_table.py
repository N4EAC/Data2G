"""FM plan M6, provisional: codes_data/fm/mode_thresholds.json, FM's per-mode
thresholds in the receiver's own measure (snr_est, what the gear shifter
sees), so an FM ARQ session can choose among f55 / f108 rungs before the FM
outcome model exists.

For each f55 / f108 rung and condition, the snr_est the receiver reports at
the rung's measured 10% knee (runs/fm_ladder/shipped.csv: CNR and drive),
averaged over bursts that synced. f55 is shared by mic and flat stations and
the shifter does not yet know the peer's TX path (M6's capability per
direction), so each f55 threshold is the worse (higher) of the two paths.
Columns (policy.MODE_CHANNELS on FM): static, flutter (440 MHz), mobile
(mobile-rural), worst (their max). The floor and ACK rungs FM keeps (w, n10
up to index 15) were not measured on FM: HF's awgn, mpg, mpp, mpd thresholds
stand in for static, flutter, mobile, worst (same snr_est units).

    DATA2G_PROFILE=fm python scripts/fm_threshold_table.py [--trials 8] [--workers 8]
"""

import os

# before numpy: each worker one BLAS thread (8 workers on a shared machine)
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fm_ladder_study as L
import fm_spacing_study as S

COLS = {"static": "static", "flutter@440": "flutter", "mobile-rural": "mobile"}


def snr_at_knee(args) -> tuple:
    """Mean snr_est of synced bursts at the knee CNR (nan: none synced)."""
    name, radio, cond, cnr, drive, trials = args
    from data2g import fmchannel as F
    from data2g import modem
    from data2g.arq import phy as PHY

    spec = L.spec_of(name)
    c, mhz = (cond.split("@") + ["146"])[:2]
    vals = []
    for t in range(trials):
        _, x = L.burst(spec, 2000 + t, radio)
        ch = F.FmChannel(c, S.radio_of(radio), cnr, seed=500 + t, duration_s=len(x) / 16000 + 2, carrier_mhz=float(mhz),
                         drive_dev_hz=drive)
        try:
            vals.append(PHY.measure(modem.receive(ch.apply(x)))["snr_est"])
        except modem.SyncError:  # not synced at the knee: says nothing about snr_est
            pass
    return name, radio, cond, float(np.mean(vals)) if vals else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    from data2g import config
    from data2g.arq import modes

    assert config.PROFILE == "fm", "run under DATA2G_PROFILE=fm"
    with (L.OUT / "shipped.csv").open() as f:
        rows = [r for r in csv.DictReader(f) if r["condition"] in COLS]
    jobs = [(r["mode"], r["radio"], r["condition"], float(r["k0.1"]), float(r["drive"]), a.trials) for r in rows
            if r["k0.1"] != "nan"]
    got = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for name, radio, cond, v in ex.map(snr_at_knee, jobs):
            got.setdefault((name, COLS[cond]), []).append(v)
            print(name, radio, cond, round(v, 2), flush=True)
    hf = json.loads((Path(config.__file__).parent / "codes_data" / "mode_thresholds.json").read_text())["modes"]
    out = {}
    for name, s in ((n, s) for n, s in modes.MODES.items() if n in modes.SELECTABLE):
        if s.sync_band in ("f55", "f108"):
            # a knee never reached (nan) on a path: that path is unusable there
            t = [max(got.get((name, col), [float("nan")]), key=lambda v: np.inf if np.isnan(v) else v)
                 for col in ("static", "flutter", "mobile")]
            t = [99.0 if np.isnan(v) or np.isinf(v) else round(v, 2) for v in t]
            out[name] = [*t, max(t)]
        elif name in hf:
            out[name] = hf[name]
    path = Path(config.__file__).parent / "codes_data" / "fm" / "mode_thresholds.json"
    note = ("FM, provisional (scripts/fm_threshold_table.py): snr_est at each f55/f108 rung's 10% knee "
            "(runs/fm_ladder/shipped.csv), f55 the worse of mic and flat; w and n10 floor rungs: HF's awgn, mpg, "
            "mpp, mpd. Replaced by the FM threshold table (plan M6).")
    path.write_text(json.dumps({"note": note, "channels": ["static", "flutter", "mobile", "worst"], "modes": out},
                               indent=1) + "\n")
    print("wrote", path, len(out), "modes")


if __name__ == "__main__":
    main()
