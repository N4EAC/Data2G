# On air, 2026-11-22: pairing P2 (FT-8800R flat and IC-9700), first session

KC2G, 432.950 MHz simplex, minimum power, a few metres apart: full quieting throughout.

## Setup that worked

- FT-8800R: data port at 9600 (flat: no pre-emphasis, discriminator out), through a DigiRig.
  - Audio: PipeWire `alsa_output/alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00` (data2g-host and miniaudio name it "CM108 Audio Controller").
  - PTT: RTS high on /dev/ttyUSB3. data2g-host: `--rig-model 1 --ptt-method rts --ptt-device /dev/ttyUSB3 --rig-dtr low --tx-path flat`. Standalone: `runs/onair/serial_ptt.py /dev/ttyUSB3 rts`.
  - DigiRig levels: sink 100%; source 50% (hardware Mic Capture +7.4 dB); ALSA "Auto Gain Control" OFF.
- IC-9700 as in P1 (CAT PTT, USB MOD 40%, PipeWire sink 40%, tx_path mic).
- `runs/onair/tx_rx.sh`: play a sounding while keyed by serial or CAT PTT and record any device.

## Levels and wiring

- The DigiRig's "Auto Gain Control" (on by default) overdrove its input from the FT-8800R's 9600 output: 13-58% of samples clipped even at 0 dB capture gain. Off: bursts at -23 dBFS at 0 dB gain, no clipping. The FT-8800R has no data-level menu.
- FT-8800R flat TX into the IC-9700 IF: linear (64/256-point peak/rms ~3, no pinned peak), the +3 dB/octave tilt arrives as sent. At DigiRig sink 100%: f55 1.08 kHz rms, f108 0.86 kHz rms in-band deviation, ~7 dB under the 2.35 kHz flat target, with no more drive available. Matters only at low CNR.
- Soundings (6 modes, one round each; genie S/N):

| direction | genie S/N | decodes |
|---|---|---|
| FT-8800R -> IC-9700 IF (flat) | 30-34 dB | all: QPSK, 64l r.67, 256l r.88 on f55 and f108 |
| IC-9700 -> FT-8800R 9600 out (mic) | 22-24 dB | QPSK; f55 64l r.67; not f108 64l r.67, not 256l |

- IC-9700 -> FT-8800R S/N unchanged with 11 dB more capture gain: not the DigiRig's converter.

## Ping (narrow and wide)

- Narrow: FT-8800R -> IC-9700 AF snr 28.1, dist 0.6, "level OK". IC-9700 -> FT-8800R snr 22.7, dist 2.4: "your audio drives the radio's limiter".
- Wide: the f108 top third (3.8-5.65 kHz) at -4..-5 dB both ways: the IC-9700's AF path (TX and RX) carries nothing above ~4 kHz. f108 needs the IC-9700's IF (or another flat radio).
- Verdict gap: wide FT-8800R -> IC-9700 also got "limiter" (dist 2.7): a dead third inflates the distortion measure.

## ARQ sessions (BW1200 = NARROW, 30 kB random data)

- FT-8800R -> IC-9700: 34.2 s after CONNECTED, 7008 bps, intact.
- IC-9700 -> FT-8800R: 60.1 s, 3991 bps, intact.
- Mostly f55-64l-r83 on data bursts.

## Conclusions so far

- P1's ~15 dB IC-9700 -> TH-D75 ceiling was mostly the TH-D75's receive path: the same IC-9700 TX reaches 22-24 dB on the FT-8800R.
- The 22-24 dB is the IC-9700's data-mode TX (its compression; the ping's distortion check flags its limiter). Next check: IC-9700 USB MOD level down (10-20%) and see whether S/N rises and dist falls.
