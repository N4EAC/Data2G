# Data2G FM: plan

Status: draft for discussion, 2026-11-13. Nothing here is built.

## TLDR

- Build one FM channel simulator first. Every later step is judged on it, and nothing in the repo models a limiter-discriminator today.
- "Narrow" is a retune of the existing 8 kHz OFDM (w48 already sits at 350..2700 Hz). "Wide" is the same modem clocked at 16 kHz, then widened. Neither needs a new waveform family.
- Status: M1 (the simulator) is draft PR #203, M2 (profiles, Q1 decided: fixed at process start) is draft PR #204, the carrier spacing study (Q19: 50 Hz, measured) draft PR #205, M3 (FM receiver) draft PR #206. First numbers are under M1, M2, M3 and Q19.
- Bands: 144-450 MHz (2 m, 1.25 m, 70 cm) are the targets. Higher bands count only where they cost these nothing.
- Rate targets are VARA FM 4.0's: 12750 bps narrow, 25210 bps wide. Both are reachable with 55 carriers and a 256-point r5/6 top rung.
- The transmitted signal must measure 15 kHz occupied or less. That makes deviation a design output of the simulator, and on wide it trades audio bandwidth against deviation.
- The biggest risk is CPU, not the channel: whether a Raspberry Pi can decode 20+ kbit/s with Data2G's codes inside an FM turnaround. Benchmark it first (M2b), on today's code. If the answer is no, nodes advertise the fastest rate they can decode.
- Decided: digipeating and repeaters are after the first release. The host works with any client; Pat and Winlink Express are the yardsticks for existing VARA FM clients. I/Q receive is an investigation (M10).
- Scope is what fits an audio passband (or a discriminator tap). Wider-than-audio and channel bonding are out; a microwave FM rung or two is an open question (Q18).
- Still the user's: Q2 (how low the floor goes). The rest are measurements.
- Decided: the limit is 15 kHz measured 26 dB down (Part 97's definition, Q15).

## What the others do

VardeFM, from its `docs/PROTOCOL.md` and `docs/RADIO.md` (docs only, no source read):

| | Narrow | Wide |
|---|---|---|
| Connection | mic / speaker | flat 9600 data port, both ends |
| Band | 422..2672 Hz | 281..6000 Hz |
| Carriers, spacing | 49 at 46.875 Hz | 62 at 93.75 Hz |
| Cyclic prefix | 2.67 ms | 1.33 ms |
| Pilots | every 6th carrier, every symbol | same |
| TX tilt | none | +3 dB/octave |
| Deviation target | about 2.5 kHz | about 3 kHz |
| Net rate, 7 levels | 0.7..7.4 kbit/s | 1.9..18.7 kbit/s |
| 10% codeword failure | about 3..16 dB | about 5..24 dB |

- One LDPC length (2400), BPSK r1/2 to 64QAM r5/6. Payload at most 4 s a burst, 24 codewords.
- Symbols hit by a click or squelch pop get low-confidence soft values.
- No frequency search. The FFT window never moves, so burst length is bounded by sample-clock error (13 s narrow at 100 ppm).
- Turnaround 0.2 s. Default txdelay 0.15 s, handhelds need 0.2..0.3 s.
- Level choice from a threshold table plus 1 dB, with per-level SNR ceilings (louder drive on robust levels).
- VARA TCP host interface on 8300/8301. No digipeating, no KISS, no compression. Tune by a 1 kHz tone and a deviation meter; no automatic tune.

VARA FM 4.0, from the author's "VARA FM 4.0 Features" note (speed chart on its last page). Symbol rate 42 on every level. "Net" is my arithmetic: net rate over carriers x 42 x bits per symbol, so it folds code rate and pilots together.

| Level | Wide carriers | Wide mod. | Wide bps | Narrow carriers | Narrow mod. | Narrow bps | Net |
|---|---|---|---|---|---|---|---|
| 1 | 14 | 4PSK | 566 | 14 | 4PSK | 549 | 0.48 |
| 2 | 29 | 4PSK | 1188 | 29 | 4PSK | 1181 | 0.49 |
| 3 | 58 | 4PSK | 2390 | 58 | 4PSK | 2390 | 0.49 |
| 4 | 98 | 4PSK | 4040 | 58 | 4PSK | 3188 | 0.49 wide, 0.65 narrow |
| 5 | 98 | 4PSK | 5387 | 58 | 8QAM | 4252 | 0.65 wide, 0.58 narrow |
| 6 | 98 | 8QAM | 7185 | 58 | 16QAM | 5668 | 0.58 |
| 7 | 98 | 16QAM | 9580 | 58 | 32QAM | 7087 | 0.58 |
| 8 | 116 | 16QAM | 11340 | 58 | 64QAM | 8505 | 0.58 |
| 9 | 116 | 32QAM | 14144 | 58 | 64QAM | 9567 | 0.58 wide, 0.65 narrow |
| 10 | 116 | 64QAM | 16932 | 58 | 128QAM | 11162 | 0.58 wide, 0.65 narrow |
| 11 | 116 | 64QAM | 19003 | 58 | 256QAM | 12750 | 0.65 |
| 12 | 116 | 128QAM | 22102 | | | | 0.65 |
| 13 | 116 | 256QAM | 25210 | | | | 0.65 |

What the chart says about its design:

- Three coding points only (net about 0.49, 0.58, 0.65). The ladder is built from constellation size and carrier count, not code rate. Its top is 256QAM at about rate 2/3, not a high-rate code.
- The bottom is reached by using fewer carriers (14 is about 650 Hz), which puts the whole deviation budget into them and, per the note, picks the part of the audio band the radio passes best. Nothing below 4PSK at about rate 1/2: the floor is 549 bps.
- 58 carriers at 46.875 Hz is 2.7 kHz and 116 is 5.4 kHz. That fits the unverified blog figures of about 470..3140 Hz narrow and 280..5670 Hz wide. The note confirms narrow was shifted up 200 Hz because some radios are poor at low voice frequencies.
- Wide has an intermediate width (98 carriers, about 4.6 kHz) for four levels, so it does not assume every 9600 port passes 5.7 kHz.

Other features the note lists, each a user expectation:

- Variable TX delay per radio. Baofeng squelch-tail elimination must be off.
- Receive equalisation for handhelds whose receive audio takes time to settle after transmitting.
- Level switching tuned on a 117 KB "N5TW standard file" sent both ways. Use the same file size as the session benchmark.
- S/N reported to the host and the log. A monitor log of all connections heard on the frequency.
- Sessions through voice repeaters.
- Digipeating through one or two hops, by a callsign distinct from the gateway's, with a retries setting. The digipeater runs freestanding and the gateway is off while it relays.
- Autotune: the drive level is set against a remote station, which reports S/N and VU, with a pass/fail verdict.
- Ping: S/N and VU at both ends, direct or through digipeaters (the minimum along the chain). VU under -40 dB is flagged as too weak.

Data2G today: w48 tops out at 8222 bps on paper (256-point r5/8, 350..2700 Hz). That is above VardeFM narrow's 7.4 kbit/s and at VARA FM narrow level 7 to 8. It has no mode wider than 2400 Hz and `FS = 8000` caps audio at 4 kHz.

Targets this sets (rates only; the SNR each needs is still M0's job):

- Narrow: 12750 bps. With about 55 carriers on the 50 Hz grid (450..3150 Hz) that is 6.7 bits per data symbol at today's prefix and pilot overhead (256-point r5/6), or 5.6 bits (256-point near r0.7) with a 16-sample prefix and pilots 1 in 12.
- Wide: 25210 bps. With about 55 carriers on a 100 Hz grid (300..5700 Hz) the same two cases give 25.5 and 30.6 kbit/s at 256-point r5/6.
- Both bands are 55 carriers, so one pilot and one header layout can serve narrow and wide.

## Data2G, not a clone

The aim is Data2G on FM, not a copy of VARA FM or VardeFM. The competitors set the rate targets above; the design keeps what Data2G already does differently:

- Gear shifting from a learned outcome model, not a threshold table (M6).
- HARQ with incremental redundancy, so a failed codeword is topped up, not resent.
- Primed reception, nods, CW ID, broadcast and KISS, and the same host interfaces as Data2G HF, so Ragtime and other Data2G clients work unchanged.
- Open source, with a native build for Linux, Windows, macOS, the Pi and Android.

Where FM's channel argues against one of these (for example HARQ round trips against short overs), the plan measures it rather than dropping it by default.

## How FM differs from the HF channel the modem was tuned for

1. The limit is peak deviation, not power. Audio SNR after the discriminator scales with deviation squared, so PAPR costs exactly what it costs on a PEP-limited HF transmitter. The existing clip headroom, ACE and PEP-fair machinery (`DATA2G_PEP_REF_DB`, `clip_constants.json`) carries over with "peak deviation" in place of "PEP".
2. Above threshold (roughly 10 dB CNR) the audio is clean, 25..40 dB, and capped by the radios (distortion, hum, limiter, sound card), not by the path. Below threshold it collapses over about 3 dB of CNR into clicks. The ladder needs many high rungs and few low ones. Measured SNR says little about margin near the cliff.
3. Noise is not white. On a flat (9600) path the discriminator's noise voltage rises 6 dB/octave: 6 kHz is 26 dB noisier than 300 Hz. On a mic/speaker path de-emphasis flattens the noise, but the TX limiter sits after pre-emphasis, so the top carriers eat the deviation budget. Mixed stations (one flat, one mic) see a 6 dB/octave tilt either way.
4. No audio frequency offset. RF mistuning becomes DC and distortion at the discriminator, never a shift of the tones. Only sample-clock error remains (up to 100 ppm a card).
5. Delay spread is microseconds. The cyclic prefix only has to cover the radios' audio filters (group delay at the band edges, the CTCSS high-pass). The 4 ms HF prefix is mostly wasted.
6. Fixed stations on good paths see a static channel. Fixed stations on borderline paths do not: within-horizon and diffraction paths at VHF/UHF fade 5-20 dB below their hourly median for minutes at a time (NBS Tech. Note 88: median 4-7 min at 138 MHz, longer at lower frequencies, worse in maritime climates, not helped by antenna spacing). A session sees the link come and go; the gear shifter and the ARQ must ride it out rather than drop the link. Mobile stations see Rayleigh flutter at 10..50 Hz, which the discriminator turns into click bursts and millisecond dropouts, not into smooth audio fading. The answer is erasure of hit symbols and interleaving, not Doppler tracking.
7. Radios key in 20..300 ms and are quiet in milliseconds. HF's `TURN_S = 1.3` and long bursts are the wrong trade: FM wants short overs.
8. Squelch, tone squelch and key-up transients (PLL settle, a DC step through the AC coupling) eat the start of a burst.
9. Repeaters add a second pre/de-emphasis pair, clipping, audio delay, hang time and time-out timers. Not a goal for the first release.

## Constraint: 15 kHz occupied

The RF signal's measured bandwidth is at most 15 kHz, 26 dB down (Q15, decided 2026-11-16). Measured, not Carson's estimate.

- Definition: the outermost points 26 dB under the spectrum's peak, at 100 Hz resolution (M1's `db26`; 300 Hz gives the same within 0.4 kHz). Part 97's own wording (97.3(a)(8)) can also be read as a power ratio, 99.75% of the power inside; our signals are 0-2 kHz narrower by that reading, so meeting `db26` meets both.
- The rules leave room: 97.307(f)(5) authorizes 20 kHz for data on 2 m (and 19.6 kilobauds; ours are about 45 baud per carrier), and (f)(2) caps it at a communications quality FM phone emission (conventionally 16K0F3E). 1.25 m and 70 cm get 100 kHz under (f)(6). The FCC's proposal to drop the VHF/UHF baud limits (WT Docket 16-239 FNPRM, 2023) had no final order by 2026-11; none is expected to affect us.
- 15 kHz keeps us among existing 2 m modes and inside 15 kHz channel plans. Measured on M1 (`scripts/fm_reference_widths.py`), 26 dB down: FM voice 7.9 kHz at normal level and up to about 21 kHz driven hard into the limiter; 1200 AFSK 9.2 kHz at 3 kHz peak deviation, 13.7 at 4; 9600 G3RUH 12.3 kHz at 3 kHz peak, 18.0 at 4. VARA FM not yet measured.

- Carson's rule is written for peaks: 2 x (3 kHz + 5.7 kHz) says 17.4 kHz for a VARA-like wide mode. The measured width of an OFDM-modulated carrier is set mostly by rms deviation and the top audio frequency, and OFDM's rms sits 6..9 dB under its peak, so the real figure is lower. How much lower is the first thing M1 has to report.
- First-order sidebands reach the top audio frequency each side (11.4 kHz total at 5.7 kHz). Second-order sidebands reach twice that and grow with the square of the modulation index. They are what the limit actually bounds.
- So each mode gets a deviation target from the simulator: the largest rms deviation whose spectrum still fits. Robust modes may get more (VardeFM already drives its low levels harder).
- On wide this couples band edge to SNR. A higher top carrier leaves less room for deviation, and audio SNR goes with deviation squared while discriminator noise rises with frequency squared. The band's top edge, the TX tilt and the deviation are one optimisation, not three (M5).
- On a flat port with no limiter the binding limit is then occupied bandwidth (an rms quantity), not peak deviation. Peaks still matter to the receiver's IF filter and to any radio that does limit. Clip headroom per mode gets re-picked under both.
- The tune procedure (M7) has to land users on the target deviation, or the limit is only true on paper.

## Milestones

Dependencies are named by ID. Sizes are rough new or changed lines of Python, native excluded unless said.

### M0. Baseline (no modem changes)

- Run today's ladder through M1's simulator, and on a real pair of FM radios through mic/speaker, with `sounding.py`.
- Output: where each w48 mode fails against CNR, the SNR ceiling per radio path, and the CNR each VARA FM level needs if a licensed copy is at hand (the VARA Wine harness exists). Its rates are known (chart above); its thresholds are not.
- Depends: M1 for the simulated half. The on-air half can start now.
- Hardware: the maintainer has an IC-9700 (enough for M10's I/Q receive on air) but few 9600-capable radios. Volunteers with a pair of computer-connected VHF/UHF radios with flat, clean TX and RX audio are wanted for M0, M5 and M9.
- This sets the targets for M4 and M5. Until then "match VARA FM narrow" is a guess.

### M1. FM channel simulator (`data2g/fmchannel.py`, about 300 lines)

- Audio in, audio out, at any FS. Inside: optional pre-emphasis, limiter and splatter filter (mic path) or flat (9600 path), FM modulator at complex baseband, IF filter (12.5 or 25 kHz channel), flat Rayleigh/Rician fading at a Doppler, AWGN at a CNR, RF offset, limiter-discriminator, optional de-emphasis and 300 Hz high-pass, sample-clock offset.
- Knobs for the ugly parts: key-up transient, receive audio settling after the station's own transmission (VARA FM added equalisation for it), squelch gate with an opening delay, squelch-tail burst, CTCSS leak, mic-input AGC/compressor, weak low-frequency response. A repeater model (two hops with a clipper between) waits until repeaters are in scope.
- Reports the RF signal's occupied bandwidth (99% power, and the -26 dB width) for any audio and drive, and solves for the drive that meets 15 kHz. Every mode's deviation target comes from this.
- Exposes the complex baseband after the IF filter, so M10 can try other demodulators on the same trials.
- Same call shape as `hfchannel.apply_channel` so `with_native.py`, the loss study and the session study take it as another channel name.
- Calibrate against recordings of real radios (M0). Unlike HF paths, a radio's audio response is repeatable, so here recordings are good evidence (my reading, check it holds).
- Depends: nothing. Everything else depends on it.
- Status (2026-11-15): draft PR #203. Ten conditions at 146 and 440 MHz: static, fixed (SUI-1-like), fixed-fringe (scatter at K 1 plus TN 88 slow fadeouts, sigma 5 dB over minutes), knife-edge (a flat diffracted path, a 15 us echo, fadeouts over half a minute), flutter (aircraft), pedestrian, mobile rural/urban/bad-urban/hilly (COST 207 with Gudmundson shadowing). Sources in the module.
- First numbers (`scripts/fm_channel_survey.py`):
  - Q17: measured, 15 kHz occupied allows 2.0-2.1 kHz rms deviation for OFDM-like audio whether its top edge is 4.6 or 5.7 kHz, 2.3-2.4 kHz with a +3 dB/octave tilt; narrow on the mic path 1.56 kHz. The width is set by rms deviation, so a wider audio band costs no deviation, only spreads it over more carriers.
  - Today's ladder through the conditions (16 bursts a point, CNR in 15 kHz for 10% codeword failure): qpsk-r1/2 at 4 dB or below on static and fixed paths, 12-18 dB on mobile and slow-fading paths; w48-64l-r3/4 9-12 dB static, 16-17 fixed-fringe, 29-34 knife-edge, past 32-40 on urban and hilly mobiles. The slow-fading knees reflect the preset's size (an input), not a measurement.

### M2. Profiles: HF and FM constants side by side

- Today `config.py` is one set of module constants, `FS` is imported by 19 Python modules, about 22 native files hold an 8 kHz assumption, and the generator emits constexprs.
- Needed: FS, numerology (M, NCP, RS, CARRIER0), BANDS, SUBMODES, thresholds, outcome model, ARQ timing and the header CRC seed all chosen by profile.
- The CRC seed must differ so an HF node rejects an FM header where the preamble is shared (narrow FM at 8 kHz would otherwise look like w48).
- Mechanism (Q1, decided): profile fixed at process start (`DATA2G_PROFILE`, read in `config.py`), native built once per profile from its own generated tables. Constexprs stay, no runtime indirection in the hot path.
- Status (2026-11-15): draft PR #204. FM is provisional: 16 kHz on HF's 50 Hz grid (Q19: measured, keep it), HF's ladder as a placeholder, its own protocol version line and a profile tag in the header CRC seed. HF is unchanged on air. Hidden 8 kHz assumptions found and fixed: the TX filter's tap count (at 16 kHz it cost the edge carriers ~3 dB), the Blanker's block and time constants, timing-slip bounds, the impulse filter, sync's FFT period, hand's sample counts.
- What FM must re-measure (each an FM test skip with its reason): the preamble threshold (done in M3: 28.7), Blanker levels on discriminator clicks (M3: the Blanker measured neutral), CP and demod backoff (M4: 1.25-1.5 ms echoes already cost bits at a 2 ms CP), clip constants, mode thresholds, the outcome model.
- Blocks M4, M5, M6 from freezing anything.

### M2b. CPU budget (benchmark first, decide the ladder's top by it)

The open question that could reshape the ladder. Wide at 20..25 kbit/s is about 3x the LDPC work per second of today's top mode (8222 bps), and FM turnarounds are about four times shorter than HF's `TURN_S = 1.3`.

- Measure now, before M4/M5: decoded bits per second on a Pi 4 (minstrel) for today's top codes, native, at the default decoder effort. `data2g-bench-rx` already does this per burst. Compare with 25 kbit/s plus a 0.3 s turnaround. This needs no FM work.
- Incremental decoding. `codes.spread` deals every codeword round-robin over the whole burst, so no codeword can be decoded until the burst ends and all of them are decoded at once. That diversity matters on HF fading; on FM's static or click-hit channel a bounded window (each codeword over a few frames, windows overlapping) may cost little. Then codewords finish during the burst and decoding streams, as the CPM receiver now does. Measure the loss on M1 with flutter before relying on it.
- Cheaper decoding where the channel allows: fewer iterations at high SNR (most FM receptions are far above threshold), min-sum in place of sum-product on the top rungs. Each measured in dB lost against CPU saved.
- Rate capability. If a Pi still cannot keep up, each node advertises the fastest mode it can decode (from a bench at first run, or a setting) in the connect exchange, and the gear shifter never recommends past it. This is a session-layer field, so it has to be in the FM connect frame before that is frozen (M6).
- Depends: nothing for the first measurement. The interleave change depends on M1.
- First measurement (2026-11-15, `docs/pi-bench-fm.md` in PR #206), on a Pi 4 with HF and FM builds of one tree:
  - Listening costs FM 17% of a core against HF's 21%: the +-12.5 Hz search pays for 16 kHz.
  - A converging 256l-r5/8 x39 burst (92 kbit, close to one 4 s burst at 25 kbit/s) delivers its payload 0.38-0.44 s after the burst ends on FM, against 0.27-0.31 s on HF. That is near a 0.3 s turnaround.
  - Failing bursts spend the whole 1 s DD budget on both profiles. That is the risk.
  - Per-symbol noise costs about 55 ms of soft bits on 256-point; a cheaper nearest-point search is wanted.
  - Done (PR #214): 8-frame interleaving and channel-estimate windows (FM protocol 2; at most +0.12 dB, up to 1.24 dB better on slow fading), and decoding while the burst arrives. Pi 4: clean bursts end 2-4x sooner (256l x39 at 30 dB 191 ms, 64l x30 at 24 dB 138 ms); failing ones within 1.57 s, against up to 4.1 s. Bench again once a wide band exists. No rate-capability field is called for yet.

### M3. Receiver changes for FM (receiver-only, testable on today's waveform)

- Coloured noise: check `equalizer.per_carrier_noise` copes with a 26 dB slope across the band, and that the demapper uses it everywhere (header included).
- Click and dropout erasure per symbol, from the residual against the pilots or the envelope. `audio.Blanker` is tuned for HF static; measure it on discriminator clicks before reusing it.
- Acquisition without a frequency search: sample-clock only. This is a physical property of the channel, not a narrowing by expected mode, so it does not break the "search must stay full" rule. It should cut detector CPU several times over (the HF note in `config.py` measured 5x between search widths).
- Tolerance to a missing or damaged burst start (squelch opening, key-up transient): detect on later preamble repeats, or lean on the header copy.
- Depends: M1.
- Status (2026-11-15): draft PR #206. Measured with `scripts/fm_rx_study.py` on the FM simulator. It runs the live streaming receiver after open-squelch hiss, with 30 paired trials. Results, in dB of CNR against today's receiver:
  - Per-symbol noise in the demapper: 0.9 / 1.8 / 2.25 dB better on mobile paths (QPSK, 16-QAM, 64-point), 0.1-0.5 on flutter, 0.2-0.35 on slow fading, never worse. On for FM, in Python and native.
  - +-12.5 Hz search (FM audio has no frequency offset): the same loss within 0.05 dB, the detector's CPU 6.7x less. FM default.
  - Preamble threshold 28.7 for FM, from 1200 s noise peaks of what an idle FM receiver delivers. The worst source is mic-path hiss with the squelch open: 33.8 at +-150 Hz, 26.1 at +-12.5 Hz. Loss is the same anywhere from 26.7 to 37.2, because FM's cliff puts preamble detection far below where data fails. No false burst events on about 17 h of hiss: noise crossings die at the header.
  - The Blanker is neutral on FM. Without it, an idle carrier's clicks drive the detector to 35-38, but the receiver blanks before detecting.
  - Coloured noise: per-carrier noise (`equalizer.PER_CARRIER_NOISE`) is already on, and the demapper uses it.
  - Method note: `modem.demodulate` on a buffer known to hold the burst cannot see receiver-state changes. Thresholds and the blanker measured identical through it. Judge M3-type changes by the streamed harness.
- Damaged burst start (`scripts/fm_start_study.py`, 40 paired trials, 25 dB): no receiver change needed.
  - Bursts were acquired almost every time with the carrier up to 0.45 s late (preamble and header gone): the header copy.
  - Every mode decodes with the carrier up to 0.2 s late. Beyond that, the erased data loses high-rate modes: 64l-r3/4 at 0.3 s, 16qam-r1/2 on the mic path at 0.45 s.
  - A key-up synthesiser transient changes nothing.
  - So the TX delay must cover the radio's key-up time (M7).
- Open: per-symbol noise on HF, issue #207.

### M4. Narrow ladder (mic/speaker, FS 8000)

- Start from w48. Decide by measurement on M1 and real radios:
  - Band edges. VARA FM moved up to about 470..3140 Hz to avoid poor low-frequency response; VardeFM stops at 2672 Hz. Candidate: 55 carriers, 450..3150 Hz. A band that some radios cannot pass is worse than a narrower one, so the top modes may need a width fallback like VARA's wide 98/116 split.
  - Cyclic prefix. 32 samples now; 8..16 may do. Worth up to 15% rate.
  - Pilot density. One symbol in six was sized for 2 Hz Doppler. A static channel needs the preamble plus sparse tracking of clock drift; flutter is handled by erasure. Worth up to 15%.
  - Preamble repeats (8 now) and header airtime, for short overs.
  - Top rungs: 256-point at r0.7..r5/6 to reach 12750 bps (targets above). VARA stops at 256QAM near r2/3, so the radios' SNR ceiling probably sits around there; 1024-point is unlikely to pay.
  - Bottom rungs: VARA's are fewer carriers, not lower rates. The existing w (1200 Hz) and n10 (500 Hz) QPSK modes play the same part and already go lower (128 bps against 549).
  - Clip headroom per mode, re-picked under a peak-deviation limit with pre-emphasis and the radio's limiter in the loop.
  - TX tilt, so the pre-emphasised signal uses the deviation budget evenly.
  - Deviation target per mode under the 15 kHz limit. With audio to 3.15 kHz the radio's own limiter (5 kHz peak) probably binds first; confirm on M1.
- Drop the n4 and CPM families from the FM profile unless Q2 says otherwise. Keep w and n10 QPSK rungs as the floor and for ACKs.
- Depends: M1, M3 (the erasure changes which rungs survive flutter), M0 for targets, M2 to freeze.

### M5. Wide ladder (9600 port or direct taps)

- Step 1: the FM profile runs at FS 16000 on the 50 Hz grid (M2), so a wide band is just more carriers, as VARA FM does. 100 Hz spacing was measured and lost (Q19).
- Step 2: a wider band on the same grid, about 300..5700 Hz (55 carriers, the count M4's narrow band uses, so its pilot and header layout are shared). Arithmetic: about 19 kbit/s with today's top code, 25.5 kbit/s with 256-point r5/6, 30.6 with M4's prefix and pilot savings. VARA FM's top is 25210.
- A narrower wide band (about 4.6 kHz, as VARA's 98 carriers) for ports that roll off early: on this grid it is just fewer carriers.
- Step 3: fit the f-squared noise. A fixed TX tilt first (VardeFM uses +3 dB/octave). Per-carrier bit loading only if the fixed tilt leaves several dB on the table.
- Top edge, tilt and deviation chosen together under the 15 kHz limit (see the constraint section). Expect the answer to sit below VARA's 5.7 kHz for the weaker rungs: the narrower wide band above is also the one that affords more deviation.
- Check real 9600 ports: many roll off before 6 kHz (Q7).
- OFDM starts at 300 Hz, so ordinary AC-coupled sound cards work. A single-carrier FSK floor mode would need response to a few Hz. Not planned.
- Depends: M1 (flat path), M2 (FS per profile, which is most of M2's cost), M3 (coloured noise).

### M6. ARQ timing and gear shifting

- Timing constants per profile: `TURN_S`, `TIMEOUT_S`, `MAX_BURST_S`, burst-length policy, PTT lead (already `--ptt-on-delay-ms`). FM wants turnarounds near 0.2..0.3 s and bursts of a few seconds.
- Gear shifter: start with a threshold table per mode on M1 (as `mode_thresholds.json`), then train the outcome model on FM data. The HF model's inputs (spread, fading regime) mean nothing here. Likely inputs: per-carrier SNR profile, click or erasure rate, SNR ceiling.
- Capability per direction (from the discussion): each station sets its TX capability and its RX capability separately (narrow or wide, and M2b's rate cap). A half-link's cap is the narrower of the sender's TX and the receiver's RX, so the two directions of a link can differ. Unlike HF's `BW`, which takes the lower of the two ends for the whole channel. Cases: a data cable rigged for 1200-style mic TX but a flat RX tap; an IC-9700 receiving wide over I/Q (M10) but transmitting narrow. The connect exchange carries both, and the gear shifter caps each direction's recommendations by its own.
- Cliff behaviour: fast fall-back on the first lost codewords, fast climb when quieting returns. Judge by paired sessions on M1 with fading and with a CNR ramp through threshold, in dB of CNR where a rate is reached.
- Depends: M4 and M5 ladders frozen, M2.

### M7. Station setup tools

- Deviation tune: a tone and a modem-like test burst, level meters, and a report of the far end's reading. VARA FM's Autotune steps the drive level against a remote station and gives a verdict with S/N and VU; users will expect the same. `sounding.py` is the starting point.
- Ping: S/N and input level at both ends without opening a session, through digipeaters if M8 has them.
- TX delay per station, with guidance for handhelds (squelch-tail elimination off). Measure the radio's key-up time against the far end (M3: 0.2 s of slack past the TX delay before high-rate bursts fail).
- A station receiving I/Q (M10) can measure the far end's deviation and occupied bandwidth in Hz, which turns Autotune from "sounds right" into a check of the 15 kHz limit.
- Overdrive diagnostic: the signature seen on 2026-10-31 (OFDM SNR pinned near the PAPR while FSK reads 25 dB or more) as a plain warning to the operator.
- Radio path settings, TX and RX separately (M6's capability per direction): mic or flat each way, which picks narrow or wide and the TX tilt.
- PTT: `native/core/rig` has no CM108/CM119 GPIO keying that I could find. Most FM sound-card interfaces (AIOC, DigiRig Lite, DRA, Masters Communications) use it or serial RTS. Confirm and add.
- Depends: M2 for the UI. Otherwise independent, and useful to today's users on FM.

### M8. Host and network features

- The host works with every client: Ragtime, other Data2G clients, and ones not written yet. The existing host interfaces stay the same on FM.
- For existing VARA FM clients, Pat and Winlink Express are the yardsticks, in their "VARA FM" session types. Both have the user pick VARA HF or VARA FM first, so the version reply need not imitate VARA. The work is a test against each client and accepting whatever they send in FM mode that `host.py` does not know (candidates: no BW commands, NARROW or WIDE on `CONNECTED`, `via` on `CONNECT`).
- Digipeating: in scope, after the first release. VARA FM's shape: one or two hops named in the connect, a digipeater callsign separate from the gateway's, a freestanding relay with a retries setting. Its own design doc when it starts. For now only two cheap things: `CONNECT ... via` gets a clean refusal, and the FM session's connect frame is checked for room to carry via calls before its version is frozen (M6).
- S/N reports to the host, and a log of stations heard.
- KISS and broadcast should work unchanged over the FM profile. Verify, do not redesign.
- Depends: M6.

### M9. Native, Pi, on-air, release

- Native port of M3..M6, generated tables per profile, `native/build-test` ctest.
- Pi 4 bench of the finished FM ladder, confirming M2b's numbers and the advertised rate caps.
- On-air trials on at least: two mobiles/handhelds on mic, two 9600-port radios, one mixed pair. Simplex only. Measure occupied bandwidth of each on a spectrum display.
- User guide chapter, speed sweep per `docs/speedtests/README.md`.
- Depends: all of the above.

### M10. Investigation: I/Q receive with ordinary FM transmit

Few stations can transmit from I/Q, but a fair number can receive it (a separate SDR receiver, an IC-9700, a FlexRadio) while transmitting through a normal FM radio. This is receiver-only: no protocol change, and the far end need not know.

What it could buy, in the order I would test it:

- Our own discriminator. No radio audio filters, no de-emphasis, no squelch, no 9600-port roll-off, a known flat response to any band edge. This alone may make "wide" receivable by a station whose radio has no flat output.
- Erasures from the RF envelope. Below threshold, clicks happen when the carrier envelope dips, and with I/Q the dip is visible. That replaces guessing click positions from audio (M3) with knowing them, under noise and under mobile flutter.
- A real CNR. Audio SNR saturates above threshold and says nothing about margin to the cliff. CNR from I/Q gives the gear shifter that margin directly (M6).
- Threshold extension: a tracking (PLL or feedback) demodulator in place of the limiter-discriminator. Textbook gain is a few dB of CNR at the cliff.
- Decision-directed demodulation: re-modulate the decoded burst and correlate at RF. Research, only if the steps above leave a visible gap.
- Measuring the far end's deviation and occupied bandwidth (M7).

What it costs: an I/Q input path (stereo I/Q on a sound device first; network SDR sources only if that proves the case), tuning offset removal, muting and recovery around our own transmission, and whatever latency the SDR adds to the turnaround.

Method: simulator only at first. M1 already has the complex baseband, so the same trials run through the radio audio path, a software discriminator, discriminator plus envelope erasures, and a tracking demodulator. Judge by the dB of CNR where each rate is reached, AWGN and flutter. Build the input path only if that is worth more than about 2 dB or enables wide on radios that cannot otherwise receive it.

Depends: M1, M3. Independent of M2 and the ladders.

## Dependency summary

```
M1 sim ──┬─> M0 baseline ──> targets for M4, M5
         ├─> M3 receiver ──┬─> M4 narrow ──┐
         │                 └─> M5 wide ────┼─> M6 ARQ + shifter ──> M8 host ──> M9
M2 profiles (PR #204) ──────────> (freeze M4, M5, M6)
M2b CPU budget: Pi measurement now; interleave change needs M1; caps the top of M4, M5; capability field in M6
M7 tools: independent, needs M2 only for UI
M10 I/Q receive study: needs M1, M3; feeds M3 (erasures), M6 (CNR), M7 (deviation)
digipeating, repeaters: after the first release
```

First pieces of work: M1, the Pi measurement in M2b, the on-air half of M0 (needs volunteer radios for the 9600 path), M3. None needs a decision.

## Open questions

Decisions for the user:

- Q2. How low does the FM floor go? VARA FM stops at 549 bps (4PSK on 14 carriers). The CPM floor reaches SNRs FM audio never delivers with a usable carrier, and squelch hides them anyway. Recommendation: keep the w and n10 QPSK rungs (down to 128 bps), no CPM, no n4.
- Q18. Is there a microwave FM rung or two worth having? Wider channels there allow more deviation and a wider audio or discriminator band than 15 kHz permits on 2 m and 70 cm. Only if it stays inside what a sound card or discriminator tap carries, and costs 2 m and 70 cm nothing.
- Q16. Are 12.5 kHz channels (2.5 kHz deviation, about 11 kHz occupied) a case to support, or is 15 kHz the only target?

Decided (2026-11-13, Q1 2026-11-15, Q15 2026-11-16):

- Q15. 15 kHz measured 26 dB down, US Part 97's definition (see the constraint section for the rules and the reference modes' widths).

- Q1. One codebase, profile fixed at process start, native built once per profile (PR #204).
- Q19 (measured, PR #205). Keep 50 Hz spacing. 50 Hz (48 carriers) against 100 Hz (24 carriers, 2 ms CP), same band, modes matched in code and coded bits, every simulator condition, 30 paired trials, each at a measured preamble threshold:
  - Fixed and static paths: no difference (within 0.3 dB).
  - Mobile paths: 100 Hz is 1.1-1.2 dB worse for QPSK and 16-QAM. That holds even with a 16-repeat preamble, which matches 50 Hz's preamble time.
  - Slow fading: 100 Hz is 2.2 dB worse.
  - Flutter at 440 MHz: 100 Hz with 8 repeats is 0.6-2.6 dB worse.
  - The 64-point mode: no significant difference.
  - Where it loses, most of the loss is acquisition. The data path shows no 100 Hz gain: RF Doppler reaches the audio as clicks and dropouts, not as fast fading for shorter symbols to track.
  - 50 Hz also carries 9% more at the same 2 ms CP.
  - A 4 ms CP was worse than 2 ms. A 1 ms CP at 100 Hz does not decode at all (acquisition timing is good to +-1 ms at 16 kHz).
- Q3. Digipeating is in scope, not needed for the first release.
- Q4. No imitation of VARA's version reply. The host works with any client; Pat and Winlink Express (VARA FM session types) are the yardsticks for existing VARA FM clients.
- Q5. Repeaters are not needed for the first release.
- Q6. I/Q transmit is rare and not planned. I/Q receive with FM transmit is investigated (M10).

Measurements that decide design:

- Q7. Usable band and SNR ceiling of real radios, per path: mic/speaker, 9600 port, handheld speaker-mic jack. Sets M4 and M5 band edges and top rungs.
- Q8. How much do prefix and pilot thinning really buy once clock drift and flutter are in the simulator?
- Q9. Fixed tilt or bit loading on wide (M5 step 3)?
- Q10. Does symbol erasure plus the existing interleaver hold a mobile link at 20..50 Hz flutter, or do the codewords need to be longer in time?
- Q11. Wide at FS 16000 or 24000? 16000 keeps every sample count and reaches 6 kHz with a 2 kHz transition band. 24000 only matters if radios pass more than 6 kHz, which Q7 answers.
- Q12. Pi 4 decode budget at 20..25 kbit/s with a 0.3 s turnaround, and how much incremental decoding and cheaper decoding recover (M2b).
- Q13. Regulatory check beyond the 15 kHz target: symbol-rate or other limits for the wide mode on 2 m and 70 cm (US Part 97 at least). Not verified here.
- Q17. How much deviation does 15 kHz allow at each candidate top edge (3.15, 4.6, 5.7 kHz), and does VARA FM wide at its recommended drive actually fit? Sets whether matching 25210 bps is possible inside the limit at all.
- Q14. VARA FM's thresholds per level on the same simulator, for a like-for-like target. Its rates are in the chart above.

## Not planned

- A new waveform family for FM. OFDM over the audio or flat path is what both competitors use, and the existing modem covers it.
- Single-carrier FSK or constant-deviation modes for the weak-signal end (needs DC-coupled audio, see M5).
- Interoperation between HF and FM profiles, by the brief.
- Anything wider than an audio passband or a discriminator tap, and channel bonding. Wideband SDRs on 2.4 GHz can go much faster, but the sensible way to do that is OFDM in hardware at the radio, which is WiFi. Microwave FM within an audio passband is Q18.

## Revisions

- 2026-11-16, Q15 decided (15 kHz, 26 dB down) with the rules and existing modes' measured widths; capability per direction (TX and RX separately) from the discussion; PR #214's windows and decoding while the burst arrives.
- 2026-11-15, M2b first Pi bench and M3's damaged burst start (PR #206); HF per-symbol noise is issue #207.
- 2026-11-15, M3 (PR #206): per-symbol noise up to 2.25 dB on mobile paths; +-12.5 Hz search at no cost, 6.7x less detector CPU; FM threshold 28.7.
- 2026-11-15, Q19 measured (PR #205): keep 50 Hz; FM's 8-repeat preamble threshold needs about 26.7.
- 2026-11-15, Q1 decided and M1/M2 begun (PRs #203, #204): bands 144-450 MHz primary; borderline fixed paths' slow fadeouts (TN 88) in the channel differences and the simulator; first simulator numbers; FM re-measurement list; Q19 (carrier spacing).
- 2026-11-15, from the first comments: host scope is every client, with Pat and Winlink Express as yardsticks; CPU budget moved up front as M2b (incremental decoding, rate capability); "Data2G, not a clone" section; hardware and volunteers in M0; wider-than-audio out of scope, microwave FM rung as Q18.
