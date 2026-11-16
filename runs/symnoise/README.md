# Issue #207: per-symbol noise (SYMBOL_NOISE) on HF

TLDR: ungated, it doubles goodput under long impulses but costs 3-6% on MPD
and MPG -4. Gated at 4x the burst median (DATA2G_SYMBOL_NOISE_GATE=4) it is
bit-identical on clean/fading cells and keeps every impulse gain.
Recommendation: turn it on for HF with gate 4 (and port the gate to native).

All: loss_study.py, PEP5, 12 seeds x 600 s, shift+cpm, paired on seeds.
Cell SNRs are PEP5 labels (display = label + 5 dB).

## Ungated vs off (loss.sh, paired.txt)

- imp_long: awgn +4 +115% (12/0), mpg 0 +104% (11/1), mpp 0 +72% (9/2), mpd 0 +55% (9/1)
- mpg/imp 0: +6.8% (9/3); other imp cells flat
- MPD loses: -4 -3.2% (1/9), 0 -5.5% (3/9), +8 -2.6% (3/8), slow 0 -3.2% (3/9)
- mpg -4 -5.8% (1/9), mpg/mid +4 -8.6% (2/9), mpp +15 -2.1%
- rec cells, carriers, edge, qrm_wide, AWGN, MPP: within noise
- The MPD loss is in long low-rate bursts: w48-qpsk-r1/5 first-tx cw 89.2% -> 83.5%,
  qpsk-r1/5 91.9% -> 88.0%. Every symbol above the median was being scaled,
  even 1.1x, which fast fading does all the time.

## 10% ladder (ladder.sh, ladder_sym*.csv; control + 1 cw, seed 0)

9 OFDM modes x awgn/mpg/mpp/mpd: every shift within +-0.38 dB (bisection step
0.19). w48-64l-r3/4 on MPD: >40 dB off, 37.2 dB on. Short bursts do not show
the MPD loss; it is a long-burst effect.

## Gated (gate.sh, paired_gate*.txt, against loss_sym0.csv)

| cell | ungated | G=2 | G=4 |
|---|---|---|---|
| mpd -4 | -3.2% | +0.8% | 0.0% (identical) |
| mpd 0 | -5.5% | -1.2% | 0.0% (identical) |
| mpd +8 | -2.6% | -0.8% | -0.3% |
| mpd/slow 0 | -3.2% | -0.5% | 0.0% (identical) |
| mpg -4 | -5.8% | +0.3% | 0.0% (identical) |
| mpg/mid +4 | -8.6% | -0.5% | -0.8% (1/1) |
| mpg/imp 0 | +6.8% | +7.2% | +7.3% (11/1) |
| awgn/imp_long +4 | +115% | +125% | +123% (12/0) |
| mpg/imp_long 0 | +104% | +125% | +122% (12/0) |
| mpp/imp_long 0 | +72% | +88% | +101% (10/2) |
| mpd/imp_long 0 | +55% | +57% | +72% (8/2) |

## Not done

- Gate not re-measured on FM (fm_rx_study.py). FM's mobile gains may rest on mild
  scaling a gate would drop; FM may want gate 1, HF gate 4.
- Native has no gate yet; needs the constant in modem::symbol_noise_scale + tables.
- Pi CPU of slot_soft with SYMBOL_NOISE on (issue's last bullet).
- Impulses are simulated (interference.PRESETS imp/imp_long); recordings show no change.
