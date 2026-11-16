"""FM's own bands, f55 (450..3150 Hz) and f108 (300..5650 Hz): every
provisional submode round-trips clean, and through the FM channel
simulator at high CNR on the radio path it is meant for. FM profile only."""

import numpy as np
import pytest

from data2g import codes, config, fmchannel, modem
from data2g.config import FS, SUBMODES

pytestmark = pytest.mark.skipif(config.PROFILE != "fm", reason="FM's bands exist under DATA2G_PROFILE=fm only")
NAMES = [n for n, s in SUBMODES.items() if s.band in ("f55", "f108")]


def _burst(spec, seed, n_cw=2):
    rng = np.random.default_rng(seed)
    sent = [rng.bytes(codes.payload_bytes(spec)) for _ in range(n_cw)]
    return sent, np.concatenate([np.zeros(FS // 2), modem.modulate(sent, spec), np.zeros(FS // 2)])


def _decoded(y, spec):
    r = modem.receive(y)
    assert r["spec"].name == spec.name
    return modem.decode_received(r)


@pytest.mark.parametrize("name", NAMES)
def test_round_trip_clean(name):
    spec = SUBMODES[name]
    sent, x = _burst(spec, 1)
    b = _decoded(x + 1e-3 * np.random.default_rng(0).standard_normal(len(x)), spec)
    assert b.payloads == sent and all(b.crc_ok)


# narrow on the mic path (the radio model passes 300..3000 Hz, so f55's top
# carriers ride its skirt), wide on a 9600 port; robust and middle modes
@pytest.mark.parametrize("name,radio", [("f55-qpsk-r1/2", "mic"), ("f55-16qam-r1/2", "mic"), ("f55-16qam-r1/2", "flat"),
                                        ("f108-qpsk-r1/2", "flat"), ("f108-16qam-r1/2", "flat")])
def test_through_the_fm_channel(name, radio):
    spec = SUBMODES[name]
    sent, x = _burst(spec, 2)
    drive = fmchannel.drive_for_bandwidth(x[np.abs(x) > 0], radio, 15_000.0)[0]
    y = fmchannel.apply_channel(x, 36.0, "static", radio, seed=3, drive_dev_hz=drive)
    b = _decoded(y, spec)
    assert b.payloads == sent and all(b.crc_ok)
