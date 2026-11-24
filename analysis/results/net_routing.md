# Routing of key nets

The process has one metal layer, so crossings use poly. Poly over DWELL (transistor channels) is excluded; the rest of a net's poly is wiring and gate leads. Squares = poly area / (4.8 um)^2, i.e. counted as minimum-width (2 lambda) poly.

| Net | Metal (um^2) | Poly wiring (um^2) | ~Poly squares |
|---|---:|---:|---:|
| VDD | 42,970 | 138 | 6 |
| VSS | 41,242 | 415 | 18 |
| PHI (clock to the 4 flip-flops) | 432 | 8,006 | 348 |
| MINIPAD (Q3, driver gate) | 2,327 | 7,361 | 320 |

## Clock path to each flip-flop

Distance along PHI's wiring from its driver to each flip-flop's clock inverter (breadth-first search on a 0.6 um raster of the net's metal and poly).

| Flip-flop | Wiring from the PHI driver (um) | ~Squares at 4.8 um | Data from |
|---|---:|---:|---|
| DFF 0 | 78 | 16 | feedback (D0) |
| DFF 2 | 364 | 76 | DFF 1 |
| DFF 3 | 1,069 | 223 | DFF 2 |
| DFF 1 | 1,389 | 289 | DFF 0 |

## Nets running alongside PHI and MINIPAD

Length of each net's poly edge that faces the other net's poly within 6 um (minimum poly spacing is 4.8 um).

| Net | Neighbour | Parallel length (um) |
|---|---|---:|
| PHI | MINIPAD | 973 |
| PHI | Q1 | 58 |
| PHI | OSC3 | 31 |
| MINIPAD | PHI | 918 |
| MINIPAD | S3_CK | 206 |
| MINIPAD | Q0 | 56 |
