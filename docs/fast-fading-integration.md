# fast-fading-integration

TLDR: three study branches merged on `9894b63` for outside study. Every feature keeps its switch. The defaults
here are each branch's best measured setting, not today's on-air behaviour. Python only: native is not ported,
so native builds and `--native` tests do not match this branch with its defaults.

- Base: `9894b63` (master when the numbers were measured; not rebased).
- Merged: `fsk-wide-bins` (bf658cf), `c32r62-r23` (7faf936), `scattered-pilots` (b4f0a4c).
- Added on top: the leak model on sub-window sums, the acquisition switch, the defaults, this file.
- Not a release candidate. Nothing here has been on air.

## Switches

| Switch | Default here | Off value | What it does |
|---|---|---|---|
| `DATA2G_PILOTS` | `mix` | `off` or empty | OFDM pilots scattered through the frame (same 1/6 of the cells) instead of a pilot row. `k3d2`, `gold`, `mix` (k3d2's stride on w and w48, gold's on n10 and n4). Wire change, both ends. |
| `DATA2G_CPM_LEAK` | `ctl,data,dd,ctlsq` | `off` or empty | CPM soft values treat the energy beside a tone as that tone's Doppler leak, not as noise (`cpm.leak_metric`), for the control codeword, data and DD. `ctlsq`: a control codeword whose rows read spill >= 0.15 stays on the square law. Receiver only. |
| `DATA2G_CPM_LEAK_K` | `0.5` | | The leak model's share of unmodelled leak counted as noise. |
| `DATA2G_CPM_CTL_SQ` | `0.15` | | `ctlsq`'s threshold. |
| `DATA2G_CPM_R23` | on | `0` or `off` | `fsk32r62-r2/3` exists: header index 4 on c32r62, recommendation index 6. Wire addition. |
| `DATA2G_OUTCOME_R23` | on | `0` or `off` | The outcome model is `outcome_predictor_r23.npz` (the installed weights, with a mode row for r2/3). Off: the installed model, which never recommends r2/3. Follows `DATA2G_CPM_R23`. |
| `DATA2G_CPM_ONAIR` | `c8w50` | `off` or empty | The wide-bin grid c8w50 is an on-air grid: every receiver searches it. Its modes are control-only and have no recommendation code. |
| `DATA2G_ROBUST_RULE` | `connect` (while c8w50 is on air) | `off` or empty | CONNECT retries go in `fsk8w50-r1/2`, not `fsk16r25-r1/2`. In-session robust modes stay as today. Others: `replace`, `alt`. |
| `DATA2G_ROBUST_FAST` | off | `off` or empty | `wide`, `always`: c8w50 as the in-session robust mode too (measured worse). |
| `DATA2G_CPM_ACQ_K` | `1` (off) | `1` or `off` | The coarse stage's best K placements go to the fine stage. Small gain, large CPU: not recommended. With `DATA2G_CPM_ACQ_SCREEN`, `DATA2G_CPM_ACQ_FLOOR`. |
| `DATA2G_CPM_SHARE` | `1` | `0` | c8w50's search rows are sums of c8r50's (same result either way). |
| `DATA2G_CPM_WIDE` | off | | Studies: every wide grid's modes (c16w125 too) in `arq.modes.MODES` for fixed bursts. c16w125 is never on air. |

Today's behaviour exactly:

    DATA2G_PILOTS=off DATA2G_CPM_LEAK=off DATA2G_CPM_R23=off DATA2G_CPM_ONAIR=off DATA2G_CPM_ACQ_K=off

With that line, `runs/ident.py`-style hashes of the CPM grids (modulated bursts, energies, locks, soft values)
equal master `9894b63`.

## Tests

Run a suite alone (`tests/test_host.py` shares a TCP port).

All switches off: 850 passed, 1 failed. The failure is `test_cpm.py::test_r23_announced_at_index_4_and_older_words_unchanged`,
the r2/3 feature test, which needs the mode on.

Defaults: 836 passed, 17 failed. The feature tests of all three branches pass
(`tests/test_cpm_wide.py`, `tests/test_scattered.py`, the r2/3 test in `tests/test_cpm.py`). The failures assert
today's wire or today's receiver on the old pilot layout, and were left as they are:

- Scattered pilots (13; the same 13 fail with only `DATA2G_PILOTS=mix` on):
  - `test_arq_phy.py::test_long_control_is_pinned_where_its_padding_starts`
  - `test_channel_torch.py`: `test_transmit_matches_numpy_modulator`, `test_ace_transmit_matches_numpy_and_keeps_points_in_their_regions`, `test_bmi_agrees_with_the_full_modem`
  - `test_dd.py`: `test_dd_rescues_a_codeword`, `test_dd_budget_spent`
  - `test_equalizer.py::test_a_tone_on_one_carrier_does_not_sink_the_burst`
  - `test_modem.py`: `test_timing_slip_recovered[-64]`, `[85]`, `test_a_steady_tone_does_not_read_as_pilots[n4]`
  - `test_receive_head.py::test_weak_header_at_the_burst_end_is_received`
  - `test_receiver.py::test_a_false_lock_on_data_does_not_cost_the_next_burst`
  - `test_sounding.py::test_fading`
  - The slip, steady-tone, weak-header and false-lock ones are receiver behaviour, not layout: the unjudged
    `find_copy` gates and slip search under Caveats.
- c8w50 (3):
  - `test_arq_session.py`: `test_connect_retries_in_the_robust_mode_and_is_answered_in_it`, `test_compact_connect_over_the_cpm_modem` (they expect fsk16r25 retries)
  - `test_arq_policy.py::test_recommend_roundtrip_every_submode` (the c8w50 modes have no code)
- Native (1): `test_native_parity.py::test_generated_tables_current`.

## Smoke loss study

12 seeds x 600 s, `shift+cpm`, PEP 5, Python, all switches off against the defaults, paired.

Delivered bit/s, mean of the seeds (seeds that delivered nothing in brackets), change ± SE, and the modes that
carried the most data codewords with the defaults.

| Cap | Cell | All off | Defaults | Change | Top data modes, defaults |
|---|---|---|---|---|---|
| 2400 | hilat-d 10 | 40 (6) | 107 (0) | +165% ± 31 | fsk32r62-r2/3 |
| 2400 | hilat-m 10 | 80 (0) | 278 (0) | +249% ± 49 | w48-qpsk-r1/2, fsk32r62-r2/3, w48-16qam-r1/3 |
| 2400 | hilat-m 20 | 88 (0) | 330 (0) | +275% ± 59 | fsk32r62-r2/3, w48-16qam-r1/3 |
| 2400 | lowlat-d 10 | 85 (0) | 131 (0) | +53% ± 9 | fsk32r62-r2/3, w48-qpsk-r1/3 |
| 2400 | nvis-d 10 | 631 (0) | 952 (0) | +51% ± 5 | w48-qpsk-r1/2 |
| 2400 | mpd 0 | 420 (0) | 479 (0) | +14.2% ± 1.9 | w48-qpsk-r1/5 |
| 2400 | mpp 0 | 483 (0) | 458 (0) | -5.3% ± 2.0 | w48-qpsk-r1/5, qpsk-r1/2 |
| 2400 | mpp -8 | 107 (0) | 102 (0) | -4.4% ± 2.9 | fsk32r62-r2/3, fsk32r62-r1/2 |
| 2400 | awgn -12 | 105 (0) | 124 (0) | +17.7% ± 4.6 | fsk32r62-r2/3, fsk32r62-r1/2 |
| 2400 | awgn 6 | 1730 (0) | 1714 (0) | -1.0% ± 0.0 | w48-16qam-r1/3 |
| 500 | mpd 0 | 179 (0) | 251 (0) | +40.5% ± 5.3 | n10-16qam-r1/3, n10-qpsk-r1/2 |
| 500 | mpp 0 | 270 (0) | 290 (0) | +7.3% ± 1.5 | n10-16qam-r1/3 |

hilat-m 20 is one cell more than was asked, added because c8w50 retries alone had lost 12% there.

Against what the parts predicted:
- hilat-d 10: the leak model alone and c8w50 retries alone each reached 84 bit/s with no dead sessions. Together
  with r2/3 it is 107: the extra is r2/3 carrying the data.
- hilat-m: the parts were measured separately at +3.5% (c8w50, 10 dB) and -12% (c8w50, 20 dB). Here the pilots
  and r2/3 lift both cells threefold, so c8w50's own effect there cannot be read from this table.
- mpp 0 and mpp -8 are down 4-5%. mpp 0 is inside the pilots' known mid-SNR loss. mpp -8 is CPM territory where
  the pilots do nothing: r2/3 carried most codewords there on a zero-shot predictor row, which is the likely cause.
- awgn 6 is down 1.0% on every seed: the same mode, so a fixed cost of the pilot layout.
- This is the first run of the three together. No part's own numbers were rerun in this build.

To rerun (no native):

    export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 DATA2G_PEP_REF_DB=5
    python -m scripts.loss_study --policy shift+cpm --seeds 12 --horizon 600 --jobs 6 --cap 2 \
        --cells hilat-d:10,hilat-m:10,mpp:0 --out runs/loss_defaults.csv
    # the same with the off line above in the environment, --out runs/loss_off.csv; --cap 0 is 500 Hz

`DATA2G_PEP_REF_DB=5` sets the noise against each burst's envelope peak. Displayed SNR is the cell + 5.
Do not use `tools/with_native.py` on this branch.

## Caveats

Scattered pilots (`DATA2G_PILOTS`):
- Mid-SNR mpp and mpg lose 2-7%.
- The w48 channel estimate costs more CPU.
- `find_copy`'s gates and the slip search were not judged with the new layout.
- The policy is untrained on it.

r2/3:
- Its predictor row is zero-shot: no data of the mode went into the model.

Leak model:
- The 0.15 control threshold is tight (fsk16r25 control rows read 0.16-0.24 on hilat-d, everything else under 0.145).
- Nods are untouched: on hilat-d they are missed 46-61% of the time.
- On c8w50 it changes nothing at 30 Hz and helps at 60 Hz.

c8w50:
- hilat-m 20 dB lost 12% in the paired loss study (4 SE), hilat-m 0 dB 7% (1.4 SE). Those runs had a fault this
  branch fixes (`ROBUST_CONNECT` was missing from `ROBUST_MODES` under the connect rule, so a fsk16r25 robust
  poll was answered in the reply mode). The cells have not been rerun alone since.
- A connect at the first retry takes 3.3 s longer (23.2 s against 19.9 s).
- A fourth grid in every receiver's search: 5.6% of a core against 3.8% in Python, the fine stage, not the transforms.
- False-lock runs were 1-2 h a source, not the 8-16 h the on-air grids passed. `COH_LOCK` is set from noise only.
- Connects at the mild floors are 6-7 points behind at -18 dB on mpp and mpd.
- A session version bump would be needed before any release: an older station does not hear c8w50 retries.

Acquisition switch:
- Five placements decode about 2 points more bursts at the floors for +57% listening CPU, and gave one
  own-grid false lock an hour on c8r50 and c8w50. Off by default.

General:
- `test_generated_tables_current` fails with the defaults: the native tables are today's.
- Wide-grid specs have no recommendation code, so `modes.encode` raises for them. Nothing in the shifter asks.
