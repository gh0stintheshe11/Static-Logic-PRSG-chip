# /// script
# requires-python = ">=3.10"
# dependencies = ["klayout>=0.28", "numpy", "matplotlib"]
# ///
"""Regenerate every derived artefact in this repository.

    uv run analysis/run_all.py
or
    pip install -r analysis/requirements.txt && python analysis/run_all.py
"""
import extract_netlist
import gate_level
import make_figures
import scope


def main():
    print("== 1/4 netlist extraction (GDS -> SPICE) ==")
    l2n, devices = extract_netlist.main()
    print("\n== 2/4 gate-level recovery, routing, logic simulation ==")
    circ, reference = gate_level.main(devices, l2n)
    print("\n== 3/4 oscilloscope captures ==")
    res = scope.main(reference)
    print("\n== 4/4 figures ==")
    make_figures.main(circ, res, reference, l2n)


if __name__ == "__main__":
    main()
