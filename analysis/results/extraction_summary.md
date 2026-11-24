# Netlist extraction summary

Source: `12_ELEC4609_FALL2022/12_ELEC4609_FALL2022.gds`, top cell `top_layout_langsun`, extracted with KLayout 0.30.14

## Cross-check against the tape-out Calibre LVS report

| Object | KLayout (this repo) | Calibre layout | Calibre source | Match |
|---|---:|---:|---:|:---:|
| Ports | 7 | 7 | 7 | yes |
| Nets | 91 | 91 | 91 | yes |
| MN | 91 | 91 | 91 | yes |
| MP | 86 | 86 | 86 | yes |

Calibre overall result: **CORRECT**. Independent re-extraction reproduces the counts.

## Device sizes

| Type | W (um) | L (um) | W/L | Count |
|---|---:|---:|---:|---:|
| MN | 4.8 | 4.8 | 1 | 86 |
| MN | 28.8 | 4.8 | 6 | 1 |
| MN | 220.8 | 4.8 | 46 | 3 |
| MN | 321.6 | 4.8 | 67 | 1 |
| MP | 9.6 | 4.8 | 2 | 84 |
| MP | 38.4 | 4.8 | 8 | 2 |

Pins: C1, C2, MINIPAD, RST, VDD, VSS, Vo
