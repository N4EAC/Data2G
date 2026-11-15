"""NumPy VHF/UHF FM channel simulator: audio in, audio out, with the radio
pair and the RF path between them modelled at complex baseband.

    audio (FS) -> TX radio: mic path (pre-emphasis, limiter, splatter
      filter, voice high-pass) or flat 9600 port (low-pass only); CTCSS;
      the drive in Hz of deviation
    -> FM modulator (RF_FS complex), key-up transient, RF offset
    -> RF path: multipath taps (fixed delays, Doppler-spread gains, Rician
      LOS), log-normal shadowing and slow path variability, aircraft
      flutter; AWGN at a CNR
    -> RX radio: IF filter, limiter-discriminator, de-emphasis and voice
      band (mic path) or low-pass and AC coupling (flat), squelch, the
      audio chain's own noise (the radio's SNR ceiling), recovery after
      the station's own transmission
    -> audio (FS), in the input's units

Clicks below the FM threshold are not added: they come out of the
discriminator as they do in a radio. CNR is carrier power over noise in
CNR_REF_BW_HZ, against the path's mean power: a burst in a fade or a
shadow is a low-CNR burst (as hfchannel's SNR).

`FmChannel` is one continuous channel for a whole session: its fading and
slow processes are fixed by the seed and read at any session time, so
bursts sent at different times see the channel move between them. The
noise is drawn per burst from its own seed, so a ladder run at several
CNRs with one seed sees the same fading (paired). `apply_channel` is the
one-burst form. `occupied_bandwidth` and `drive_for_bandwidth` measure the
RF signal, for the 15 kHz occupied limit.

Conditions (CONDITIONS) are presets of the path; radio paths (RADIOS) of the
radios. Parameters and their sources are next to each preset.

Simulation only, not on the live path and not ported to native.
"""

from dataclasses import dataclass, field, replace

import numpy as np
from scipy import signal

from .config import FS

C_MPS = 299_792_458.0
# The bands the FM profile is for: 144-450 MHz (2 m, 1.25 m, 70 cm). Higher
# bands count only where they cost these nothing. Studies run both ends.
CARRIERS_MHZ = (146.0, 440.0)
CNR_REF_BW_HZ = 15_000.0  # the noise bandwidth a CNR is referred to: a 15 kHz IF
# The limiter-discriminator's threshold sits near 10 dB CNR in that bandwidth.


def rf_rate(fs: int = FS) -> int:
    """Complex baseband rate: the smallest multiple of the audio rate at
    or above 48 kHz (room for a 15 kHz signal, a 25 kHz IF filter's skirts
    and the noise around them)."""
    return fs * -(-48_000 // fs)


# --- radios ------------------------------------------------------------------------


@dataclass(frozen=True)
class Radio:
    """One radio pair's audio path, the same at both ends.

    `path` "mic": TX pre-emphasis (6 dB/octave above 1 / (2 pi tau)), a hard
    limiter at `peak_dev_hz`, a splatter low-pass at `audio_hi_hz` and a
    voice high-pass at `audio_lo_hz`; RX de-emphasis and the same band.
    `path` "flat" (a 9600 data port, or a discriminator tap and a direct
    modulator input): low-pass at `audio_hi_hz` and AC coupling at
    `audio_lo_hz` each way, a limiter only if `peak_dev_hz` is set.

    Defaults are typical, not measured: the FM plan's M0 measures real
    radios and replaces them."""

    path: str = "mic"
    audio_lo_hz: float = 300.0
    audio_hi_hz: float = 3000.0
    emphasis_us: float = 750.0  # land-mobile 6 dB/octave pre-emphasis (TIA-603), mic path only
    peak_dev_hz: float | None = 5000.0  # the TX limiter's clip level; None: no limiter
    if_bw_hz: float = 15_000.0  # IF filter, two-sided (25 kHz channel radios ~15, 12.5 kHz ~11)
    if_order: int = 4  # Butterworth: a real filter's group-delay distortion at the edges
    ceiling_db: float = 40.0  # the audio chain's own noise under the drive's rms (radio SNR ceiling)
    ctcss_hz: float | None = None  # a sub-audible tone at ctcss_dev_hz, which the flat path passes
    ctcss_dev_hz: float = 600.0


RADIOS = {
    # Mic and speaker jacks (or a data jack wired to the same circuits).
    "mic": Radio(),
    "mic-narrow": Radio(peak_dev_hz=2500.0, if_bw_hz=11_000.0),  # a 12.5 kHz channel radio
    # A 9600 port: flat to about 6 kHz on good radios, no limiter, AC coupled.
    "flat": Radio(path="flat", audio_lo_hz=10.0, audio_hi_hz=6000.0, peak_dev_hz=None),
    # A 9600 port that rolls off early (Q7: measure what real ones do).
    "flat-4k": Radio(path="flat", audio_lo_hz=10.0, audio_hi_hz=4000.0, peak_dev_hz=None),
}


# --- paths --------------------------------------------------------------------------


@dataclass(frozen=True)
class Tap:
    """One multipath tap: `delay_us`, mean power `power_db` (relative; a
    condition's taps are normalised to unit total), Doppler `spectrum`
    ("classical" Jakes, "gauss1"/"gauss2" COST 207's bi-Gaussian shapes,
    "bell" fixed-wireless, "flat" none: a static tap) at the condition's
    Doppler. `k_db`: Rician K of a fixed LOS part (None: Rayleigh), at
    `los_doppler` times the maximum Doppler."""

    delay_us: float
    power_db: float = 0.0
    spectrum: str = "classical"
    k_db: float | None = None
    los_doppler: float = 0.0


@dataclass(frozen=True)
class Condition:
    """A path: multipath taps whose Doppler comes from `speed_kmh` at the
    carrier (mobile) or `doppler_hz` (fixed stations: moving scatterers),
    log-normal shadowing (`shadow_db` sigma, decorrelating over
    `shadow_m` metres of travel, or `shadow_s` seconds when fixed), slow
    path variability on top (`slow_db`, `slow_s`: tropospheric and
    diffraction-path changes), and optional aircraft flutter (a path
    `flutter_db` under the direct one whose Doppler sweeps through
    +-`flutter_hz` over `flutter_s`)."""

    name: str
    taps: tuple = (Tap(0.0, spectrum="flat"),)
    speed_kmh: float = 0.0
    doppler_hz: float = 0.0
    shadow_db: float = 0.0
    shadow_m: float = 50.0
    shadow_s: float = 0.0
    slow_db: float = 0.0
    slow_s: float = 60.0
    flutter_db: float | None = None
    flutter_hz: float = 0.0
    flutter_s: float = 20.0
    note: str = ""

    def max_doppler(self, carrier_mhz: float) -> float:
        return self.doppler_hz + self.speed_kmh / 3.6 * carrier_mhz * 1e6 / C_MPS


# COST 207 (Failli 1989, as reproduced in Molisch, Wireless Communications 2e,
# app. 7.C): delays from the original, not 3GPP TS 45.005's TU (0.5, 2.3 us,
# all classical). Doppler class by delay: classical to 0.5 us, gauss1 to
# 2 us, gauss2 past. RICE's K is ambiguous in the sources: its formula's
# diffuse part integrates to 0.205 against a unit line, K = 4.4 (6.5 dB), the
# line at +0.7 fd; that is used here (Molisch's prose implies K = 1).
_TU6 = (Tap(0.0, -3), Tap(0.2, 0), Tap(0.6, -2, "gauss1"), Tap(1.6, -6, "gauss1"),
        Tap(2.4, -8, "gauss2"), Tap(5.0, -10, "gauss2"))
_BU6 = (Tap(0.0, -3), Tap(0.4, 0), Tap(1.0, -3, "gauss1"), Tap(1.6, -5, "gauss1"),
        Tap(5.0, -2, "gauss2"), Tap(6.6, -4, "gauss2"))
_HT6 = (Tap(0.0, 0), Tap(0.2, -2), Tap(0.4, -4), Tap(0.6, -7), Tap(15.0, -6, "gauss2"), Tap(17.2, -12, "gauss2"))
_RA4 = (Tap(0.0, 0, k_db=6.5, los_doppler=0.7), Tap(0.2, -2), Tap(0.4, -10), Tap(0.6, -20))

# Notes behind the numbers (sources: the FM plan discussion's M1 research):
# - Doppler: fd = v f / c (146 MHz: 4.1 Hz at 30 km/h, 13.5 at 100; 440 MHz:
#   12.2, 40.8). Measured VHF/UHF rms delay spread is 0.1-2 us urban, up to
#   8-30 us in mountains, so COST 207's 900 MHz profiles carry over; at 15 kHz
#   everything but HT-class echoes is flat fading.
# - Shadowing: Gudmundson's exponential correlation, exp(-d / dc): 900 MHz
#   suburban sigma 7.5 dB, dc ~500 m; ITU-R M.1225 vehicular 10 dB, 20 m.
#   ITU-R P.1546 location variability 5.5 dB (planning) to 8-12 dB (whole
#   areas). The values per preset are a choice within those.
# - Fixed stations: IEEE 802.16 SUI models (Erceg et al., 802.16.3c-01/29r4):
#   K 1-20 on the first tap, "rounded" Doppler of 0.15-2.5 Hz at 2.5 GHz;
#   moving scatterers' Doppler scales with frequency, so 0.1-0.5 Hz at VHF/UHF.
# - Slow fadeouts on borderline paths (NBS Tech. Note 88, Barsis and
#   Johnson 1961): within-horizon and diffraction paths see fadeouts 5-20 dB
#   under the hourly median lasting minutes (138 MHz, southern California:
#   median 4-7 min for 5-15 dB fades; longer at lower frequencies; a 751 MHz
#   knife-edge path 0.3-0.8 min), not Rayleigh, not decorrelated by 20
#   wavelengths of antenna spacing; much rarer in dry inland climates.
#   Modelled as a Gauss-Markov process in dB: sigma 5 dB gives 10% of the time
#   6.4 dB down and 1% 11.6 dB down.
# - Aircraft scatter: amateur reports only, about +-200 Hz at 144 MHz
#   (2 v f / c: 243 Hz at 250 m/s), 20-30 dB enhancements for minutes.
CONDITIONS: dict[str, Condition] = {c.name: c for c in (
    Condition("static", note="a fixed line-of-sight path, nothing moving"),
    # Fixed stations
    Condition("fixed", (Tap(0.0, 0, "rounded", k_db=13.0), Tap(0.4, -15, "rounded"), Tap(0.9, -20, "rounded")),
              doppler_hz=0.2, note="SUI-1-like: good fixed path, foliage and traffic barely move it"),
    Condition("fixed-fringe", (Tap(0.0, 0, "rounded", k_db=0.0), Tap(0.4, -5, "rounded"), Tap(0.9, -10, "rounded")),
              doppler_hz=0.3, slow_db=5.0, slow_s=120.0,
              note="SUI-3-like scatter at K 1, plus TN 88's slow fadeouts (minutes): the borderline fixed link"),
    Condition("knife-edge", (Tap(0.0, 0, "rounded", k_db=3.0), Tap(15.0, -10, "rounded")), doppler_hz=0.3,
              slow_db=6.0, slow_s=30.0,
              note="diffraction over a ridge: a flat two-ray-like main path, an echo off another face, "
                   "TN 88's 751 MHz fadeouts (0.3-0.8 min)"),
    Condition("flutter", (Tap(0.0, 0, "flat"),), flutter_db=-12.0, flutter_hz=150.0, flutter_s=30.0,
              note="static path plus an aircraft reflection 12 dB down sweeping +-150 Hz (at 146 MHz)"),
    # Mobiles (speeds are defaults: with_speed() for others)
    Condition("pedestrian", _TU6, speed_kmh=5.0, shadow_db=6.0, shadow_m=20.0,
              note="a handheld walking in town: slow, deep fades (fd 0.7 Hz at 146 MHz)"),
    Condition("mobile-rural", _RA4, speed_kmh=90.0, shadow_db=5.0, shadow_m=200.0,
              note="COST 207 RA: open country, a strong direct path"),
    Condition("mobile-urban", _TU6, speed_kmh=40.0, shadow_db=8.0, shadow_m=50.0,
              note="COST 207 TU: town traffic, picket fencing"),
    Condition("mobile-bad-urban", _BU6, speed_kmh=30.0, shadow_db=8.0, shadow_m=30.0,
              note="COST 207 BU: dense city, late echoes off large buildings"),
    Condition("mobile-hilly", _HT6, speed_kmh=80.0, shadow_db=6.0, shadow_m=200.0,
              note="COST 207 HT: 15-17 us echoes, enough to distort FM in a 15 kHz channel"),
)}


# --- random processes ---------------------------------------------------------------------


def _doppler_psd(f: np.ndarray, fd: float, kind: str) -> np.ndarray:
    """Doppler power spectrum shape at frequencies f for maximum Doppler fd."""
    if kind == "flat" or fd <= 0:
        return (np.abs(f) == np.abs(f).min()).astype(float)  # one bin: a constant gain
    u = f / fd
    if kind == "classical":  # Jakes, integrated over each bin so the band-edge poles stay finite
        df = f[1] - f[0] if len(f) > 1 else fd
        lo, hi = np.clip((f - df / 2) / fd, -1, 1), np.clip((f + df / 2) / fd, -1, 1)
        return np.arcsin(hi) - np.arcsin(lo)
    if kind == "gauss1":  # COST 207 GAUS1: G(A=1, f1=-0.8fd, s1=0.05fd) + G(A=0.1, 0.4fd, 0.1fd)
        return np.exp(-((u + 0.8) ** 2) / (2 * 0.05**2)) + 0.1 * np.exp(-((u - 0.4) ** 2) / (2 * 0.1**2))
    if kind == "gauss2":  # COST 207 GAUS2: G(1, 0.7fd, 0.1fd) + G(10^-1.5, -0.4fd, 0.15fd)
        return np.exp(-((u - 0.7) ** 2) / (2 * 0.1**2)) + 10**-1.5 * np.exp(-((u + 0.4) ** 2) / (2 * 0.15**2))
    if kind == "bell":  # fixed wireless (TGn): 1 / (1 + 9 (f / fd)^2), fd the environment's spread
        return 1.0 / (1.0 + 9.0 * u**2)
    if kind == "rounded":  # SUI: 1 - 1.72 u^2 + 0.785 u^4 within +-fd
        return np.where(np.abs(u) <= 1, 1 - 1.72 * u**2 + 0.785 * u**4, 0.0)
    raise ValueError(f"Doppler spectrum {kind!r}")


def doppler_gain(n: int, rate: float, fd: float, kind: str, rng: np.random.Generator) -> np.ndarray:
    """n samples at `rate` of a unit-mean-power complex Gaussian gain with
    the given Doppler spectrum (white noise shaped in one FFT: periodic
    over n, so make n cover the whole session)."""
    f = np.fft.fftfreq(n, 1 / rate)
    s = _doppler_psd(f, fd, kind)
    w = (rng.normal(size=n) + 1j * rng.normal(size=n)) * np.sqrt(s)
    g = np.fft.ifft(w)
    return g / np.sqrt(np.mean(np.abs(g) ** 2))


def gauss_markov_db(n: int, rate: float, sigma_db: float, tau_s: float, rng: np.random.Generator) -> np.ndarray:
    """n samples of a stationary Gaussian process in dB, sigma `sigma_db`,
    exponential autocorrelation exp(-|dt| / tau_s) (Gudmundson's model)."""
    if sigma_db <= 0:
        return np.zeros(n)
    a = np.exp(-1.0 / (rate * tau_s))
    e = rng.normal(scale=sigma_db * np.sqrt(1 - a * a), size=n)
    e[0] = rng.normal(scale=sigma_db)
    return signal.lfilter([1.0], [1.0, -a], e)


# --- the channel ----------------------------------------------------------------------------


@dataclass
class FmChannel:
    """One continuous FM channel for a session of `duration_s` (bursts may
    run past its end: the processes wrap)."""

    condition: str | Condition = "static"
    radio: str | Radio = "mic"
    cnr_db: float | None = 30.0
    seed: int = 0
    duration_s: float = 120.0
    carrier_mhz: float = 146.0  # CARRIERS_MHZ: Doppler and flutter scale with it
    drive_dev_hz: float = 1500.0  # rms deviation of the input audio (before pre-emphasis, 1 kHz-normalised)
    rf_offset_hz: float = 0.0  # TX carrier against the RX's tuning
    ppm: float = 0.0  # audio sample clock, TX sound card against RX
    keyup_s: float = 0.0  # carrier absent this long at each burst's start (radio key-up)
    keyup_dev_hz: float = 0.0  # the TX synthesiser's offset at key-up, settling with keyup_tau_s
    keyup_tau_s: float = 0.02
    squelch_db: float | None = None  # CNR (10 ms) the noise squelch opens at; None: open squelch
    squelch_open_s: float = 0.05
    squelch_hang_s: float = 0.1
    rx_dc: float = 0.0  # RX audio's DC step after the station's own transmission, x the drive's rms
    rx_tau_s: float = 0.15
    fs: int = FS
    _gains: list = field(init=False, repr=False)

    def __post_init__(self):
        self.cond = CONDITIONS[self.condition] if isinstance(self.condition, str) else self.condition
        self.rad = RADIOS[self.radio] if isinstance(self.radio, str) else self.radio
        self.rf_fs = rf_rate(self.fs)
        rng = np.random.default_rng(self.seed)
        c = self.cond
        fd = c.max_doppler(self.carrier_mhz)
        # gains on a grid fast enough for the Doppler, read by interpolation
        fl = c.flutter_hz * self.carrier_mhz / 146.0 if c.flutter_db is not None else 0.0
        self.grid_rate = max(200.0, 16.0 * max(fd, fl))
        n = int(np.ceil(self.duration_s * self.grid_rate)) + 2
        p = np.array([10 ** (t.power_db / 10) for t in c.taps])
        p = p / p.sum()
        self._gains = []
        for t, pk in zip(c.taps, p):
            if t.k_db is None:
                g = doppler_gain(n, self.grid_rate, fd, t.spectrum, rng)
            else:
                k = 10 ** (t.k_db / 10)
                ph = rng.uniform(0, 2 * np.pi)
                los = np.exp(1j * (ph + 2 * np.pi * t.los_doppler * fd * np.arange(n) / self.grid_rate))
                g = np.sqrt(k / (k + 1)) * los + np.sqrt(1 / (k + 1)) * doppler_gain(n, self.grid_rate, fd, t.spectrum, rng)
            self._gains.append(np.sqrt(pk) * g)
        # slow processes (dB), one grid
        if c.shadow_db > 0:
            tau = c.shadow_s if c.speed_kmh <= 0 else c.shadow_m / (c.speed_kmh / 3.6)
            shadow = gauss_markov_db(n, self.grid_rate, c.shadow_db, max(tau, 1e-3), rng)
        else:
            shadow = np.zeros(n)
        slow = gauss_markov_db(n, self.grid_rate, c.slow_db, c.slow_s, rng)
        self._slow_amp = 10 ** ((shadow + slow) / 20)
        self._flutter = None
        if c.flutter_db is not None:
            t = np.arange(n) / self.grid_rate
            # a crossing aircraft: Doppler sweeping +fl..-fl and back (triangle), phase its integral
            tri = 2 * np.abs(((t / c.flutter_s + rng.uniform()) % 1) - 0.5) * 2 - 1
            phase = 2 * np.pi * np.cumsum(fl * tri) / self.grid_rate
            self._flutter = 10 ** (c.flutter_db / 20) * np.exp(1j * (phase + rng.uniform(0, 2 * np.pi)))
        self.burst_seed = int(rng.integers(1 << 31))

    # -- reading the processes ----------------------------------------------------

    def _at(self, x: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Process x (on the grid) at times t (s), linear interpolation, wrapping."""
        u = (t * self.grid_rate) % (len(x) - 1)
        i = u.astype(int)
        f = u - i
        return x[i] * (1 - f) + x[i + 1] * f

    def path_gain_db(self, t: np.ndarray) -> np.ndarray:
        """Received carrier power over the mean at times t (narrowband: the taps' sum)."""
        g = sum(self._at(gk, t) for gk in self._gains)
        if self._flutter is not None:
            g = g + self._at(self._flutter, t)
        return 20 * np.log10(np.abs(g * self._at(self._slow_amp, t)) + 1e-12)

    # -- one burst ----------------------------------------------------------------------

    def apply(self, x: np.ndarray, t0: float = 0.0, burst: int = 0) -> np.ndarray:
        """Audio `x` (fs) keyed up at session time t0 -> the receiver's audio.
        `burst` picks the burst's noise (seeded from the channel's seed and
        this): one number per burst in a session."""
        r = self.rad
        rng = np.random.default_rng([self.burst_seed, burst])
        up = self.rf_fs // self.fs
        m = np.asarray(x, dtype=np.float64)
        ref_rms = np.sqrt(np.mean(m[np.abs(m) > 0] ** 2)) if np.any(m) else 1.0
        if self.ppm:
            from .hfchannel import sample_clock_offset

            m = sample_clock_offset(m, self.ppm)
        dev = tx_audio(m / ref_rms * self.drive_dev_hz, r, self.fs)  # Hz of deviation
        if r.ctcss_hz:
            dev = dev + r.ctcss_dev_hz * np.sin(2 * np.pi * r.ctcss_hz * np.arange(len(dev)) / self.fs)
        f_inst = signal.resample_poly(dev, up, 1)
        n = len(f_inst)
        t = t0 + np.arange(n) / self.rf_fs
        on = np.arange(n) >= int(self.keyup_s * self.rf_fs)
        if self.keyup_dev_hz:
            f_inst = f_inst + self.keyup_dev_hz * np.exp(-np.maximum(t - t0 - self.keyup_s, 0) / self.keyup_tau_s)
        f_inst = f_inst + self.rf_offset_hz
        s = np.exp(2j * np.pi * np.cumsum(f_inst) / self.rf_fs) * on
        # the path
        y = np.zeros(n, dtype=complex)
        for tap, g in zip(self.cond.taps, self._gains):
            y += _delay(s, tap.delay_us * 1e-6 * self.rf_fs) * self._at(g, t)
        if self._flutter is not None:
            y += s * self._at(self._flutter, t)
        y *= self._at(self._slow_amp, t)
        if self.cnr_db is not None:
            # unit mean carrier power; noise density so that CNR_REF_BW_HZ holds 10^(-cnr/10)
            sigma2 = 10 ** (-self.cnr_db / 10) * self.rf_fs / CNR_REF_BW_HZ
            y += np.sqrt(sigma2 / 2) * (rng.normal(size=n) + 1j * rng.normal(size=n))
        out = rx_audio(y, r, self.fs, self.rf_fs, self.drive_dev_hz)
        if self.squelch_db is not None and self.cnr_db is not None:
            out *= _squelch(y, self.fs, self.rf_fs, self.cnr_db, self.squelch_db, self.squelch_open_s, self.squelch_hang_s)
        if r.ceiling_db is not None:
            out += rng.normal(scale=10 ** (-r.ceiling_db / 20), size=len(out))
        if self.rx_dc:
            out += self.rx_dc * np.exp(-np.arange(len(out)) / (self.rx_tau_s * self.fs))
        return out * ref_rms


def apply_channel(x: np.ndarray, cnr_db: float | None = 30.0, condition: str | Condition = "static",
                  radio: str | Radio = "mic", seed: int = 0, **kw) -> np.ndarray:
    """One burst through its own channel: the condition's processes start at
    a random point of their stationary distribution (seeded), so a slow
    shadow gives each burst its own draw."""
    ch = FmChannel(condition, radio, cnr_db, seed, duration_s=len(x) / FS + 2.0, **kw)
    return ch.apply(x)


# --- radio audio --------------------------------------------------------------------------------


def _emphasis(fs: int, tau_us: float, inverse: bool):
    """First-order 6 dB/octave pre-emphasis (zero at 1/(2 pi tau), a pole
    far above the audio band) or its inverse, unity gain at 1 kHz."""
    tau = tau_us * 1e-6
    tau2 = 1 / (2 * np.pi * 0.45 * fs)  # the realisable pole, near Nyquist
    b, a = signal.bilinear([tau, 1.0], [tau2, 1.0], fs)
    if inverse:
        b, a = a, b
    _, h = signal.freqz(b, a, worN=[1000.0], fs=fs)
    return b / np.abs(h[0]), a


def tx_audio(dev: np.ndarray, r: Radio, fs: int) -> np.ndarray:
    """The TX radio's audio path: input in Hz of deviation -> what reaches
    the modulator."""
    y = dev
    if r.path == "mic":
        b, a = _emphasis(fs, r.emphasis_us, inverse=False)
        y = signal.lfilter(b, a, y)
    if r.peak_dev_hz is not None:
        y = np.clip(y, -r.peak_dev_hz, r.peak_dev_hz)
    return _band(y, r, fs)


def _band(y: np.ndarray, r: Radio, fs: int) -> np.ndarray:
    hi = min(r.audio_hi_hz, 0.45 * fs)
    sos = signal.butter(6 if r.path == "mic" else 4, hi, "lowpass", fs=fs, output="sos")
    y = signal.sosfilt(sos, y)
    sos = signal.butter(2 if r.path == "mic" else 1, r.audio_lo_hz, "highpass", fs=fs, output="sos")
    return signal.sosfilt(sos, y)


def rx_audio(z: np.ndarray, r: Radio, fs: int, rf_fs: int, drive_dev_hz: float) -> np.ndarray:
    """The RX radio: IF filter, limiter-discriminator, audio path; out in
    units of the drive's rms deviation."""
    sos = signal.butter(r.if_order, r.if_bw_hz / 2, "lowpass", fs=rf_fs, output="sos")
    z = signal.sosfilt(sos, z)
    f = np.angle(z[1:] * np.conj(z[:-1])) * rf_fs / (2 * np.pi)
    f = np.concatenate([[0.0], f])
    y = signal.resample_poly(f, 1, rf_fs // fs)
    if r.path == "mic":
        b, a = _emphasis(fs, r.emphasis_us, inverse=True)
        y = signal.lfilter(b, a, y)
    return _band(y, r, fs) / drive_dev_hz


def _delay(s: np.ndarray, d: float) -> np.ndarray:
    """s delayed by d samples (fractional; in the frequency domain, padded)."""
    if d == 0:
        return s
    pad = int(np.ceil(d)) + 8
    n = len(s) + pad
    f = np.fft.fftfreq(n)
    y = np.fft.ifft(np.fft.fft(s, n) * np.exp(-2j * np.pi * f * d))
    return y[: len(s)]


def _squelch(z: np.ndarray, fs: int, rf_fs: int, cnr_db: float, open_db: float, open_s: float, hang_s: float):
    """A noise squelch, as the receiver hears it: open when the 10 ms
    carrier-to-noise has stayed above `open_db` for `open_s`, closed `hang_s`
    after it drops 2 dB below (hysteresis). Per audio sample, 0 or 1."""
    blk = rf_fs // 100
    nb = len(z) // blk + 1
    p = np.array([np.mean(np.abs(z[i * blk:(i + 1) * blk]) ** 2) if i * blk < len(z) else 0.0 for i in range(nb)])
    noise = 10 ** (-cnr_db / 10) * rf_fs / CNR_REF_BW_HZ  # what the noise alone adds per sample
    cnr = 10 * np.log10(np.maximum(p - noise, 1e-12) / (noise * CNR_REF_BW_HZ / rf_fs))
    gate = np.zeros(nb)
    state, above, below = 0, 0, 0
    for i, c in enumerate(cnr):
        above = above + 1 if c >= open_db else 0
        below = below + 1 if c < open_db - 2 else 0
        if not state and above * 0.01 >= open_s:
            state = 1
        elif state and below * 0.01 >= hang_s:
            state = 0
        gate[i] = state
    return np.repeat(gate, fs // 100)[: int(np.ceil(len(z) * fs / rf_fs))]


# --- the RF signal's bandwidth ------------------------------------------------------------------


def rf_signal(x: np.ndarray, radio: str | Radio = "mic", drive_dev_hz: float = 1500.0, fs: int = FS) -> tuple[np.ndarray, int]:
    """What the TX radio puts on air for audio x: complex baseband at rf_rate."""
    r = RADIOS[radio] if isinstance(radio, str) else radio
    m = np.asarray(x, dtype=np.float64)
    rms = np.sqrt(np.mean(m[np.abs(m) > 0] ** 2))
    dev = tx_audio(m / rms * drive_dev_hz, r, fs)
    if r.ctcss_hz:
        dev = dev + r.ctcss_dev_hz * np.sin(2 * np.pi * r.ctcss_hz * np.arange(len(dev)) / fs)
    rf = rf_rate(fs)
    f = signal.resample_poly(dev, rf // fs, 1)
    return np.exp(2j * np.pi * np.cumsum(f) / rf), rf


def occupied_bandwidth(s: np.ndarray, rf_fs: int, rbw_hz: float = 100.0) -> dict:
    """The RF signal's bandwidth, measured: `obw99` (the band holding 99% of
    the power, 0.5% outside each edge: ITU's occupied bandwidth) and
    `db26` (the outermost points 26 dB under the spectrum's peak, at
    `rbw_hz` resolution: US Part 97's measure), Hz."""
    nper = int(2 ** np.ceil(np.log2(rf_fs / rbw_hz)))
    f, p = signal.welch(s, rf_fs, nperseg=min(nper, len(s)), return_onesided=False, detrend=False)
    o = np.argsort(f)
    f, p = f[o], p[o]
    c = np.cumsum(p) / p.sum()
    lo, hi = f[np.searchsorted(c, 0.005)], f[np.searchsorted(c, 0.995)]
    over = np.nonzero(p >= p.max() * 10 ** (-26 / 10))[0]
    return {"obw99": float(hi - lo), "db26": float(f[over[-1]] - f[over[0]])}


def drive_for_bandwidth(x: np.ndarray, radio: str | Radio = "mic", target_hz: float = 15_000.0,
                        measure: str = "worst", fs: int = FS) -> tuple[float, dict]:
    """The largest rms drive (Hz of deviation, as FmChannel.drive_dev_hz)
    whose RF signal stays within `target_hz`: by `measure` "obw99", "db26",
    or "worst" (both). Bisection; returns the drive and its measurement."""

    def width(d):
        s, rf = rf_signal(x, radio, d, fs)
        w = occupied_bandwidth(s, rf)
        return (max(w.values()) if measure == "worst" else w[measure]), w

    lo, hi = 50.0, 8000.0
    if width(hi)[0] <= target_hz:
        return hi, width(hi)[1]
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if width(mid)[0] <= target_hz else (lo, mid)
        if hi - lo < 5.0:
            break
    return lo, width(lo)[1]


def with_speed(name: str, speed_kmh: float) -> Condition:
    """A mobile condition at another speed."""
    return replace(CONDITIONS[name], speed_kmh=speed_kmh, name=f"{name}@{speed_kmh:g}")
