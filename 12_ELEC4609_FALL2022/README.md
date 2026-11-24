# Tape-out package

These are the files submitted for fabrication. The folder is named after the
submission: group 12, ELEC 4609, Fall 2022.

| File | Content |
|---|---|
| `12_ELEC4609_FALL2022.gds` | Final layout (GDSII): library `Libv2_langsun_4609fall2022`, top cell `top_layout_langsun`, 15 cells, 552 x 576 um, database unit 0.5 nm |
| `top_layout_langsun.drc.summary` | Calibre DRC summary, 2022-10-15 17:34: 36 rule checks, **0 results** |
| `top_layout_langsun.lvs.report` | Calibre LVS report, 2022-10-15 17:34: **CORRECT** against schematic `top_langsun` |
| `Libv2_langsun_4609fall2022.tar.gz` | The Cadence library as submitted |

**Timeline** (from the file timestamps in the archive and the report headers):

- 17:04-17:05: most cells saved
- 17:10: last edit of `PRSG3_layout_langsun`
- 17:33: last edit of `top_layout_langsun`
- 17:34: DRC and LVS run

After sign-off, the mask data went to the University of Alberta for mask making.
The chips were then fabricated at Carleton and came back for testing in the
second half of November 2022 ([test results](../docs/post_fab_test.md)).

The archive is identical to the [`Libv2_langsun_4609fall2022`](../Libv2_langsun_4609fall2022)
folder at the repository root ([inventory](../docs/cadence_libraries.md)) except
for `top_testbench_langsun`, a simulation testbench that was edited after
submission and is not part of the chip.

How these files were checked and re-extracted: [`docs/verification.md`](../docs/verification.md).

SHA-256:

```
7a4ca0784b76c560b440aff77b8bdc7588b24395e7e9b0bb776b7d032ec3891d  12_ELEC4609_FALL2022.gds
cb02221410285abbb23be4f81863ae6291e39e530fc0abaeab0e2eddf7a4f5e2  Libv2_langsun_4609fall2022.tar.gz
e1a8b55d8cc9e2ba24ba258a17fdfcc98af68089dd458d3433f61d21ea36733b  top_layout_langsun.drc.summary
a6710967aab6f4368cf2791a40458bae51369a797f613009d76ce7e83bb73aa5  top_layout_langsun.lvs.report
```
