# Post-fabrication captures (raw data)

These files were saved by the Tektronix TDS2024C used on the probe station. Folder
names are the original ones ("G12" = group 12). Each folder holds one capture:

- `F00xxCH2.CSV`: the waveform from channel 2, 2500 points. Columns 1-2 hold the
  header (record length, sample interval, vertical and horizontal scale, probe
  attenuation, ...); columns 4-5 hold time [s] and voltage [V].
- `F00xxTEK.JPG`: a screenshot showing the scope date and the automatic
  measurements.
- `F00xxTEK.SET`: the scope setup, which can be recalled on the instrument.

| Folder | File | Scope date | Signal | Settings | Key numbers |
|---|---|---|---|---|---|
| `G12_OutFRI` | F0000 | 19-Nov-22 | Vo, first session | 50 us/div, 100 mV/div | ~0.2 V swing (possibly a 10x probe on a 1x setting), ~112 kHz clock |
| `G12_CLK_SLW` | F0021 | not shown | clock, `C_ext` not recorded | 5 ms/div, 1 V/div | 223 Hz, 41 % duty |
| `G12_OUT` | F0022 | 22-Nov-22 | Vo | 5 ms/div, 1 V/div | ~201 Hz clock, 11 decoded bits |
| `G12_OUT2` | F0023 | 22-Nov-22 | Vo | 25 ms/div, 1 V/div | ~201 Hz clock, 51 decoded bits |
| `G12_CLK10NF` | F0024 | 22-Nov-22 | clock, `C_ext` = 10 nF | 1 ms/div, 1 V/div | 1.30 kHz, 43 % duty |

Notes:

- This is the complete set the course posted for this chip. The course's copies
  are numerically identical. `G12_CLK_SLW/F0021CH2.CSV` was re-saved with
  shorter number formatting at some point, but the values are unchanged.
- The dates are the scope's own clock, which may not have been set to local time.
- The scope's automatic frequency readings on the output screenshots (shown
  with "?") are meaningless for a pseudo-random signal. Use the decoded values in
  [`docs/post_fab_test.md`](../docs/post_fab_test.md).
- The test setup (HP 4155 supplies, LED with series resistor, 10x probes,
  substrate bias per die) is reconstructed from the course notes in
  [`docs/post_fab_test.md`](../docs/post_fab_test.md). The actual supply,
  substrate bias, LED supply and resistor values were not recorded.
