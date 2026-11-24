# Analysis scripts

Everything in [`results/`](results) and the generated figures in
[`../docs/img/`](../docs/img) can be rebuilt from the tape-out GDS and the raw
scope captures. Cadence, Calibre and the PDK are not needed.

```sh
uv run analysis/run_all.py                 # dependencies come from the script header (PEP 723)
# or
pip install -r analysis/requirements.txt
python analysis/run_all.py
```

Tested with Python 3.13 and 3.14, KLayout 0.30, NumPy 2.5 and Matplotlib 3.11.
A full run takes a few seconds.

| Script | Input | Output |
|---|---|---|
| `extract_netlist.py` | `12_ELEC4609_FALL2022/*.gds`, LVS report | `results/top_layout_langsun.extracted.sp`, `results/extraction_summary.md` |
| `gate_level.py` | extracted devices and net geometry | `results/gate_level_netlist.txt`, `results/logic_simulation.md`, `results/net_routing.md` |
| `scope.py` | `post_fab_test/*/F*CH2.CSV` | `results/post_fab_summary.md` |
| `make_figures.py` | all of the above, `G12C1.jpg` | `docs/img/{layout_*,sim_timing,meas_*,art}.png`, `docs/img/die_vs_layout.jpg` |
| `run_all.py` | | runs the four steps in order |
| `common.py` | | paths, lambda, GDS layer map |

Each script also runs on its own (`python analysis/scope.py`, ...).

## Method notes

- **Layer map** (`common.py`): recovered by matching per-layer shape counts
  with the Calibre DRC summary. See [`docs/verification.md`](../docs/verification.md#2-independent-re-extraction).
- **Extraction** uses KLayout's LVS engine with 3-terminal MOS devices (SOI).
  `extract_netlist.py` exits with an error if the device, net or port counts
  differ from the Calibre LVS report.
- **Gate recognition** handles INV, NAND2 and NOR2, which is everything in this
  design. Nets are named by tracing the structure (oscillator -> PHI ->
  flip-flops -> feedback), so the names do not depend on the extractor's
  auto-generated ones.
- **Logic simulation** is unit delay, with PHI and RST as inputs. The oscillator
  is analog and is replaced by an ideal clock.
- **Net routing** (`gate_level.routing_report`) compares the metal area and the
  poly-wiring area of VDD, VSS, PHI and MINIPAD. Poly over DWELL is a channel and
  is excluded.
- **Scope decoding** (`scope.decode_phased_output`): clusters the samples into
  three levels, drops segments shorter than 0.4 ms (glitches), and emits one bit
  per bit phase. `scope.lfsr_consistency` then checks the bits against the
  register's recurrence.
