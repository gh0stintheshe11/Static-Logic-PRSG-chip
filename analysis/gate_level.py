"""Recover the gate-level circuit from the extracted transistors and simulate it.

1. Group transistors into static CMOS gates (INV / NAND2 / NOR2).
2. Name nets by tracing the structure (RC clock generator -> PHI, four
   master-slave flip-flops, XNOR + reset feedback) instead of relying on the
   extractor's auto-generated net names.
3. Unit-delay logic simulation of the digital core:
   - reference output sequence after reset,
   - exhaustive next-state table of the 4-bit register (all 16 states).

Outputs (analysis/results/):
  gate_level_netlist.txt   human-readable recovered netlist
  logic_simulation.md      reference sequence + state graph
"""
from collections import defaultdict
from itertools import combinations

from common import GDS, RESULTS_DIR, TOP_CELL, ensure_dirs, rel

VDD, VSS = "VDD", "VSS"


# ----------------------------------------------------------------------------
# 1. gate recognition
# ----------------------------------------------------------------------------
def _between(dev, a, b):
    return {dev["d"], dev["s"]} == {a, b}


def _other(dev, net):
    return dev["s"] if dev["d"] == net else dev["d"]


def recognize(devices):
    """Return (gates, leftover_devices); gate = {kind, out, ins, devs}."""
    by_net = defaultdict(list)
    for i, d in enumerate(devices):
        by_net[d["d"]].append(i)
        by_net[d["s"]].append(i)
    used, gates = set(), []

    def to_rail(out, rail, typ):
        return [i for i in by_net[out] if i not in used
                and devices[i]["type"] == typ and _between(devices[i], out, rail)]

    def series(out, rail, typ):
        """Pairs of `typ` devices in series out -> private mid node -> rail."""
        pairs = []
        for i1 in by_net[out]:
            d1 = devices[i1]
            if i1 in used or d1["type"] != typ or rail in (d1["d"], d1["s"]):
                continue
            mid = _other(d1, out)
            if mid in (VDD, VSS) or len(by_net[mid]) != 2:
                continue
            i2 = next(i for i in by_net[mid] if i != i1)
            if i2 not in used and devices[i2]["type"] == typ and _between(devices[i2], mid, rail):
                pairs.append((i1, i2))
        return pairs

    nets = sorted(set(by_net) - {VDD, VSS})
    # (kind, parallel network type/rail, series network type/rail)
    for kind, ptyp, prail, styp, srail in (("NAND2", "MP", VDD, "MN", VSS),
                                           ("NOR2", "MN", VSS, "MP", VDD)):
        for out in nets:
            for i1, i2 in series(out, srail, styp):
                ins = sorted((devices[i1]["g"], devices[i2]["g"]))
                par = to_rail(out, prail, ptyp)
                match = next(((a, b) for a, b in combinations(par, 2)
                              if sorted((devices[a]["g"], devices[b]["g"])) == ins), None)
                if match:
                    gates.append({"kind": kind, "out": out, "ins": ins, "devs": [*match, i1, i2]})
                    used.update([*match, i1, i2])
                    break
    for out in nets:
        for p in to_rail(out, VDD, "MP"):
            n = next((n for n in to_rail(out, VSS, "MN") if devices[n]["g"] == devices[p]["g"]), None)
            if n is not None:
                gates.append({"kind": "INV", "out": out, "ins": [devices[p]["g"]], "devs": [p, n]})
                used.update([p, n])
                break
    leftovers = [d for i, d in enumerate(devices) if i not in used]
    return gates, leftovers


# ----------------------------------------------------------------------------
# 2. structural naming
# ----------------------------------------------------------------------------
class Circuit:
    def __init__(self, devices):
        self.devices = devices
        self.gates, self.leftovers = recognize(devices)
        self.names = {}
        self.stages = []     # per flip-flop: dict of raw net names
        self.groups = {}     # section title -> list of gates
        self._trace()

    def _one(self, kind, ins=None, has=(), lacks=()):
        found = [g for g in self.gates if g["kind"] == kind
                 and (ins is None or sorted(g["ins"]) == sorted(ins))
                 and all(n in g["ins"] for n in has) and not any(n in g["ins"] for n in lacks)]
        if len(found) != 1:
            raise RuntimeError(f"expected one {kind} ins={ins} has={has} lacks={lacks}, got {len(found)}")
        return found[0]

    def _trace(self):
        inv = lambda net: self._one("INV", ins=[net])
        # RC oscillator: C1 -> INV -> OSC1 -> INV -> C2 -> INV -> OSC3 -> INV -> PHI
        g1 = inv("C1")
        g2 = inv(g1["out"])
        assert g2["out"] == "C2", "oscillator topology mismatch"
        g3 = inv("C2")
        g4 = inv(g3["out"])
        self.osc1, self.osc3, self.phi = g1["out"], g3["out"], g4["out"]
        self.names.update({self.osc1: "OSC1", self.osc3: "OSC3", self.phi: "PHI"})
        self.groups["RC clock generator (Fig. 4 of the spec)"] = [g1, g2, g3, g4]
        self.osc_gates = [g1, g2, g3, g4]

        # feedback: D0 = NOR(XOR(Qa, Qb), RST)
        nor = self._one("NOR2", has=["RST"])
        self.d0 = nor["out"]
        self.xor = next(n for n in nor["ins"] if n != "RST")
        xor_g = next(g for g in self.gates if g["kind"] == "NAND2" and g["out"] == self.xor)
        x2, x3 = (next(g for g in self.gates if g["out"] == n) for n in xor_g["ins"])
        x1_net = (set(x2["ins"]) & set(x3["ins"])).pop()
        x1 = next(g for g in self.gates if g["out"] == x1_net)
        self.taps = sorted(x1["ins"])
        self.names.update({self.d0: "D0", self.xor: "XOR", x1["out"]: "X1",
                           x2["out"]: "X2", x3["out"]: "X3"})

        # flip-flop chain starting at D0
        ckbs = {g["out"] for g in self.gates if g["kind"] == "INV" and g["ins"] == [self.phi]}
        d = self.d0
        while True:
            st, gl = self._trace_dff(d, ckbs)
            k = len(self.stages)
            self.stages.append(st)
            for key, net in st.items():
                if net not in ("MINIPAD",) and key != "D":
                    self.names[net] = f"Q{k}" if key == "Q" else f"S{k}_{key}"
            self.groups[f"Flip-flop {k}: D={self.name(st['D'])}, Q={self.name(st['Q'])}"] = gl
            d = st["Q"]
            if d == "MINIPAD" or len(self.stages) > 8:
                break
        self.groups["Feedback: D0 = NOR(XOR(tap_a, tap_b), RST)"] = [x1, x2, x3, xor_g, nor]

    def _trace_dff(self, d, ckbs):
        nand = lambda **kw: self._one("NAND2", **kw)
        # master input gate: NAND(D, CKB) where CKB is a local inverted clock
        m1 = next(g for g in self.gates if g["kind"] == "NAND2" and d in g["ins"]
                  and any(n in ckbs for n in g["ins"] if n != d))
        ckb = next(n for n in m1["ins"] if n != d)
        m2 = nand(ins=[m1["out"], ckb])
        mq = nand(has=[m1["out"]], lacks=[ckb])
        mqb = nand(ins=[mq["out"], m2["out"]])
        ck = self._one("INV", ins=[ckb])
        s1 = nand(ins=[mq["out"], ck["out"]])
        s2 = nand(ins=[s1["out"], ck["out"]])
        q = nand(has=[s1["out"]], lacks=[ck["out"]])
        qb = nand(ins=[q["out"], s2["out"]])
        assert mqb["out"] in mq["ins"] and qb["out"] in q["ins"], "latch cross-coupling mismatch"
        st = {"D": d, "CKB": ckb, "CK": ck["out"], "M1": m1["out"], "M2": m2["out"], "MQ": mq["out"],
              "MQB": mqb["out"], "S1": s1["out"], "S2": s2["out"], "Q": q["out"], "QB": qb["out"]}
        ckb_inv = next(g for g in self.gates if g["kind"] == "INV" and g["out"] == ckb)
        return st, [ckb_inv, ck, m1, m2, mq, mqb, s1, s2, q, qb]

    def name(self, net):
        return self.names.get(net, net)

    # ---- reporting ---------------------------------------------------------
    def netlist_text(self):
        def sizes(g):
            return ", ".join(f'{self.devices[i]["type"][1]} {self.devices[i]["W"]:g}/{self.devices[i]["L"]:g}'
                             for i in g["devs"])
        last = len(self.stages) - 1
        tap_names = [f"Q{last} (MINIPAD)" if t == "MINIPAD" else self.name(t) for t in self.taps]
        lines = [f"# Gate-level netlist recovered from {rel(GDS)}",
                 "# (KLayout extraction -> static-CMOS gate recognition -> structural naming)",
                 "# Sizes are W/L in um per transistor (P = PMOS, N = NMOS).",
                 f"# Register: {len(self.stages)} stages, feedback taps = {', '.join(tap_names)}, "
                 "output = last stage Q (MINIPAD).", ""]
        for title, gl in self.groups.items():
            lines.append(f"## {title}")
            for g in gl:
                ins = ", ".join(self.name(n) for n in g["ins"])
                lines.append(f"  {self.name(g['out']):<8} = {g['kind']:<5}({ins:<18})  [{sizes(g)}]")
            lines.append("")
        lines.append("## Discrete transistors (not part of a logic gate)")
        role = {}
        for d in self.leftovers:
            terms = {d["d"], d["s"]}
            if d["g"] == "MINIPAD" and "Vo" in terms:
                role[d["name"]] = "open-drain LED driver (gate = MINIPAD = Q3)"
            elif d["g"] == VSS and VSS in terms:
                pad = (terms - {VSS}).pop()
                role[d["name"]] = f"grounded-gate NMOS input protection on pad {pad}"
            elif d["g"] == VDD and terms == {"C1", self.osc3}:
                role[d["name"]] = "oscillator feedback resistor M1 (gate = VDD), C1 <-> OSC3"
        for d in self.leftovers:
            lines.append(f"  {d['type']} D={self.name(d['d']):<6} G={self.name(d['g']):<8} S={self.name(d['s']):<6} "
                         f"W/L={d['W']:g}/{d['L']:g}  at ({d['x']:g}, {d['y']:g})  {role.get(d['name'], '?')}")
        return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# 3. logic simulation
# ----------------------------------------------------------------------------
def _eval(kind, vals):
    if kind == "INV":
        return 1 - vals[0]
    if kind == "NAND2":
        return 0 if all(vals) else 1
    return 0 if any(vals) else 1  # NOR2


class LogicSim:
    """Unit-delay simulation of the digital core with PHI and RST as inputs.

    The four oscillator inverters are removed (PHI is driven directly, which is
    equivalent to injecting an external clock at pad C2).
    """

    def __init__(self, circ: Circuit):
        self.c = circ
        self.gates = [g for g in circ.gates if g not in circ.osc_gates]
        self.val = defaultdict(int)
        self.val["RST"], self.val[circ.phi] = 1, 0
        self._settle_async()  # Gauss-Seidel: resolves the symmetric power-up state of the latches

    def _settle_async(self):
        for _ in range(200):
            changed = False
            for g in self.gates:
                v = _eval(g["kind"], [self.val[n] for n in g["ins"]])
                if self.val[g["out"]] != v:
                    self.val[g["out"]], changed = v, True
            if not changed:
                return
        raise RuntimeError("did not settle")

    def _settle_sync(self):
        """All gates update together each step (unit delay): keeps the CKB -> CK
        ordering of the local clock inverters, i.e. master closes before slave opens."""
        for _ in range(200):
            new = {g["out"]: _eval(g["kind"], [self.val[n] for n in g["ins"]]) for g in self.gates}
            if all(self.val[k] == v for k, v in new.items()):
                return
            self.val.update(new)
        raise RuntimeError("oscillation")

    def state(self):
        return tuple(self.val[st["Q"]] for st in self.c.stages)

    def set_state(self, bits):
        """Force the slave latches (PHI = 0, slaves opaque) to the given Q values."""
        self.val[self.c.phi] = 0
        self._settle_async()
        for b, st in zip(bits, self.c.stages):
            self.val[st["Q"]], self.val[st["QB"]] = b, 1 - b
        self._settle_async()
        assert self.state() == tuple(bits)

    def clock(self, rst):
        """One full clock period: PHI low (masters sample D), then rising edge."""
        self.val["RST"] = rst
        self.val[self.c.phi] = 0
        self._settle_sync()
        self.val[self.c.phi] = 1
        self._settle_sync()
        return self.state()


def reference_sequence(circ, n_reset=5, n_run=34):
    sim = LogicSim(circ)
    trace = []
    for k in range(n_reset + n_run):
        rst = 1 if k < n_reset else 0
        trace.append((rst, sim.clock(rst)))
    return trace


def state_graph(circ):
    nxt = {}
    for rst in (0, 1):
        for s in range(16):
            bits = tuple((s >> (3 - i)) & 1 for i in range(4))
            sim = LogicSim(circ)
            sim.set_state(bits)
            nxt[(rst, bits)] = sim.clock(rst)
    return nxt


def lfsr_report(circ):
    trace = reference_sequence(circ)
    out = "".join(str(s[-1]) for rst, s in trace if rst == 0)
    period = next(p for p in range(1, len(out)) if all(out[i] == out[i + p] for i in range(len(out) - p)))
    nxt = state_graph(circ)
    fmt = lambda b: "".join(map(str, b))
    # follow the cycle from 0000 with RST = 0
    cyc, s = [], (0, 0, 0, 0)
    while s not in cyc:
        cyc.append(s)
        s = nxt[(0, s)]
    lock = [b for (r, b), n in nxt.items() if r == 0 and n == b]
    tap_stage = [next(k for k, st in enumerate(circ.stages) if st["Q"] == t) for t in circ.taps]
    lines = ["# Logic simulation of the recovered netlist", "",
             f"- Register: {len(circ.stages)} static master-slave D flip-flops "
             f"(each 8 x NAND2 + 2 x INV), positive-edge triggered.",
             f"- Feedback: D0 = NOR(XOR(Q{tap_stage[0]}, Q{tap_stage[1]}), RST) "
             f"= XNOR(Q{tap_stage[0]}, Q{tap_stage[1]}) when RST = 0.",
             "- Output: MINIPAD = Q3 drives the open-drain LED driver (LED on when Q3 = 1).", "",
             "## Output after releasing RST (5 reset cycles first)", "",
             "```", f"Q3/MINIPAD: {out}", "```", "",
             f"Repeats every **{period}** clock cycles; per period: {out[:period].count('1')} ones, "
             f"{out[:period].count('0')} zeros.", "",
             "## Next-state table (all 16 register states, Q0 Q1 Q2 Q3)", "",
             "| state | next (RST=0) | next (RST=1) |", "|---|---|---|"]
    for s in range(16):
        b = tuple((s >> (3 - i)) & 1 for i in range(4))
        lines.append(f"| {fmt(b)} | {fmt(nxt[(0, b)])} | {fmt(nxt[(1, b)])} |")
    lines += ["", f"- With RST = 0 the 15 states starting at 0000 form a single cycle of length {len(cyc)} "
              f"(maximal length for 4 bits: 2^4 - 1 = 15).",
              f"- Lock-up state(s) (next = itself with RST = 0): {', '.join(fmt(b) for b in lock)}. "
              "Asserting RST shifts a 0 into Q0, which leaves the lock-up state.", ""]
    return "\n".join(lines), out[:period], trace


def routing_report(l2n, circ, min_width_um=4.8):
    """How much of each key net is metal and how much is poly interconnect.

    Poly over DWELL is a transistor channel and is excluded; everything else
    on the net's poly is wiring (cross-unders and gate leads)."""
    from extract_netlist import net_region
    dbu = l2n.internal_layout().dbu
    dwell = l2n.layer_by_name("DWELL")
    rows = [("VDD", "VDD"), ("VSS", "VSS"), ("PHI (clock to the 4 flip-flops)", circ.phi),
            ("MINIPAD (Q3, driver gate)", "MINIPAD")]
    lines = ["# Routing of key nets", "",
             "The process has one metal layer, so crossings use poly. Poly over DWELL "
             "(transistor channels) is excluded; the rest of a net's poly is wiring and gate leads. "
             f"Squares = poly area / ({min_width_um} um)^2, i.e. counted as minimum-width (2 lambda) poly.", "",
             "| Net | Metal (um^2) | Poly wiring (um^2) | ~Poly squares |", "|---|---:|---:|---:|"]
    for label, raw in rows:
        m = net_region(l2n, raw, "METAL").area() * dbu * dbu
        p = (net_region(l2n, raw, "POLY") - dwell).area() * dbu * dbu
        lines.append(f"| {label} | {m:,.0f} | {p:,.0f} | {p / min_width_um ** 2:,.0f} |")

    # PHI: distance along the wiring from the driver (its metal stub at the clock
    # generator) to the clock inverter (CKB) of each flip-flop
    from extract_netlist import routing_distance
    sinks = []
    for k, st in enumerate(circ.stages):
        inv = next(g for g in circ.gates if g["kind"] == "INV" and g["out"] == st["CKB"])
        d = circ.devices[inv["devs"][0]]
        sinks.append((k, st["D"], (d["x"], d["y"])))
    dist = routing_distance(l2n, circ.phi, "METAL", [p for _, _, p in sinks])
    fed_by = {st["Q"]: k for k, st in enumerate(circ.stages)}
    lines += ["", "## Clock path to each flip-flop", "",
              "Distance along PHI's wiring from its driver to each flip-flop's clock inverter "
              "(breadth-first search on a 0.6 um raster of the net's metal and poly).", "",
              "| Flip-flop | Wiring from the PHI driver (um) | ~Squares at 4.8 um | Data from |",
              "|---|---:|---:|---|"]
    for (k, d_net, _), dd in sorted(zip(sinks, dist), key=lambda t: t[1]):
        src = f"DFF {fed_by[d_net]}" if d_net in fed_by else "feedback (D0)"
        lines.append(f"| DFF {k} | {dd:,.0f} | {dd / min_width_um:,.0f} | {src} |")

    # long parallel runs: which nets run next to PHI / MINIPAD at (near-)minimum spacing
    circuit = l2n.netlist().circuit_by_name(TOP_CELL)
    nets = [n.expanded_name() for n in circuit.each_net()]
    space = int(round(1.25 * min_width_um / dbu))   # 6 um: minimum poly spacing is 4.8 um
    lines += ["", "## Nets running alongside PHI and MINIPAD", "",
              f"Length of each net's poly edge that faces the other net's poly within "
              f"{1.25 * min_width_um:g} um (minimum poly spacing is {min_width_um:g} um).", "",
              "| Net | Neighbour | Parallel length (um) |", "|---|---|---:|"]
    for label, raw in (("PHI", circ.phi), ("MINIPAD", "MINIPAD")):
        mine = net_region(l2n, raw, "POLY").merged()
        found = []
        for other in nets:
            if other == raw:
                continue
            pairs = mine.separation_check(net_region(l2n, other, "POLY").merged(), space)
            length = sum(e.first.length() for e in pairs.each()) * dbu
            if length > 0:
                found.append((length, other))
        for length, other in sorted(found, reverse=True)[:3]:
            lines.append(f"| {label} | {circ.name(other)} | {length:,.0f} |")
    return "\n".join(lines) + "\n"


def main(devices=None, l2n=None):
    ensure_dirs()
    if devices is None:
        from extract_netlist import extract
        l2n, devices = extract()
    circ = Circuit(devices)
    (RESULTS_DIR / "gate_level_netlist.txt").write_text(circ.netlist_text())
    text, seq, _ = lfsr_report(circ)
    (RESULTS_DIR / "logic_simulation.md").write_text(text)
    if l2n is not None:
        (RESULTS_DIR / "net_routing.md").write_text(routing_report(l2n, circ))
    kinds = defaultdict(int)
    for g in circ.gates:
        kinds[g["kind"]] += 1
    print(f"gates: {dict(kinds)}, discrete devices: {len(circ.leftovers)}, "
          f"stages: {len(circ.stages)}, taps: {[circ.name(t) for t in circ.taps]}")
    print(f"reference Q3 sequence (one period): {seq}")
    return circ, seq


if __name__ == "__main__":
    main()
