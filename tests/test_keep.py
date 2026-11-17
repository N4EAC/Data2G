"""T_KEEP (docs/arq.md §8a): T_REPLY only when it changes, once both stations
keep it. At link level: T_KEEP until acted on, the listener's reply
recommendation always the one the sender means through lost bursts and nods,
and a peer that never said T_KEEP gets T_REPLY in every control as before."""

import random

import pytest

from data2g.arq import frames as F
from data2g.arq import link as L

from test_arq import payload
from test_nod import AskingPolicy, FullRx, _ctl


def run(seed, a_keep=True, b_keep=True, nods=False, max_turns=3000):
    """Lockstep, 15% of bursts lost: -> (a, b, controls read, of them without T_REPLY)."""
    rng = random.Random(seed)
    data_a, data_b = payload(rng, 1500, "mixed"), payload(rng, 100, "mixed")
    a = L.Station(0, AskingPolicy(random.Random(seed + 1)), master=True, nod=nods, keep=a_keep)
    b = L.Station(1, AskingPolicy(random.Random(seed + 2)), nod=nods, keep=b_keep)
    a.write(data_a)
    b.write(data_b)
    got_a, got_b, n, bare = bytearray(), bytearray(), 0, 0
    burst, sender = a.build(nod=True), a
    for _ in range(max_turns):
        receiver = b if sender is a else a
        ok = False
        if rng.random() >= 0.15:
            said = sender._reply_by_bn[sender._latest]
            if burst.nod is not None:
                before = receiver.peer_reply_recommend
                ok = receiver.handle(receiver.nod_rx(burst.nod[0]))
                assert ok and receiver.peer_reply_recommend == before
            else:
                ext = _ctl(burst).ext
                ok = receiver.handle(FullRx(burst))
                assert ok
                n += 1
                bare += F.T_REPLY not in ext
                if not (sender.keep and receiver.keep):
                    # as before T_KEEP: the control's T_REPLY, or none
                    assert receiver.peer_reply_recommend == (ext[F.T_REPLY][0] if ext.get(F.T_REPLY) else None)
            if said != L._UNKNOWN:
                assert receiver.peer_reply_recommend == said, (said, receiver.peer_reply_recommend)
        got_a += a.read()
        got_b += b.read()
        assert a.state != L.FAILED and b.state != L.FAILED, (a.fail_reason, b.fail_reason)
        if got_a == data_b and got_b == data_a and not a.tx.pending() and not b.tx.pending():
            return a, b, n, bare
        if ok:
            burst, sender = receiver.build(nod=True), receiver
            receiver.answered()
        else:
            burst, sender = a.on_timeout(), a
            assert burst is not None, a.fail_reason
    raise AssertionError("stuck")


@pytest.mark.parametrize("nods", [False, True])
@pytest.mark.parametrize("seed", range(6))
def test_reply_is_kept_through_losses(seed, nods, monkeypatch):
    monkeypatch.setattr(L, "NOD", True)
    a, b, n, bare = run(seed, nods=nods)
    assert a._keeping and b._keeping and a._keep_told and b._keep_told
    assert bare > n // 4, (bare, n)  # most recommendations repeat the last


@pytest.mark.parametrize("a_keep,b_keep", [(True, False), (False, True), (False, False)])
def test_a_peer_that_never_said_gets_t_reply(a_keep, b_keep):
    """One station without T_KEEP (a v5 peer before it, or DATA2G_KEEP=0):
    neither leaves T_REPLY out as unchanged, neither keeps it (run checks
    each control), and the one that says T_KEEP stops once it is acted on."""
    a, b, n, bare = run(1, a_keep, b_keep)
    assert not a._keeping and not b._keeping
    assert a.keep_peer == b_keep and b.keep_peer == a_keep
    assert a._keep_told == a_keep and b._keep_told == b_keep


def test_t_keep_until_acted_on_then_t_reply_only_on_change():
    modes = ("fsk16r25-r1/2",)
    a = L.Station(0, AskingPolicy(random.Random(1), 0.0, modes, p_kept=0.0), master=True, keep=True)
    b = L.Station(1, AskingPolicy(random.Random(2), 0.0, modes, p_kept=0.0), keep=True)
    a.policy.reply, b.policy.reply = 3, 7
    a.write(payload(random.Random(3), 4000, "mixed"))
    x = a.build()
    assert F.T_KEEP in _ctl(x).ext and F.T_REPLY in _ctl(x).ext
    a.on_timeout()  # lost: still unacknowledged
    x = a.on_timeout(allow_repeat=False)
    assert F.T_KEEP in _ctl(x).ext and not a._keep_told
    assert b.handle(FullRx(x)) and b.keep_peer and not b._keeping
    r = b.build()
    assert F.T_KEEP in _ctl(r).ext and F.T_REPLY in _ctl(r).ext  # a has not acted on b's yet
    assert a.handle(FullRx(r)) and a._keeping
    want = a.peer_reply_recommend
    x = a.build()
    assert F.T_KEEP not in _ctl(x).ext
    assert F.T_REPLY not in _ctl(x).ext  # b acted on the burst that said it: it holds it
    assert b.handle(FullRx(x)) and b._keeping and b.peer_reply_recommend == 3
    r = b.build()
    assert F.T_REPLY not in _ctl(r).ext and F.T_KEEP not in _ctl(r).ext  # as a holds it
    assert a.handle(FullRx(r)) and a.peer_reply_recommend == want
    # a change is said, and so is "none" (an empty T_REPLY: left out, a would keep the last)
    a.policy.recommend = lambda st: (0, 1, None)
    x = a.build()
    assert _ctl(x).ext[F.T_REPLY] == b""
    assert b.handle(FullRx(x)) and b.peer_reply_recommend is None
    assert a.handle(FullRx(b.build()))
    x = a.build()
    assert F.T_REPLY not in _ctl(x).ext
    assert b.handle(FullRx(x)) and b.peer_reply_recommend is None


def test_t_keep_takes_t_replys_place_in_a_full_control():
    """An OFDM ACK mode's control (4 B a codeword) is full with T_REPLY: T_KEEP
    goes in its place until acted on, and once both keep it the usual control is
    its core alone, one codeword instead of two."""
    class Tight(AskingPolicy):
        want_dup = False

        def payload_bytes(self, m):
            return 4

        def ctl_payload_bytes(self, m):
            return 4

        def max_ctl(self, m):
            return 4

        def rv_cycle(self, m):
            return 4

    a = L.Station(0, Tight(random.Random(1), 0.0, ("ack-4f",), p_kept=0.0), master=True, keep=True)
    b = L.Station(1, Tight(random.Random(2), 0.0, ("ack-4f",), p_kept=0.0), keep=True)
    a.policy.reply = b.policy.reply = 3
    seen, burst, sender, receiver = [], a.build(), a, b
    for _ in range(8):
        ext = F.Control.unpack([x.payload for x in burst.slots]).ext  # the whole control: up to two codewords
        seen.append((len(burst.slots), F.T_KEEP in ext, F.T_REPLY in ext))
        assert receiver.handle(FullRx(burst))
        burst, sender, receiver = receiver.build(), receiver, sender
        sender.answered()
    assert seen[0] == seen[1] == (2, True, False)  # each station's first: no room for both
    assert a._keeping and b._keeping and a.peer_reply_recommend == 3 == b.peer_reply_recommend
    assert (2, False, True) in seen  # said once in full
    assert seen[-2:] == [(1, False, False)] * 2

