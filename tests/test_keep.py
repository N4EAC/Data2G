"""T_KEEP (docs/arq.md §8a): T_REPLY only when it changes, once both stations
keep it. At link level: T_KEEP until acted on, the listener's reply
recommendation always the one the sender means through lost bursts and nods,
and a peer that never said T_KEEP gets T_REPLY in every control as before."""

import random

import pytest

from data2g.arq import frames as F
from data2g.arq import link as L

from test_arq import CTL_BYTES, payload
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
            said = sender._said(sender._latest)
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
    assert bool(a._keep_told) == a_keep and bool(b._keep_told) == b_keep


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
    x = a.build()
    # a's T_KEEP is acted on, but a does not know yet that b reads its controls so: in full
    assert F.T_KEEP not in _ctl(x).ext and _ctl(x).ext[F.T_REPLY] == b""
    burst, sender, receiver = x, a, b
    for _ in range(4):
        assert receiver.handle(FullRx(burst))
        burst, sender, receiver = receiver.build(), receiver, sender
        sender.answered()
    assert sender is a and F.T_REPLY not in _ctl(burst).ext and F.T_KEEP not in _ctl(burst).ext  # as b holds it
    assert b.handle(FullRx(burst)) and b.peer_reply_recommend == 3 and a.peer_reply_recommend == 7
    r = b.build()
    b.answered()
    assert F.T_REPLY not in _ctl(r).ext and a.handle(FullRx(r)) and a.peer_reply_recommend == 7
    # a change is said, and so is "none" (an empty T_REPLY: left out, b would keep the last)
    a.policy.recommend = lambda st: (0, 1, None)
    x = a.build()
    assert _ctl(x).ext[F.T_REPLY] == b""
    assert b.handle(FullRx(x)) and b.peer_reply_recommend is None
    r = b.build()
    b.answered()
    assert a.handle(FullRx(r))
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
    for _ in range(12):
        ext = F.Control.unpack([x.payload for x in burst.slots]).ext  # the whole control: up to two codewords
        seen.append((len(burst.slots), F.T_KEEP in ext, F.T_REPLY in ext))
        assert receiver.handle(FullRx(burst))
        burst, sender, receiver = receiver.build(), receiver, sender
        sender.answered()
    assert seen[0] == seen[1] == (2, True, False)  # each station's first: no room for both
    assert a._keeping and b._keeping and a.peer_reply_recommend == 3 == b.peer_reply_recommend
    assert (2, False, True) in seen  # said in full until each knows the other keeps it
    assert seen[-2:] == [(1, False, False)] * 2, seen


# --- the handshake's window, sheds, the primed order (review of #231) ----------------------------

CPM, ACK = "fsk16r25-r1/2", "ack-4f"


class Mixed(AskingPolicy):
    """A CPM mode (a 20 B control, one codeword) and an OFDM ACK mode (4 B a
    codeword, full with T_REPLY): `mode` is the test's to set, or drawn."""

    want_dup = False
    draw = False

    def choose(self, station, escalation):
        if self.draw and self.rng.random() < 0.5:
            self.mode = self.rng.choice((CPM, ACK))
        return self.mode, 3

    def payload_bytes(self, m):
        return 40 if m == CPM else 4

    def ctl_payload_bytes(self, m):
        return CTL_BYTES if m == CPM else 4

    def max_ctl(self, m):
        return 1 if m == CPM else 4

    def rv_cycle(self, m):
        return 4


def _whole(burst):
    """A burst's control, all its codewords (control-only bursts and a CPM data burst's one)."""
    n = F.Core.unpack(burst.slots[0].payload).n_ctl
    return F.Control.unpack([x.payload for x in burst.slots[:n]])


def _pair(mode_a=ACK, mode_b=ACK):
    a = L.Station(0, Mixed(random.Random(1), 0.0, (mode_a,), p_kept=0.0), master=True, keep=True)
    b = L.Station(1, Mixed(random.Random(2), 0.0, (mode_b,), p_kept=0.0), keep=True)
    return a, b


def test_reply_is_not_kept_before_its_sender_keeps_it():
    """The receiver keeps T_REPLY only once the sender does. A's first burst has
    no T_KEEP, B's reply to its second is lost, and A's poll (not keeping yet:
    nothing of B's has acted on its T_KEEP) leaves T_REPLY out for none. B, which
    has heard A's T_KEEP and been acted on, must not put the old value back."""
    a, b = _pair()
    a.policy.reply, b.policy.reply = None, 3
    a0 = a.build()
    assert F.T_KEEP not in _whole(a0).ext  # a full control, no T_REPLY to take the place of
    assert b.handle(FullRx(a0))
    b0 = b.build()
    b.answered()
    assert F.T_KEEP in _whole(b0).ext
    assert a.handle(FullRx(b0)) and a.keep_peer and not a._keep_told
    a.policy.mode, a.policy.reply = CPM, 7
    a1 = a.build()
    assert _whole(a1).ext[F.T_REPLY] == b"" and F.T_KEEP in _whole(a1).ext
    assert b.handle(FullRx(a1)) and b.peer_reply_recommend == 7
    b.build()  # lost
    b.answered()
    a.policy.reply = None
    a2 = a.on_timeout(allow_repeat=False)  # a poll
    assert F.T_REPLY not in _whole(a2).ext and not a._keeping
    assert b.handle(FullRx(a2)) and b.peer_reply_recommend is None


def run_mixed(seed, turns=400):
    """Lockstep with 20% of bursts lost, modes drawn (T_KEEP fits some controls and
    not others), nods on, recommendations moving: after every burst heard, the
    listener holds what its sender means (None while the sender does not keep it and
    left T_REPLY out), and a nod leaves it so."""
    rng = random.Random(seed)
    a = L.Station(0, Mixed(random.Random(seed + 1), 0.0, (CPM, ACK), p_kept=0.3), master=True, max_misses=None,
                  keep=True, nod=True)
    b = L.Station(1, Mixed(random.Random(seed + 2), 0.0, (CPM, ACK), p_kept=0.3), max_misses=None, keep=True, nod=True)
    a.policy.draw = b.policy.draw = True
    a.write(payload(rng, 3000, "mixed"))
    b.write(payload(rng, 600, "mixed"))
    n = bare = 0
    burst, sender = a.build(nod=True), a
    for _ in range(turns):
        receiver = b if sender is a else a
        ok = False
        if rng.random() >= 0.2:
            said = sender._said(sender._latest)
            if burst.nod is not None:
                ok = receiver.handle(receiver.nod_rx(burst.nod[0]))
            else:
                ext = _whole(burst).ext
                ok = receiver.handle(FullRx(burst))
                n += 1
                bare += F.T_REPLY not in ext
                if ok and F.T_REPLY not in ext and not sender._keeping:
                    assert receiver.peer_reply_recommend is None
            if ok and said != L._UNKNOWN:
                assert receiver.peer_reply_recommend == said, (said, receiver.peer_reply_recommend, burst.nod)
        a.read()
        b.read()
        assert a.state != L.FAILED and b.state != L.FAILED, (a.fail_reason, b.fail_reason)
        if ok:
            burst, sender = receiver.build(nod=True), receiver
            receiver.answered()
        else:
            burst, sender = a.on_timeout(), a
            assert burst is not None, a.fail_reason
    return a, b, n, bare


@pytest.mark.parametrize("first", range(0, 600, 25))
def test_reply_agrees_through_the_handshake_losses_and_nods(first, monkeypatch):
    """600 loss patterns: run_mixed's checks hold, and every link gets to leave T_REPLY out."""
    monkeypatch.setattr(L, "NOD", True)
    for seed in range(first, first + 25):
        a, b, n, bare = run_mixed(seed)
        assert a._keeping and b._keeping and bare > n // 4, (seed, bare, n)


def _kept_pair():
    """Two CPM stations that keep T_REPLY, a's turn next: -> (a, b)."""
    a, b = _pair(CPM, CPM)
    a.policy.reply, b.policy.reply = 3, 7
    burst, sender, receiver = a.build(), a, b
    for _ in range(8):
        assert receiver.handle(FullRx(burst))
        burst, sender, receiver = receiver.build(), receiver, sender
        sender.answered()
    assert sender is a and a._keeping and b._keeping and b.peer_reply_recommend == 3
    return a, b


@pytest.mark.parametrize("size,left", [(7, b""), (8, b""), (9, None)])
def test_a_shed_t_reply_says_none_where_that_fits(size, left):
    """Once both keep it, a changed T_REPLY that an inline codeword leaves no room
    for is cut to none (an empty T_REPLY, a byte less) before it is dropped, so the
    peer falls back to its own reply mode rather than keep its last. Dropped
    altogether (not a byte to spare), the peer keeps its last and the next control
    says it in full."""
    a, b = _kept_pair()
    a.policy.reply = 5
    a.write(bytes(range(1, size + 1)))
    x = a.build()
    ext = _whole(x).ext
    assert F.T_INLINE in ext and ext.get(F.T_REPLY) == left
    assert b.handle(FullRx(x)) and b.peer_reply_recommend == {b"": 5, b"": None, None: 3}[left]
    assert a._said(a._latest) == {b"": 5, b"": None, None: L._UNKNOWN}[left]
    y = b.build()
    b.answered()
    assert a.handle(FullRx(y))
    assert _whole(a.build()).ext.get(F.T_REPLY) == (None if left == b"" else b"")


def test_primed_hypotheses_leave_t_reply_out_first_once_kept():
    """A CPM control from a peer that keeps T_REPLY mostly has none: the first
    hypothesis leaves it out, the next has it with its value unknown."""
    receiver, _ = _kept_pair()

    class Rx:
        submode, n_cw, n_ctl_slots = CPM, 1, 1

    hs = receiver.expect(Rx())
    exts = [F.Control.unpack([t]).ext for t, *_ in hs]
    # (a callee tries the caller's repeated burst second: the T_REPLY one is then third)
    assert F.T_REPLY not in exts[0] and any(F.T_REPLY in e for e in exts[1:3]), exts
    assert len(hs) <= L.PRIME_TRIES



def test_primed_hypotheses_drop_t_keep_once_the_peer_has_stopped():
    """The peer's last data burst came in the handshake and carried T_KEEP. Its
    next comes after it stopped saying it: no hypothesis has one."""
    a, b = _pair(CPM, CPM)
    a.policy.reply, b.policy.reply = 3, 7
    a.write(bytes(range(1, 31)))
    burst, sender, receiver = a.build(), a, b
    assert F.T_KEEP in _whole(burst).ext and len(burst.slots) == 2
    for _ in range(8):
        assert receiver.handle(FullRx(burst))
        burst, sender, receiver = receiver.build(), receiver, sender
        sender.answered()
        assert len(burst.slots) == 1
    assert sender is a and a._keeping and b._keeping

    class Rx:
        submode, n_cw, n_ctl_slots = CPM, 2, 1

    hs = b.expect(Rx())
    assert hs and not any(F.T_KEEP in F.Control.unpack([t]).ext for t, *_ in hs)


@pytest.mark.parametrize("mode,left", [(ACK, "swapped"), (CPM, "shed")])
def test_expected_modes_leave_out_a_reply_mode_never_said(mode, left):
    """The expected reply slot listens for the reply mode I recommended only where
    the control said it: not where T_KEEP took T_REPLY's place, nor where it was shed."""
    if left == "swapped":
        a, b = _pair()
        a.policy.reply = 3
        x = a.build()
        assert F.T_KEEP in _whole(x).ext and F.T_REPLY not in _whole(x).ext
        assert "3" not in a.expected_modes()
        return
    a, b = _kept_pair()
    assert "3" in a.expected_modes()  # kept: as said last
    a.policy.reply = 5
    a.write(bytes(range(1, 10)))
    x = a.build()
    assert F.T_INLINE in _whole(x).ext and F.T_REPLY not in _whole(x).ext
    assert not {"3", "5"} & set(a.expected_modes())
