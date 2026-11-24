"""Analysis of the post-fabrication oscilloscope captures (Tektronix TDS2024C CSV).

- clock captures:  frequency, duty cycle, levels
- output captures: decode one bit per clock period and check the bit stream
  against the 4-bit XNOR LFSR implemented on the chip

Output: analysis/results/post_fab_summary.md
"""
import re

import numpy as np

from common import RESULTS_DIR, SCOPE_DIR, ensure_dirs

# Folder, file stem, what the tester labelled it, scope date/time read from the
# saved screenshot (the CSV does not contain it). CLK_SLW's screenshot shows a
# status message instead of the date.
CAPTURES = [
    ("G12_OutFRI", "F0000", "output, first session (folder name: 'FRI')", "19-Nov-22 02:42"),
    ("G12_CLK_SLW", "F0021", "clock, unrecorded C_ext ('slow')", "-"),
    ("G12_OUT", "F0022", "output, 5 ms/div", "22-Nov-22 02:45"),
    ("G12_OUT2", "F0023", "output, 25 ms/div", "22-Nov-22 02:46"),
    ("G12_CLK10NF", "F0024", "clock, C_ext = 10 nF", "22-Nov-22 02:53"),
]


def capture_path(folder, stem):
    return SCOPE_DIR / folder / f"{stem}CH2.CSV"


def load_tek_csv(path):
    """TDS2000-series CSV: columns 0/1 = header key/value, columns 3/4 = time/voltage."""
    meta, t, v = {}, [], []
    with open(path) as f:
        for line in f:
            parts = [p.strip() for p in line.split(",")]
            if parts[0]:
                meta[parts[0]] = parts[1]
            t.append(float(parts[3]))
            v.append(float(parts[4]))
    return np.array(t), np.array(v), meta


def kmeans1d(v, k, iters=100):
    centers = np.quantile(v, np.linspace(0.05, 0.95, k))
    for _ in range(iters):
        labels = np.argmin(np.abs(v[:, None] - centers[None, :]), axis=1)
        new = np.array([v[labels == i].mean() if np.any(labels == i) else centers[i] for i in range(k)])
        if np.allclose(new, centers):
            break
        centers = new
    return np.sort(centers)


def runs(t, cls):
    """Run-length encode a label array -> list of [label, t_start, t_end]."""
    out, start = [], 0
    dt = t[1] - t[0]
    for i in range(1, len(cls) + 1):
        if i == len(cls) or cls[i] != cls[start]:
            out.append([cls[start], t[start], t[i - 1] + dt])
            start = i
    return out


# ----------------------------------------------------------------------------
# clock captures
# ----------------------------------------------------------------------------
def clock_stats(t, v):
    lo, hi = kmeans1d(v, 2)
    thr = (lo + hi) / 2
    segs = runs(t, v > thr)
    full = segs[1:-1]  # drop partial first/last segments
    highs = np.array([b - a for h, a, b in full if h])
    lows = np.array([b - a for h, a, b in full if not h])
    period = highs.mean() + lows.mean()

    def plateau(level, frac=0.15):
        starts, ends = [], []
        for h, a, b in full:
            if h != level:
                continue
            seg = (t >= a) & (t < b)
            n = seg.sum()
            vv = v[seg]
            m = max(1, int(frac * n))
            starts.append(np.median(vv[1:m + 1]))
            ends.append(np.median(vv[-m - 1:-1]))
        return np.mean(starts), np.mean(ends)

    return {
        "freq_hz": 1 / period, "period_s": period, "duty": highs.mean() / period,
        "t_high_s": highs.mean(), "t_low_s": lows.mean(), "n_periods": min(len(highs), len(lows)),
        "high_start_v": plateau(True)[0], "high_end_v": plateau(True)[1],
        "low_start_v": plateau(False)[0], "low_end_v": plateau(False)[1],
        "vmin": v.min(), "vmax": v.max(), "vpp": v.max() - v.min(), "vmean": v.mean(),
    }


# ----------------------------------------------------------------------------
# output captures (slow clock): one bit per clock period
# ----------------------------------------------------------------------------
def decode_phased_output(t, v, min_len=0.4e-3):
    """The Vo waveform has three levels:
         A  : always present for part of every clock period (output transistor off)
         B0 : rest of the period when the register output is 0
         B1 : rest of the period when the register output is 1 (LED driver on)
    plus short glitches (< min_len) at the phase boundaries, which are dropped.
    Returns one bit per B segment."""
    c_b1, c_b0, c_a = kmeans1d(v, 3)
    thr_lo, thr_hi = (c_b1 + c_b0) / 2, (c_b0 + c_a) / 2
    cls = np.where(v >= thr_hi, "A", np.where(v < thr_lo, "1", "0"))
    segs = [s for s in runs(t, cls) if s[2] - s[1] >= min_len]
    merged = []
    for s in segs:
        if merged and merged[-1][0] == s[0]:
            merged[-1][2] = s[2]
        else:
            merged.append(list(s))
    pattern = "".join("A" if s[0] == "A" else "b" for s in merged)
    alternates = "AA" not in pattern and "bb" not in pattern
    a_starts = np.array([s[1] for s in merged if s[0] == "A"])
    a_lens = np.array([s[2] - s[1] for s in merged if s[0] == "A"][1:-1])
    period = np.diff(a_starts)
    bits = "".join(s[0] for s in merged if s[0] != "A")
    return {
        "levels_v": {"A": c_a, "B0": c_b0, "B1": c_b1},
        "segments": merged, "alternates": alternates, "bits": bits,
        "period_s": period.mean(), "period_std_s": period.std(), "a_len_s": a_lens.mean(),
        "glitches": sum(1 for s in runs(t, cls) if s[2] - s[1] < min_len and s[0] == "1"),
    }


def lfsr_consistency(bits, reference):
    """Check a measured Q3 bit stream against the on-chip register:
         Q3[n+4] = XNOR(Q3[n+3], Q3[n])        (RST = 0)
    RST can only force zeros into the register, so a measured 1 where the
    recurrence predicts 0 cannot be explained by RST activity. A 0 followed by
    four 1s requires entering the 1111 lock-up state from another state, which
    a fault-free register cannot do with or without RST."""
    y = [int(c) for c in bits]
    viol0 = viol1 = 0
    marks = []
    for n in range(len(y) - 4):
        pred = 1 ^ y[n + 3] ^ y[n]
        if pred == y[n + 4]:
            marks.append(".")
        elif y[n + 4] == 0:
            viol0 += 1
            marks.append("0")
        else:
            viol1 += 1
            marks.append("1")
    run_lengths = {c: max((len(m.group()) for m in re.finditer(f"{c}+", bits)), default=0) for c in "01"}
    lockup_entries = [m.start() for m in re.finditer(r"(?=01111)", bits)]
    n = len(reference)
    best = min((sum(a != b for a, b in zip(bits, (reference * (len(bits) // n + 2))[s:])), s) for s in range(n))
    period = next((p for p in range(1, len(bits) // 2)
                   if all(bits[i] == bits[i + p] for i in range(len(bits) - p))), None)
    return {
        "checks": len(marks), "ok": marks.count("."), "viol_rst_explainable": viol0,
        "viol_not_rst": viol1, "marks": "".join(marks), "max_run": run_lengths,
        "lockup_entries": lockup_entries, "best_mismatch": best[0], "best_shift": best[1],
        "period": period, "ones": bits.count("1"),
    }


FAULT_MODELS = {
    "rst": "RST pulses only (force a 0 into Q0)",
    "race": "hold-time races at DFF1 and/or DFF3 (they capture the new value of the stage feeding them)",
    "race+rst": "races and RST pulses",
    "clock": "missed or extra clock edges (0-3 shifts per period)",
    "upset": "arbitrary upsets of any register bits",
}


def fault_model_fit(bits):
    """Fewest fault events with which each model reproduces the measured Q3 stream.

    Exhaustive search (Viterbi) over all 16 start states and, every clock period,
    every choice the model allows. None = the model cannot produce the stream."""
    from itertools import product

    def shift(s, race1=False, race3=False, rst=False):
        q0, q1, q2, q3 = s
        d0 = 0 if rst else 1 ^ q0 ^ q3
        return (d0, d0 if race1 else q0, q1, q1 if race3 else q2)

    def options(s, model):
        if model == "clock":
            out, st = [], s
            for k in range(4):
                out.append((st, int(k != 1)))
                st = shift(st)
            return out
        if model == "upset":
            base = shift(s)
            return [(tuple(b ^ ((m >> (3 - i)) & 1) for i, b in enumerate(base)), bin(m).count("1"))
                    for m in range(16)]
        races = product((0, 1), repeat=2) if "race" in model else [(0, 0)]
        rsts = (0, 1) if "rst" in model else (0,)
        return [(shift(s, r1, r3, rs), r1 + r3 + rs) for (r1, r3) in races for rs in rsts]

    y = [int(c) for c in bits]
    result = {}
    for model in FAULT_MODELS:
        best = {s: 0 for s in product((0, 1), repeat=4) if s[3] == y[0]}
        for k in range(1, len(y)):
            nxt = {}
            for s, c in best.items():
                for ns, dc in options(s, model):
                    if ns[3] == y[k] and c + dc < nxt.get(ns, 10 ** 9):
                        nxt[ns] = c + dc
            best = nxt
            if not best:
                break
        result[model] = min(best.values()) if best else None
    return result


# ----------------------------------------------------------------------------
# output capture (fast clock, first session)
# ----------------------------------------------------------------------------
def burst_analysis(t, v, min_pulse=5e-6, max_dip=3e-6):
    """High 'slot' pulses (>= min_pulse) separated by short dips (< max_dip)
    form bursts. Reports burst sizes and gap lengths in clock periods."""
    lo, hi = kmeans1d(v, 2)
    segs = runs(t, v > (lo + hi) / 2)
    dips = [(a + b) / 2 for k, (h, a, b) in enumerate(segs[1:-1], 1)
            if not h and b - a < max_dip and segs[k - 1][0] and segs[k + 1][0]]
    iv = np.diff(dips)
    period = np.median(iv[iv < 2 * np.median(iv)])
    bursts, cur, last_end = [], 0, None
    gaps = []
    for h, a, b in segs:
        if h and b - a >= min_pulse:
            if cur == 0 and last_end is not None:
                gaps.append(a - last_end)
            cur += 1
            last_end = b
        elif not h and b - a >= max_dip and cur:
            bursts.append(cur)
            cur = 0
    if cur:
        bursts.append(cur)
    return {"levels_v": (lo, hi), "period_s": period, "bursts": bursts,
            "gaps_periods": [g / period for g in gaps], "vpp": v.max() - v.min()}


# ----------------------------------------------------------------------------
def analyze(reference):
    res = {}
    for folder, stem, desc, when in CAPTURES:
        t, v, meta = load_tek_csv(capture_path(folder, stem))
        entry = {"desc": desc, "when": when, "meta": meta, "span_s": t[-1] - t[0] + (t[1] - t[0])}
        if "CLK" in folder:
            entry["clock"] = clock_stats(t, v)
        elif folder == "G12_OutFRI":
            entry["burst"] = burst_analysis(t, v)
        else:
            dec = decode_phased_output(t, v)
            entry["decode"] = dec
            entry["lfsr"] = lfsr_consistency(dec["bits"], reference)
            entry["faults"] = fault_model_fit(dec["bits"])
        res[folder] = entry
    return res


def si(x, unit):
    """Format a number with an SI prefix, e.g. si(5e-5, 's') -> '50 us'."""
    for scale, prefix in ((1, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n")):
        if abs(x) >= scale:
            return f"{x / scale:.3g} {prefix}{unit}"
    return f"{x:g} {unit}"


def summary_markdown(res, reference):
    L = ["# Post-fabrication measurement summary", "",
         "Generated by `analysis/scope.py` from the CSV files in `post_fab_test/` "
         "(Tektronix TDS2024C, channel 2, 2500 points, 1x probe).", "",
         "## Captures", "", "| Folder | File | What | Scope date | Time/div | V/div | Span |",
         "|---|---|---|---|---:|---:|---:|"]
    for folder, stem, desc, when in CAPTURES:
        m = res[folder]["meta"]
        L.append(f"| `{folder}` | {stem} | {desc} | {when} | {si(float(m['Horizontal Scale']), 's')} "
                 f"| {si(float(m['Vertical Scale']), 'V')} | {si(res[folder]['span_s'], 's')} |")
    L += ["", "## Clock", "", "| Capture | f | period | duty (high) | high level | low level | Vpp |",
          "|---|---:|---:|---:|---|---|---:|"]
    for folder in ("G12_CLK_SLW", "G12_CLK10NF"):
        c = res[folder]["clock"]
        L.append(f"| `{folder}` | {c['freq_hz']:.1f} Hz | {c['period_s'] * 1e3:.3f} ms | {c['duty'] * 100:.0f} % "
                 f"| {c['high_start_v']:.2f} -> {c['high_end_v']:.2f} V | {c['low_start_v']:.2f} -> {c['low_end_v']:.2f} V "
                 f"| {c['vpp']:.2f} V |")
    L += ["", "## Output (Vo), slow clock", ""]
    for folder in ("G12_OUT", "G12_OUT2"):
        d, c = res[folder]["decode"], res[folder]["lfsr"]
        lv = d["levels_v"]
        L += [f"### `{folder}`", "",
              f"- Levels: A = {lv['A']:.2f} V (every period), B0 = {lv['B0']:.2f} V (bit 0), "
              f"B1 = {lv['B1']:.2f} V (bit 1, driver on); {d['glitches']} short glitches dropped.",
              f"- Phases alternate A / bit strictly: {'yes' if d['alternates'] else 'NO'}; "
              f"clock period {d['period_s'] * 1e3:.2f} ms ({1 / d['period_s']:.1f} Hz), A phase {d['a_len_s'] * 1e3:.2f} ms.",
              f"- Decoded Q3 bits ({len(d['bits'])}): `{d['bits']}`",
              f"- LFSR recurrence Q3[n+4] = XNOR(Q3[n+3], Q3[n]): {c['ok']}/{c['checks']} hold; "
              f"violations {c['viol_rst_explainable']} (measured 0, could be RST) + "
              f"{c['viol_not_rst']} (measured 1, not explainable by RST).",
              f"- Longest runs: {c['max_run']['0']} zeros, {c['max_run']['1']} ones "
              f"(fault-free register: <= 4 zeros, <= 3 ones). "
              f"'0 then four 1s' (needs a jump into the 1111 lock-up): "
              f"{len(c['lockup_entries'])} occurrence(s).",
              f"- Best alignment with the reference sequence `{reference}`: "
              f"{c['best_mismatch']} mismatches out of {len(d['bits'])}. Periodicity found: {c['period']}.", "",
              "  Fewest fault events with which a fault model reproduces the stream "
              "(exhaustive search over start states and per-cycle choices):", "",
              "  | Fault model | Fewest events |", "  |---|---:|"]
        for model, desc in FAULT_MODELS.items():
            n = res[folder]["faults"][model]
            L.append(f"  | {desc} | {'cannot reproduce' if n is None else n} |")
        L.append("")
    b = res["G12_OutFRI"]["burst"]
    L += ["## Output, first session (`G12_OutFRI`)", "",
          f"- Levels {b['levels_v'][0]:.2f} / {b['levels_v'][1]:.2f} V (Vpp {b['vpp']:.2f} V); "
          f"clock period from dip spacing {b['period_s'] * 1e6:.2f} us ({1 / b['period_s'] / 1e3:.0f} kHz).",
          f"- Bursts of consecutive high slots: {b['bursts']}",
          f"- Gaps between bursts [clock periods]: {[round(float(g), 1) for g in b['gaps_periods']]}", ""]
    return "\n".join(L)


def main(reference=None):
    ensure_dirs()
    if reference is None:
        from gate_level import Circuit, lfsr_report
        from extract_netlist import extract
        _, devices = extract()
        _, reference, _ = lfsr_report(Circuit(devices))
    res = analyze(reference)
    text = summary_markdown(res, reference)
    (RESULTS_DIR / "post_fab_summary.md").write_text(text)
    print(text)
    return res


if __name__ == "__main__":
    main()
