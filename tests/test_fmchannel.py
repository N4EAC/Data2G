"""data2g.fmchannel: the FM channel simulator behaves like FM (FM plan, M1)."""

import numpy as np
import pytest

from data2g import codes, fmchannel as F, modem
from data2g.config import FS, SUBMODES


def _tone(seconds=2.0, f=1000.0):
    t = np.arange(int(seconds * FS)) / FS
    return np.sin(2 * np.pi * f * t), np.stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t)], 1)


def _tone_snr(y, basis):
    """Audio SNR and click count of a received tone, after the radios' phase shift."""
    y, basis = y[FS // 2:], basis[FS // 2:]
    c, *_ = np.linalg.lstsq(basis, y, rcond=None)
    fit = basis @ c
    err = y - fit
    return 10 * np.log10(np.mean(fit**2) / np.mean(err**2)), int(np.sum(np.abs(err) > 3 * np.std(fit)))


@pytest.mark.parametrize("radio", ["mic", "flat"])
def test_clean_above_threshold_clicks_below(radio):
    """Above threshold the tone comes through near the radios' ceiling and
    without clicks; below it (3 dB CNR) the discriminator clicks."""
    x, basis = _tone()
    snr, clicks = _tone_snr(F.apply_channel(x, 40, "static", radio, seed=1), basis)
    assert snr > 30 and clicks == 0
    assert _tone_snr(F.apply_channel(x, 15, "static", radio, seed=1), basis)[1] == 0
    assert _tone_snr(F.apply_channel(x, 3, "static", radio, seed=1), basis)[1] > 50


def test_de_emphasis_quiets_the_mic_path():
    """At one CNR above threshold the mic path's de-emphasis takes the
    discriminator's rising noise down: its audio SNR beats the flat path's."""
    x, basis = _tone()
    mic = _tone_snr(F.apply_channel(x, 15, "static", "mic", seed=2), basis)[0]
    flat = _tone_snr(F.apply_channel(x, 15, "static", "flat", seed=2), basis)[0]
    assert mic > flat + 3


def test_occupied_bandwidth_of_a_tone():
    """1 kHz at 2.5 kHz peak deviation: about Carson's 7 kHz (which holds
    ~98% of the power), measured."""
    x, _ = _tone()
    s, rf = F.rf_signal(x, "flat", 2500 / np.sqrt(2))
    w = F.occupied_bandwidth(s, rf)
    assert 6500 < w["obw99"] < 9000 and 6500 < w["db26"] < 9500


def test_drive_for_bandwidth_meets_the_limit():
    x = np.random.default_rng(0).normal(size=FS)
    d, w = F.drive_for_bandwidth(x, "flat", 12_000)
    assert max(w.values()) <= 12_000
    s, rf = F.rf_signal(x, "flat", d * 1.1)
    assert max(F.occupied_bandwidth(s, rf).values()) > 12_000


def test_rayleigh_tap_power_and_level_crossings():
    """One classical tap: unit mean power, and Rice's level-crossing rate at
    the rms level, sqrt(2 pi) fd rho exp(-rho^2) = 0.92 fd."""
    cond = F.Condition("one", (F.Tap(0.0),), doppler_hz=10.0)
    ch = F.FmChannel(cond, duration_s=400.0, seed=3)
    t = np.arange(0, 400.0, 1 / 2000)
    p = 10 ** (ch.path_gain_db(t) / 10)
    assert abs(10 * np.log10(p.mean())) < 0.5
    up = np.sum((p[:-1] < 1) & (p[1:] >= 1)) / 400.0
    assert abs(up / (0.92 * 10.0) - 1) < 0.15


def test_gauss_markov_sigma_and_correlation():
    g = F.gauss_markov_db(200_000, 10.0, 5.0, 30.0, np.random.default_rng(4))
    assert abs(g.std() - 5.0) < 0.6
    lag = 300  # tau_s at 10 Hz
    assert abs(np.corrcoef(g[:-lag], g[lag:])[0, 1] - np.exp(-1)) < 0.1


def test_same_seed_same_fading_at_any_cnr():
    """Ladder runs are paired: the seed fixes the path, the CNR only the noise."""
    t = np.linspace(0, 10, 500)
    a = F.FmChannel("mobile-urban", cnr_db=5, seed=7, duration_s=20).path_gain_db(t)
    b = F.FmChannel("mobile-urban", cnr_db=25, seed=7, duration_s=20).path_gain_db(t)
    assert np.array_equal(a, b)


def test_every_condition_runs():
    x, _ = _tone(0.5)
    for name in F.CONDITIONS:
        y = F.apply_channel(x, 20, name, "flat", seed=0)
        assert y.shape == x.shape and np.isfinite(y).all(), name


@pytest.mark.parametrize("radio", ["mic", "flat"])
def test_a_burst_decodes_through_the_radios(radio):
    """A real burst over a clean FM link: every codeword decodes. Mic: a
    1200 Hz mode inside the voice band; flat: the 2400 Hz one."""
    spec = SUBMODES["16qam-r1/2" if radio == "mic" else "w48-16qam-r1/2"]
    rng = np.random.default_rng(5)
    sent = [rng.bytes(codes.payload_bytes(spec)) for _ in range(3)]
    x = np.concatenate([np.zeros(FS // 2), modem.modulate(sent, spec), np.zeros(FS // 2)])
    b = modem.demodulate(F.apply_channel(x, 30, "static", radio, seed=6))
    assert b.payloads == sent and all(b.crc_ok)
