"""Extract a transistor-level netlist from the tape-out GDS with KLayout.

The original Cadence/Calibre setup is not needed: the layer stack is simple
enough to describe here, and the result is cross-checked against the numbers
in the Calibre LVS report that was produced at tape-out.

Outputs (analysis/results/):
  top_layout_langsun.extracted.sp   flat SPICE netlist (MOS3, SOI floating body)
  extraction_summary.md             device statistics + Calibre cross-check
"""
import re
from collections import Counter

import klayout.db as kdb

from common import GDS, LAYERS, LVS_REPORT, RESULTS_DIR, TOP_CELL, ensure_dirs, rel


def extract(gds_path=GDS):
    """Return (l2n, devices). `devices` is a list of plain dicts.

    The netlist (``l2n.netlist()``) is owned by the LayoutToNetlist object, so
    callers must keep ``l2n`` alive while using it.
    """
    ly = kdb.Layout()
    ly.read(str(gds_path))
    top = ly.cell(TOP_CELL)
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(ly, top, []))

    def layer(name):
        return l2n.make_layer(ly.layer(*LAYERS[name]), name)

    dwell, pplus = layer("DWELL"), layer("PPLUS")
    metal, cont, poly = layer("METAL"), layer("CONTACT"), layer("POLY")
    metal_txt = l2n.make_text_layer(ly.layer(*LAYERS["METAL"]), "METAL_TXT")

    gate = poly & dwell
    sd = dwell - poly
    ngate, pgate = gate - pplus, gate & pplus
    nsd, psd = sd - pplus, sd & pplus

    # SOI: no body terminal -> 3-terminal devices, like Calibre's "MN/MP (3 pins)".
    l2n.extract_devices(kdb.DeviceExtractorMOS3Transistor("MN"), {"SD": nsd, "G": ngate, "P": poly})
    l2n.extract_devices(kdb.DeviceExtractorMOS3Transistor("MP"), {"SD": psd, "G": pgate, "P": poly})

    for lyr in (metal, cont, poly, nsd, psd):
        l2n.connect(lyr)
    l2n.connect(metal, cont)
    l2n.connect(cont, poly)
    l2n.connect(cont, nsd)
    l2n.connect(cont, psd)
    l2n.connect(metal, metal_txt)  # pin labels name the nets
    l2n.extract_netlist()

    nl = l2n.netlist()
    nl.combine_devices()
    nl.make_top_level_pins()
    nl.purge()
    nl.flatten()

    circuit = nl.circuit_by_name(TOP_CELL)
    devices = []
    for d in circuit.each_device():
        nets = {t: d.net_for_terminal(t).expanded_name() for t in ("S", "G", "D")}
        pos = d.trans.disp
        devices.append({
            "name": d.expanded_name(),
            "type": d.device_class().name,
            "d": nets["D"], "g": nets["G"], "s": nets["S"],
            "W": round(d.parameter("W"), 3), "L": round(d.parameter("L"), 3),
            "x": round(pos.x, 2), "y": round(pos.y, 2),
        })
    return l2n, devices


def net_region(l2n, net_name, layer_name):
    """Geometry of one net on one layer (top-cell coordinates, DBU).

    Unnamed nets are addressed by their displayed name (e.g. "$24"), which
    `net_by_name` does not find, so match on `expanded_name()` instead.
    """
    circuit = l2n.netlist().circuit_by_name(TOP_CELL)
    net = next(n for n in circuit.each_net() if n.expanded_name() == net_name)
    return l2n.shapes_of_net(net, l2n.layer_by_name(layer_name), True)


def routing_distance(l2n, net_name, start_layer, points_um, res_um=0.6):
    """Distance along the conductors of one net (its METAL and POLY shapes) from
    all of its `start_layer` shapes to each of `points_um`, by breadth-first search
    on a raster of `res_um` pixels. Fine for the Manhattan wiring used here."""
    from collections import deque

    import numpy as np

    dbu = l2n.internal_layout().dbu
    layers = {name: net_region(l2n, net_name, name).merged() for name in ("METAL", "POLY")}
    box = (layers["METAL"] + layers["POLY"]).bbox().to_dtype(dbu)
    x0, y1 = box.left, box.top
    nx, ny = int(box.width() / res_um) + 2, int(box.height() / res_um) + 2

    def raster(region):
        grid = np.zeros((ny, nx), bool)
        for poly in region.each():
            b = poly.bbox().to_dtype(dbu)
            for iy in range(int((y1 - b.top) / res_um), int((y1 - b.bottom) / res_um) + 1):
                for ix in range(int((b.left - x0) / res_um), int((b.right - x0) / res_um) + 1):
                    x, y = x0 + (ix + 0.5) * res_um, y1 - (iy + 0.5) * res_um
                    if poly.inside(kdb.Point(int(round(x / dbu)), int(round(y / dbu)))):
                        grid[iy, ix] = True
        return grid

    grids = {name: raster(r) for name, r in layers.items()}
    conductor = grids["METAL"] | grids["POLY"]
    dist = np.full((ny, nx), np.inf)
    queue = deque()
    for iy, ix in zip(*np.nonzero(grids[start_layer])):
        dist[iy, ix] = 0.0
        queue.append((iy, ix))
    while queue:
        iy, ix = queue.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jy, jx = iy + dy, ix + dx
            if 0 <= jy < ny and 0 <= jx < nx and conductor[jy, jx] and dist[jy, jx] == np.inf:
                dist[jy, jx] = dist[iy, ix] + res_um
                queue.append((jy, jx))
    return [float(dist[int((y1 - y) / res_um), int((x - x0) / res_um)]) for x, y in points_um]


def calibre_initial_counts(report=LVS_REPORT):
    """Parse 'INITIAL NUMBERS OF OBJECTS' from the Calibre LVS report."""
    text = report.read_text()
    block = text.split("INITIAL NUMBERS OF OBJECTS")[1].split("NUMBERS OF OBJECTS AFTER")[0]
    counts = {}
    for key in ("Ports", "Nets"):
        m = re.search(rf"{key}:\s+(\d+)\s+(\d+)", block)
        counts[key] = (int(m.group(1)), int(m.group(2)))
    for m in re.finditer(r"(\d+)\s+(\d+)\s+(MN|MP) \(3 pins\)", block):
        counts[m.group(3)] = (int(m.group(1)), int(m.group(2)))
    m = re.search(r"CELL\s+SUMMARY.*?\n\s*(CORRECT|INCORRECT)\s+" + TOP_CELL, text, re.S)
    counts["result"] = m.group(1) if m else "unknown"
    return counts


def summarize(nl, devices):
    circuit = nl.circuit_by_name(TOP_CELL)
    ours = {
        "Ports": len(list(circuit.each_pin())),
        "Nets": len(list(circuit.each_net())),
        "MN": sum(d["type"] == "MN" for d in devices),
        "MP": sum(d["type"] == "MP" for d in devices),
    }
    cal = calibre_initial_counts()
    lines = ["# Netlist extraction summary", "",
             f"Source: `{rel(GDS)}`, top cell `{TOP_CELL}`, extracted with KLayout "
             f"{kdb.__version__ if hasattr(kdb, '__version__') else ''}".rstrip(), "",
             "## Cross-check against the tape-out Calibre LVS report", "",
             "| Object | KLayout (this repo) | Calibre layout | Calibre source | Match |",
             "|---|---:|---:|---:|:---:|"]
    all_ok = True
    for key in ("Ports", "Nets", "MN", "MP"):
        lay, src = cal[key]
        ok = ours[key] == lay == src
        all_ok &= ok
        lines.append(f"| {key} | {ours[key]} | {lay} | {src} | {'yes' if ok else 'NO'} |")
    lines += ["", f"Calibre overall result: **{cal['result']}**. "
              f"Independent re-extraction {'reproduces' if all_ok else 'does NOT reproduce'} the counts.", "",
              "## Device sizes", "", "| Type | W (um) | L (um) | W/L | Count |", "|---|---:|---:|---:|---:|"]
    for (t, w, l), n in sorted(Counter((d["type"], d["W"], d["L"]) for d in devices).items()):
        lines.append(f"| {t} | {w:g} | {l:g} | {w / l:.3g} | {n} |")
    lines += ["", "Pins: " + ", ".join(sorted(p.name() for p in circuit.each_pin())), ""]
    return "\n".join(lines), all_ok


def main():
    ensure_dirs()
    l2n, devices = extract()
    nl = l2n.netlist()
    writer = kdb.NetlistSpiceWriter()
    writer.use_net_names = True
    sp = RESULTS_DIR / f"{TOP_CELL}.extracted.sp"
    nl.write(str(sp), writer, f"Extracted from {rel(GDS)} with KLayout (flat, MOS3, lengths in um)")
    text, ok = summarize(nl, devices)
    (RESULTS_DIR / "extraction_summary.md").write_text(text)
    print(text)
    print(f"wrote {rel(sp)}")
    if not ok:
        raise SystemExit("extraction does not match the Calibre LVS counts")
    return l2n, devices


if __name__ == "__main__":
    main()
