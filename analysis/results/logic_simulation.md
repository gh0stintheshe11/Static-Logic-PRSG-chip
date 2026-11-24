# Logic simulation of the recovered netlist

- Register: 4 static master-slave D flip-flops (each 8 x NAND2 + 2 x INV), positive-edge triggered.
- Feedback: D0 = NOR(XOR(Q0, Q3), RST) = XNOR(Q0, Q3) when RST = 0.
- Output: MINIPAD = Q3 drives the open-drain LED driver (LED on when Q3 = 1).

## Output after releasing RST (5 reset cycles first)

```
Q3/MINIPAD: 0001010011011100001010011011100001
```

Repeats every **15** clock cycles; per period: 7 ones, 8 zeros.

## Next-state table (all 16 register states, Q0 Q1 Q2 Q3)

| state | next (RST=0) | next (RST=1) |
|---|---|---|
| 0000 | 1000 | 0000 |
| 0001 | 0000 | 0000 |
| 0010 | 1001 | 0001 |
| 0011 | 0001 | 0001 |
| 0100 | 1010 | 0010 |
| 0101 | 0010 | 0010 |
| 0110 | 1011 | 0011 |
| 0111 | 0011 | 0011 |
| 1000 | 0100 | 0100 |
| 1001 | 1100 | 0100 |
| 1010 | 0101 | 0101 |
| 1011 | 1101 | 0101 |
| 1100 | 0110 | 0110 |
| 1101 | 1110 | 0110 |
| 1110 | 0111 | 0111 |
| 1111 | 1111 | 0111 |

- With RST = 0 the 15 states starting at 0000 form a single cycle of length 15 (maximal length for 4 bits: 2^4 - 1 = 15).
- Lock-up state(s) (next = itself with RST = 0): 1111. Asserting RST shifts a 0 into Q0, which leaves the lock-up state.
