# Cadence Virtuoso libraries

The two library folders at the repository root are OpenAccess (OA 22.43)
libraries. They reference the PDK library `CuSOiPDk_DEVICES` (Carleton
University SOI PDK, **not included**) and `analogLib` (used by the testbenches).

| Library | Status |
|---|---|
| [`Libv2_langsun_4609fall2022`](../Libv2_langsun_4609fall2022) | **Tape-out version.** [`12_ELEC4609_FALL2022.gds`](../12_ELEC4609_FALL2022/README.md) was streamed from this library; the GDS library name matches. |
| [`Libv1_langsun_4609fall2022`](../Libv1_langsun_4609fall2022) | Earlier snapshot. It differs from Libv2 only in `PRSG3_layout_langsun` and `top_layout_langsun` (the final routing edits). Every other cell differs only in the embedded library name. |

To open the library in Virtuoso, add it to `cds.lib` together with the PDK:

```
DEFINE Libv2_langsun_4609fall2022 <repo>/Libv2_langsun_4609fall2022
```

Without Virtuoso, use the GDS and the netlists that
[`analysis/`](../analysis/README.md) recovers from it.

**Library name history.** The cellviews still reference earlier names of the
same library, showing how it was copied and renamed during the term:
`CuFab` -> `CuFab_LS` -> `CuFab_LangSun` -> `Lib_langsun_4609fall2022` -> `Libv1/Libv2_langsun_4609fall2022`.

## Cell inventory (61 cells)

### Layout: in the tape-out GDS (15)

| Cell | Role |
|---|---|
| `top_layout_langsun` | chip top level (LVS'd against `top_langsun`) |
| `SPRSG_Frame_langsun` | 230 x 240 lambda frame with the six pads |
| `PRSG3_layout_langsun` | core: clock generator + XNOR + 4 flip-flops |
| `DFlipFlop5_layout_langsun`, `DFlipFlop6_layout_langsun` | static master-slave DFF, mirrored pair |
| `NAND6_layout_langsun`, `NAND7_layout_langsun` | NAND2 cells used in the DFFs and the XNOR |
| `inverter2_layout_langsun` | DFF clock inverter |
| `inverter3_layout_langsun` | oscillator inverter |
| `XNOR3_layout_langsun` | XNOR (4 x NAND2) + reset NOR |
| `NOR_layout_langsun` | NOR2 |
| `clk_layout_langsun` | RC oscillator (4 inverters + M1) |
| `input_protection_layout_langsun` | protection for C1 and C2 |
| `input_protection3_layout_langsun` | protection for RST |
| `outputBuffer_layout_langsun` | open-drain LED driver |

### Layout: earlier iterations, not used (17)

`art_layout_langsun`, `DFlipFlop_layout_langsun`, `DFlipFlop2/3/4_layout_langsun`,
`input_protection2_layout_langsun`, `inverter_layout_langsun`, `NAND_layout_langsun`,
`NAND2/3/4/5_layout_langsun`, `outputBuffer2_layout_langsun`, `PRSG_layout_langsun`,
`PRSG2_layout_langsun`, `XNOR_layout_langsun`, `XNOR2_layout_langsun`.

The ART logo in the GDS was drawn directly in `top_layout_langsun`, not through
`art_layout_langsun`.

### Schematics (15)

| Cell | Role |
|---|---|
| `top_langsun` | chip top level, the LVS source; references `clk_generator_langsun`, `C1C2_protection_langsun`, `PRSG_Rst_langsun`, `output_buffer_langsun` |
| `PRSG_Rst_langsun` | register used on the chip: DFFs + `XNOR_langsun` (XNOR with RST) |
| `DFlipFlop_langsun` | static master-slave DFF (`NAND_langsun`, `inverter_langsun`) |
| `XNOR_langsun` | XNOR from NAND2s + reset NOR (`NAND_langsun`, `NOR_langsun`) |
| `clk_generator_langsun` | RC oscillator |
| `C1C2_protection_langsun` | pad protection (NMOS clamps + resistors) |
| `output_buffer_langsun` | open-drain driver |
| `inverter_langsun`, `NAND_langsun`, `NOR_langsun` | gates |
| `PRSG_langsun` | earlier register variant (also references a 5-input NOR, `NOR_5in_langsun`) |
| `NOR_5in_langsun` | 5-input NOR |
| `XNOR_v2_langsun` | transistor-level XNOR variant |
| `clk_generator_test_langsun` | oscillator variant |
| `output_buffer2_langsun` | driver variant (schematic only, no symbol) |

### Testbenches (14, schematic only, analogLib sources)

`C1C2_protection_testbench_langsun`, `clk_testbench_langsun`, `DFlipFlop_testbench_langsun`,
`inverter_testbench_langsun`, `maintest_langsun` (oscillator + register),
`NAND_testbench_langsun`, `NOR_5in_testbench_langsun`, `NOR_testbench_langsun`,
`output_buffer_testbench_langsun`, `PRSG_Rst_testbench_langsun`, `PRSG_testbench_langsun`,
`top_testbench_langsun`, `XNOR_testbench_langsun`, `XNOR_v2_testbench_langsun`.

No simulation results (waveform databases) were kept.
