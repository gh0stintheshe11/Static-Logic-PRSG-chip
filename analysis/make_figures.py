"""Generate the figures used in README.md and docs/ (written to docs/img/)."""
import matplotlib

matplotlib.use("Agg")
import klayout.db as kdb
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MPath

import scope
from common import ART_DATATYPE, DIE_PHOTO, GDS, IMG_DIR, LAYERS, PAD_TEXT, TOP_CELL, ensure_dirs, rel
from gate_level import Circuit, LogicSim

plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "figure.dpi": 100})

LAYER_STYLE = [  # drawing order, colour, alpha
    ("NWELL", "#f3e08a", 0.35), ("PPLUS", "#f4a259", 0.30), ("DWELL", "#43a047", 0.55),
    ("POLY", "#e53935", 0.65), ("METAL", "#1e88e5", 0.40), ("CONTACT", "#111111", 0.90),
]
ART_COLOR = "#c9a227"


# ----------------------------------------------------------------------------
# layout helpers
# ----------------------------------------------------------------------------
class Chip:
    def __init__(self):
        self.ly = kdb.Layout()
        self.ly.read(str(GDS))
        self.top = self.ly.cell(TOP_CELL)
        self.dbu = self.ly.dbu

    def region(self, layer, datatype):
        li = self.ly.find_layer(layer, datatype)
        return kdb.Region() if li is None else kdb.Region(self.top.begin_shapes_rec(li)).merged()

    def _patch(self, ax, region, color, alpha):
        verts, codes = [], []
        for poly in region.each():
            dp = poly.to_dtype(self.dbu)
            contours = [list(dp.each_point_hull())] + [list(dp.each_point_hole(h)) for h in range(dp.holes())]
            for c in contours:
                pts = [(p.x, p.y) for p in c]
                verts += pts + [pts[0]]
                codes += [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 1) + [MPath.CLOSEPOLY]
        if verts:
            ax.add_patch(PathPatch(MPath(verts, codes), fc=color, ec="none", alpha=alpha))

    def draw(self, ax, box=None, art=True, fade=1.0):
        for name, color, alpha in LAYER_STYLE:
            self._patch(ax, self.region(*LAYERS[name]), color, alpha * fade)
        if art:
            r = kdb.Region()
            for layer in (1, 5, 7):
                r += self.region(layer, ART_DATATYPE)
            self._patch(ax, r.merged(), ART_COLOR, 0.9 * fade)
        b = box or self.bbox()
        ax.set_xlim(b[0], b[2])
        ax.set_ylim(b[1], b[3])
        ax.set_aspect("equal")
        ax.set_xlabel("x [um]")
        ax.set_ylabel("y [um]")

    def bbox(self):
        b = self.top.dbbox()
        return (b.left, b.bottom, b.right, b.top)

    def instances(self):
        """All instances with their bbox in top-level coordinates."""
        out = []
        it = self.top.begin_instances_rec()
        while not it.at_end():
            cell = it.inst_cell()
            b = cell.dbbox().transformed(it.dtrans() * it.inst_dtrans())
            out.append({"cell": cell.name, "depth": len(it.path()),
                        "box": (b.left, b.bottom, b.right, b.top)})
            it.next()
        return out

    def pads(self):
        """Pad name -> centre, from the frame cell's pad texts."""
        li = self.ly.find_layer(*PAD_TEXT)
        out = {}
        it = self.top.begin_shapes_rec(li)
        while not it.at_end():
            if it.shape().is_text():
                t = it.shape().text.transformed(it.trans())
                out[t.string] = (t.x * self.dbu, t.y * self.dbu)
            it.next()
        return out


def inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def outline(ax, box, color, label=None, lw=1.6, fontsize=9, loc="tl", **kw):
    ax.add_patch(Rectangle((box[0], box[1]), box[2] - box[0], box[3] - box[1],
                           fill=False, ec=color, lw=lw, **kw))
    if label:
        x, ha = (box[0] + 2, "left") if "l" in loc else (box[2] - 2, "right")
        y, va = (box[3] - 2, "top") if "t" in loc else (box[1] + 2, "bottom")
        ax.text(x, y, label, color=color, fontsize=fontsize, ha=ha, va=va, fontweight="bold",
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.0))


def stage_of_instance(circ, insts):
    """Map flip-flop instances to register stages via the position of the gate driving Q."""
    dffs = [i for i in insts if i["cell"].startswith("DFlipFlop")]
    mapping = {}
    for k, st in enumerate(circ.stages):
        g = next(g for g in circ.gates if g["out"] == st["Q"])
        d = circ.devices[g["devs"][0]]
        inst = next(i for i in dffs if inside(i["box"], d["x"], d["y"]))
        mapping[id(inst)] = k
    return mapping


# ----------------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------------
def fig_floorplan(chip, circ):
    insts = chip.instances()
    st = stage_of_instance(circ, insts)
    fig, axs = plt.subplots(1, 2, figsize=(15, 7.6))
    for ax in axs:
        chip.draw(ax)
    axs[0].set_title(f"Layout ({rel(GDS)}), 552 x 576 um")
    ax = axs[1]
    ax.set_title("Floorplan")
    names = {"clk_layout_langsun": ("RC clock\ngenerator", "#6a1b9a", "tl"),
             "XNOR3_layout_langsun": ("XNOR + RST NOR\n(feedback)", "#ad1457", "tr"),
             "input_protection_layout_langsun": ("C1/C2\nprotection", "#00695c", "bl"),
             "input_protection3_layout_langsun": ("RST\nprot.", "#00695c", "bl"),
             "outputBuffer_layout_langsun": ("LED\ndriver", "#e65100", "bl")}
    for i in insts:
        if i["cell"] in names:
            label, color, loc = names[i["cell"]]
            outline(ax, i["box"], color, label, loc=loc)
        elif id(i) in st:
            k = st[id(i)]
            extra = " -> MINIPAD" if k == len(circ.stages) - 1 else ""
            outline(ax, i["box"], "#0d47a1", f"DFF {k} (Q{k}{extra})", loc="tl" if k % 2 else "tr")
    for name, (x, y) in chip.pads().items():
        ax.text(x, y, name, ha="center", va="center", fontsize=12, fontweight="bold", color="#0b3d91")
    fig.tight_layout()
    fig.savefig(IMG_DIR / "layout_floorplan.png", dpi=110)
    plt.close(fig)


def fig_dff(chip, circ, k=0):
    """Zoom on one flip-flop with every NAND/INV sub-cell labelled by its role."""
    insts = chip.instances()
    st = stage_of_instance(circ, insts)
    dff = next(i for i in insts if st.get(id(i)) == k)
    subs = [i for i in insts if i["depth"] == 2 and inside(dff["box"], *i["box"][:2])
            and inside(dff["box"], *i["box"][2:])]
    m = 6
    b = dff["box"]
    fig, ax = plt.subplots(figsize=(12, 5.4))
    chip.draw(ax, (b[0] - m, b[1] - m, b[2] + m, b[3] + m), art=False)
    stage_gates = [g for g in circ.gates if circ.name(g["out"]).startswith(f"S{k}_") or g["out"] == circ.stages[k]["Q"]]
    for s in subs:
        g = next((g for g in stage_gates
                  if inside(s["box"], circ.devices[g["devs"][0]]["x"], circ.devices[g["devs"][0]]["y"])), None)
        label = f"{circ.name(g['out'])}\n{g['kind']}" if g else s["cell"]
        outline(ax, s["box"], "#212121", label, lw=1.0, fontsize=8)
    ax.set_title(f"Flip-flop {k} ({dff['cell']}): master latch = M1, M2, MQ, MQB; slave latch = S1, S2, Q, QB")
    fig.tight_layout()
    fig.savefig(IMG_DIR / "layout_dff.png", dpi=110)
    plt.close(fig)


def fig_die_vs_layout(chip):
    die = plt.imread(str(DIE_PHOTO))
    crop = die[60:325, 355:615]  # region around the G12 die in the probe-station photo
    fig, axs = plt.subplots(1, 2, figsize=(12, 6))
    axs[0].imshow(crop)
    axs[0].set_title(f"Fabricated die on the probe station ({DIE_PHOTO.name}, cropped)")
    axs[0].axis("off")
    chip.draw(axs[1])
    for name, (x, y) in chip.pads().items():
        axs[1].text(x, y, name, ha="center", va="center", fontsize=11, fontweight="bold", color="#0b3d91")
    axs[1].set_title("Layout (GDS)")
    axs[1].axis("off")
    fig.tight_layout()
    fig.savefig(IMG_DIR / "die_vs_layout.jpg", dpi=110, pil_kwargs={"quality": 88})
    plt.close(fig)


def fig_clock_net(chip, circ, l2n):
    """The clock net PHI highlighted: almost all of it is poly."""
    from extract_netlist import net_region
    dwell = l2n.layer_by_name("DWELL")
    poly = net_region(l2n, circ.phi, "POLY") - dwell
    metal = net_region(l2n, circ.phi, "METAL")
    dbu = l2n.internal_layout().dbu
    insts = chip.instances()
    st = stage_of_instance(circ, insts)
    fig, ax = plt.subplots(figsize=(7.6, 7.6))
    chip.draw(ax, fade=0.22)
    chip._patch(ax, poly.merged(), "#d50000", 0.95)
    chip._patch(ax, metal.merged(), "#0d47a1", 0.95)
    for i in insts:
        if i["cell"] == "clk_layout_langsun":
            outline(ax, i["box"], "#6a1b9a", "RC clock generator", loc="tl", fontsize=8)
        elif id(i) in st:
            outline(ax, i["box"], "#455a64", f"DFF {st[id(i)]}", lw=1.0, loc="tr", fontsize=8)
    ax.set_title(f"Clock net PHI: {metal.area() * dbu * dbu:,.0f} um² metal (blue), "
                 f"{poly.area() * dbu * dbu:,.0f} um² poly wiring (red)", fontsize=10)
    fig.tight_layout()
    fig.savefig(IMG_DIR / "layout_clock_net.png", dpi=110)
    plt.close(fig)


def fig_art(chip):
    """The ART-layer initials, turned upright: die photo crop next to the layout."""
    die = plt.imread(str(DIE_PHOTO))
    crop = np.rot90(die[226:290, 366:420], k=-1)  # the text runs bottom-to-top on the die
    art = kdb.Region()
    for layer in (1, 5, 7):
        art += chip.region(layer, ART_DATATYPE)
    fig, axs = plt.subplots(1, 2, figsize=(8, 2.6), gridspec_kw={"width_ratios": [1, 1.15]})
    axs[0].imshow(crop, interpolation="lanczos")
    axs[0].set_title("on the die (G12C1.jpg)", fontsize=10)
    for poly in art.each():
        pts = [(p.y, -p.x) for p in poly.to_dtype(chip.dbu).each_point_hull()]  # rotate 90 deg cw
        axs[1].add_patch(plt.Polygon(pts, fc=ART_COLOR, ec="none"))
    b = art.bbox().to_dtype(chip.dbu)
    axs[1].set_xlim(b.bottom - 4, b.top + 4)
    axs[1].set_ylim(-b.right - 4, -b.left + 4)
    axs[1].set_aspect("equal")
    axs[1].set_title("ART layer in the GDS", fontsize=10)
    for ax in axs:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(IMG_DIR / "art.png", dpi=110)
    plt.close(fig)


def fig_timing(circ, n_reset=4, n_run=32):
    sim = LogicSim(circ)
    rows = {"PHI": [], "RST": [], **{f"Q{k}": [] for k in range(len(circ.stages))}}
    for c in range(n_reset + n_run):
        rst = 1 if c < n_reset else 0
        for phi in (0, 1):
            sim.val["RST"] = rst
            sim.val[circ.phi] = phi
            sim._settle_sync()
            rows["PHI"].append(phi)
            rows["RST"].append(rst)
            for k, s in enumerate(circ.stages):
                rows[f"Q{k}"].append(sim.val[s["Q"]])
    t = np.arange(len(rows["PHI"]) + 1) / 2
    fig, ax = plt.subplots(figsize=(13, 3.8))
    labels = list(rows)
    for i, name in enumerate(labels):
        y0 = (len(labels) - 1 - i) * 1.5
        v = np.array(rows[name] + rows[name][-1:])
        color = "#c62828" if name == f"Q{len(circ.stages) - 1}" else "#263238"
        ax.step(t, y0 + v, where="post", color=color, lw=1.4)
        ax.text(-0.6, y0 + 0.4, name if not color.startswith("#c6") else f"{name} = MINIPAD\n(LED on = 1)",
                ha="right", va="center", fontsize=9, color=color)
    out = [rows[f"Q{len(circ.stages) - 1}"][2 * c + 1] for c in range(n_reset, n_reset + n_run)]
    p0 = n_reset
    for rep in range(2):
        a, b = p0 + 15 * rep, p0 + 15 * (rep + 1)
        ax.annotate("", xy=(a, -0.6), xytext=(b, -0.6), arrowprops=dict(arrowstyle="<->", color="#1565c0"))
        ax.text((a + b) / 2, -1.0, "15 clock cycles", ha="center", va="top", color="#1565c0", fontsize=9)
    ax.axvspan(0, n_reset, color="#ffcdd2", alpha=0.4, lw=0)
    ax.text(n_reset / 2, len(labels) * 1.5 - 0.3, "RST = 1", ha="center", fontsize=9, color="#b71c1c")
    ax.set_xlim(-0.2, n_reset + n_run)
    ax.set_ylim(-1.6, len(labels) * 1.5)
    ax.set_yticks([])
    ax.set_xlabel("clock cycle")
    ax.set_title("Logic simulation of the netlist recovered from the GDS: Q3 = " + "".join(map(str, out[:15])) + " ...")
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG_DIR / "sim_timing.png", dpi=110)
    plt.close(fig)


def fig_clocks(res):
    fig, axs = plt.subplots(1, 2, figsize=(13, 3.8))
    for ax, folder, span in zip(axs, ("G12_CLK_SLW", "G12_CLK10NF"), (3, 3)):
        t, v, _ = scope.load_tek_csv(scope.capture_path(folder, next(s for f, s, *_ in scope.CAPTURES if f == folder)))
        c = res[folder]["clock"]
        t0 = t[0]
        sel = t <= t0 + span * c["period_s"]
        scale, unit = (1e3, "ms")
        ax.plot((t[sel] - t0) * scale, v[sel], color="#283593", lw=1.2)
        ax.set_title(f"{folder}: {c['freq_hz']:.4g} Hz, duty {c['duty'] * 100:.0f} %, "
                     f"{c['vmin']:.2f}-{c['vmax']:.2f} V")
        ax.set_xlabel(f"time [{unit}]")
        ax.set_ylabel("V")
        ax.set_ylim(0, 3.2)
        ax.grid(alpha=0.3)
    axs[1].text(0.98, 0.05, "C_ext = 10 nF", transform=axs[1].transAxes, ha="right")
    axs[0].text(0.98, 0.05, "C_ext not recorded", transform=axs[0].transAxes, ha="right")
    fig.tight_layout()
    fig.savefig(IMG_DIR / "meas_clock.png", dpi=110)
    plt.close(fig)


def _shade_decode(ax, t, v, dec, scale):
    colors = {"A": "#e0e0e0", "0": "#bbdefb", "1": "#ffcdd2"}
    for lab, a, b in dec["segments"]:
        ax.axvspan(a * scale, b * scale, color=colors[lab], alpha=0.8, lw=0)
    ax.plot(t * scale, v, color="#212121", lw=0.8)
    for lab, a, b in dec["segments"]:
        if lab != "A":
            ax.text((a + b) / 2 * scale, 3.12, lab, ha="center", va="bottom", fontsize=9,
                    color="#b71c1c" if lab == "1" else "#0d47a1", fontweight="bold")
    for name, lv in dec["levels_v"].items():
        ax.axhline(lv, color="#757575", lw=0.6, ls="--")
    ax.set_ylim(1.2, 3.45)
    ax.set_ylabel("Vo [V]")


def fig_output(res, reference):
    fig, axs = plt.subplots(2, 1, figsize=(13, 7.4), gridspec_kw={"height_ratios": [1, 1.25]})
    # (a) structure of one capture
    t, v, _ = scope.load_tek_csv(scope.capture_path("G12_OUT", "F0022"))
    dec = res["G12_OUT"]["decode"]
    _shade_decode(axs[0], t, v, dec, 1e3)
    lv = dec["levels_v"]
    axs[0].set_title("G12_OUT (5 ms/div): every clock period = phase A (grey, driver always off) "
                     "+ bit phase (blue = 0, red = 1); glitches at phase boundaries")
    for name, txt in (("A", "A"), ("B0", "bit 0"), ("B1", "bit 1")):
        axs[0].text(t[-1] * 1e3 + 0.3, lv[name], f"{txt}: {lv[name]:.2f} V", va="center", fontsize=8)
    axs[0].set_xlim(t[0] * 1e3, t[-1] * 1e3 + 5)
    axs[0].set_xlabel("time [ms]")
    # (b) long capture, decoded + recurrence check
    t, v, _ = scope.load_tek_csv(scope.capture_path("G12_OUT2", "F0023"))
    dec, chk = res["G12_OUT2"]["decode"], res["G12_OUT2"]["lfsr"]
    _shade_decode(axs[1], t, v, dec, 1e3)
    bit_segs = [s for s in dec["segments"] if s[0] != "A"]
    for n, mark in enumerate(chk["marks"]):
        lab, a, b = bit_segs[n + 4]
        x = (a + b) / 2 * 1e3
        if mark == ".":
            axs[1].text(x, 1.32, "ok", ha="center", fontsize=7, color="#2e7d32")
        else:
            axs[1].text(x, 1.32, "X", ha="center", fontsize=9, color="#b71c1c" if mark == "1" else "#ef6c00",
                        fontweight="bold")
    for p in chk["lockup_entries"]:
        a, b = bit_segs[p + 1][1], bit_segs[p + 4][2]
        axs[1].annotate("0 followed by 1s x5: requires a jump into the 1111 lock-up state",
                        xy=((a + b) / 2 * 1e3, 1.75), xytext=((a + b) / 2 * 1e3 + 12, 2.3),
                        fontsize=8.5, color="#b71c1c", arrowprops=dict(arrowstyle="->", color="#b71c1c"),
                        bbox=dict(fc="white", ec="#b71c1c", alpha=0.95, pad=2))
    axs[1].set_ylim(1.15, 3.45)
    axs[1].set_xlim(t[0] * 1e3, t[-1] * 1e3)
    axs[1].set_xlabel("time [ms]")
    axs[1].set_title(f"G12_OUT2 (25 ms/div): {len(dec['bits'])} decoded bits; the register recurrence "
                     f"Q3[n+4] = XNOR(Q3[n+3], Q3[n]) holds for only {chk['ok']} of {chk['checks']}")
    fig.text(0.01, 0.005, "Bottom row: ok = recurrence holds;  X red = measured 1 where 0 is predicted "
             "(cannot be caused by RST, which only forces 0s);  X orange = measured 0 where 1 is predicted.",
             fontsize=8.5, color="#424242")
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(IMG_DIR / "meas_output.png", dpi=110)
    plt.close(fig)


def fig_first_session(res):
    t, v, _ = scope.load_tek_csv(scope.capture_path("G12_OutFRI", "F0000"))
    b = res["G12_OutFRI"]["burst"]
    fig, ax = plt.subplots(figsize=(13, 3.4))
    ax.plot(t * 1e6, v, color="#4e342e", lw=0.9)
    ax.set_xlabel("time [us]")
    ax.set_ylabel("V")
    ax.set_title(f"G12_OutFRI (first session, 50 us/div, 100 mV/div): {b['vpp'] * 1e3:.0f} mV swing, "
                 f"clock ~{1 / b['period_s'] / 1e3:.0f} kHz, bursts of {b['bursts']} consecutive high slots")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(IMG_DIR / "meas_first_session.png", dpi=110)
    plt.close(fig)


def main(circ=None, res=None, reference=None, l2n=None):
    ensure_dirs()
    if circ is None or l2n is None:
        from extract_netlist import extract
        from gate_level import lfsr_report
        l2n, devices = extract()
        circ = Circuit(devices)
        _, reference, _ = lfsr_report(circ)
        res = scope.analyze(reference)
    chip = Chip()
    fig_floorplan(chip, circ)
    fig_dff(chip, circ)
    fig_clock_net(chip, circ, l2n)
    fig_die_vs_layout(chip)
    fig_art(chip)
    fig_timing(circ)
    fig_clocks(res)
    fig_output(res, reference)
    fig_first_session(res)
    print("figures written to", IMG_DIR)


if __name__ == "__main__":
    main()
