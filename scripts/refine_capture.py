"""Capture equalizer.refine's inputs from uncapped DD decodes (for the low-rank time-pass study).

    PYTHONPATH=.:scripts python scripts/refine_capture.py OUT.pkl MODE:N_CW:CHAN:SNR:SEED ...

Bursts as pi_genburst.py makes them (data slots, data_mask(1, i, 7)); each received and every slot
decoded by phy.ModemRx with no DD budget. Every refine call's arguments are kept.
"""
import pickle
import sys

import numpy as np

from data2g import equalizer, modem
from data2g.arq import phy as PHY
from data2g.arq.burst import Slot, TxBurst, data_mask
from data2g.arq.modes import MODES
from data2g import codes

import phy_session as PS

calls = []
_refine = equalizer.refine


def spy(*a, **k):
    calls.append((a, k))
    return _refine(*a, **k)


equalizer.refine = spy


def run(mode, n, chan, snr, seed):
    s = MODES[mode]
    rng = np.random.default_rng(seed)
    slots = [Slot(data_mask(1, i, 7), 0, bytes(rng.integers(0, 256, codes.payload_bytes(s), dtype=np.uint8)))
             for i in range(n)]
    y = PS.ContinuousChannel(chan, snr, seed, 120.0).apply(PHY.tx_audio(TxBurst(mode, slots, 0, 2)), 10.0)
    r = modem.receive(y)
    rx = PHY.ModemRx(r, {}, None)
    ok = sum(rx.decode(i, data_mask(1, i, 7), 0, None) == sl.payload for i, sl in enumerate(slots))
    print(f"{mode} x{n} {chan} {snr}: {ok}/{n}, refine calls so far {len(calls)}", flush=True)


if __name__ == "__main__":
    for a in sys.argv[2:]:
        m, n, ch, snr, seed = a.split(":")
        run(m, int(n), ch, float(snr), int(seed))
    with open(sys.argv[1], "wb") as f:
        pickle.dump(calls, f)
