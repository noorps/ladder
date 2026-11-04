"""charts for the readme. every chart reads a json in results/<label>/ and writes its own
json (the exact numbers plotted) beside the png."""
import argparse
import json
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ladder.instance import load_scholl_graph  # noqa: E402
from ladder.metrics import station_loads, summary  # noqa: E402
from ladder.solvers import exact, rpw  # noqa: E402
from ladder.validate import validate  # noqa: E402

BG, PANEL, TEXT, MUTED = "#FAF8F1", "#F2F0E4", "#2B2E28", "#6E7566"
MATCHA, DEEP, SOFT, RULE = "#6E9460", "#4C6B42", "#AFC7A3", "#E7E2D4"
OVER = "#B64E3A"
RAMP = ["#C9D9BF", "#AFC7A3", "#8DAE7E", "#6E9460", "#4C6B42"]   # one hue, light to dark
SOLVER_COLORS = {"rpw": SOFT, "comsoal": MATCHA, "cpsat": TEXT}
SOLVER_NAMES = {"rpw": "rpw", "comsoal": "comsoal", "cpsat": "cp-sat"}

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "sans-serif"],
    "font.size": 10, "axes.edgecolor": RULE, "axes.labelcolor": TEXT, "xtick.color": MUTED,
    "ytick.color": MUTED, "text.color": TEXT, "axes.titlecolor": TEXT, "figure.facecolor": BG,
    "axes.facecolor": BG, "savefig.facecolor": BG, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": RULE, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "legend.frameon": False, "axes.titlelocation": "left", "axes.titleweight": "normal",
})


def first_fit_in_order(inst, c):
    """what a line looks like before anyone balances it: tasks in numbering order,
    open a new station whenever the next task does not fit."""
    station_of = [0] * inst.n
    k, room = 0, c
    for i in inst.topo_order:
        if inst.times[i] > room:
            k += 1
            room = c
        station_of[i] = k
        room -= inst.times[i]
    validate(inst, station_of, c)
    return station_of


def bars(ax, loads, c, title):
    xs = range(1, len(loads) + 1)
    colors = [OVER if l > c else SOFT for l in loads]
    ax.bar(xs, loads, color=colors, width=0.72, edgecolor=BG, linewidth=1)
    ax.axhline(c, color=DEEP, linewidth=1.4, linestyle=(0, (4, 3)))
    ax.text(0.5, c + c * 0.03, f"takt {c} s", va="bottom", ha="left", fontsize=9, color=DEEP)
    ax.set_xticks(list(xs))
    ax.set_xlim(0.3, len(loads) + 2.2)
    ax.set_ylim(0, c * 1.25)
    ax.set_xlabel("station")
    ax.set_title(title, fontsize=11, pad=8)
    ax.grid(axis="x", visible=False)


def station_loading(out_dir, graph="Sawyer", c=41):
    inst = load_scholl_graph(graph)
    before = first_fit_in_order(inst, c)
    mid = rpw.solve_salbp1(inst, c).assignment
    after = exact.solve_salbp1(inst, c, time_limit=60)
    assert after.proven
    panels = [("before: tasks placed in numbering order", before),
              ("ranked positional weight", mid),
              ("cp-sat, proven optimal", after.assignment)]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    data = {"instance": graph, "n": inst.n, "cycle_time": c, "panels": []}
    for ax, (title, a) in zip(axes, panels):
        s = summary(inst, a, c)
        bars(ax, s["loads"], c, f"{title}\n{s['stations']} stations, efficiency {100 * s['line_efficiency']:.0f}%, "
                                f"smoothness {s['smoothness_index']:.1f}")
        data["panels"].append({"title": title, "assignment": a, **{k: v for k, v in s.items()}})
    axes[0].set_ylabel("station load (s)")
    fig.suptitle(f"{graph.lower()} ({inst.n} tasks) at a {c} s cycle time: total work {inst.total_time} s", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_dir / "station_loading.png", dpi=160)
    (out_dir / "station_loading.json").write_text(json.dumps(data, indent=1))
    plt.close(fig)


def throughput_vs_variability(out_dir):
    doc = json.loads((out_dir / "sim_sweep.json").read_text())
    line = doc["lines"][0]
    buffers = doc["buffers"]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    data = {"line": line["name"], "stations": line["stations"], "cycle_time": line["cycle_time"],
            "paper_uph": line["paper_uph"], "series": []}
    for i, b in enumerate(buffers):
        cells = sorted([g for g in line["grid"] if g["buffer"] == b], key=lambda g: g["cv"])
        xs = [g["cv"] for g in cells]
        ys = [g["actual_uph_mean"] for g in cells]
        lo = [g["actual_over_paper_min"] * line["paper_uph"] for g in cells]
        hi = [g["actual_over_paper_max"] * line["paper_uph"] for g in cells]
        color = RAMP[min(i, len(RAMP) - 1)]
        ax.fill_between(xs, lo, hi, color=color, alpha=0.18, linewidth=0)
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=4, markerfacecolor=BG, markeredgewidth=1.5)
        ax.text(xs[-1] + 0.02, ys[-1], f"buffer {b}", va="center", fontsize=9, color=color if i > 1 else MUTED)
        data["series"].append({"buffer": b, "cv": xs, "actual_uph": ys, "uph_min": lo, "uph_max": hi})
    ax.axhline(line["paper_uph"], color=DEEP, linewidth=1.2, linestyle=(0, (4, 3)))
    ax.text(0.0, line["paper_uph"] + 1.2, f"paper rate {line['paper_uph']:.0f} uph", fontsize=9, color=DEEP)
    ax.set_xlabel("coefficient of variation of station time")
    ax.set_ylabel("units per hour (mean of 3 seeds, band = spread)")
    ax.set_xlim(-0.02, 1.12)
    ax.set_title(f"{line['name'].split('_')[0].lower()} optimal balance, {line['stations']} stations at a "
                 f"{line['cycle_time']} s cycle time: simulated throughput against the paper rate", fontsize=11, pad=8)
    fig.tight_layout()
    fig.savefig(out_dir / "throughput_vs_variability.png", dpi=160)
    (out_dir / "throughput_vs_variability.json").write_text(json.dumps(data, indent=1))
    plt.close(fig)


BUCKETS = [(1, 25, "n <= 25"), (26, 50, "26-50"), (51, 100, "51-100"), (101, 150, "101-150"), (151, 10000, "> 150")]


def gap_to_optimal(out_dir):
    doc = json.loads((out_dir / "benchmark.json").read_text())
    recs = []
    for set_name, s in doc["sets"].items():
        if s["problem"] != 1:
            continue
        recs.extend(s["instances"])
    data = {"problem": "salbp-1", "sets": [k for k, s in doc["sets"].items() if s["problem"] == 1],
            "time_limit_s": doc["config"]["time_limit"], "buckets": []}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), gridspec_kw={"width_ratios": [1.3, 1]})
    width = 0.26
    for bi, (lo, hi, label) in enumerate(BUCKETS):
        rs = [r for r in recs if lo <= r["n"] <= hi]
        if not rs:
            continue
        row = {"bucket": label, "instances": len(rs), "solvers": {}}
        for si, name in enumerate(["rpw", "comsoal", "cpsat"]):
            gaps = [r["solvers"][name]["gap_pct"] for r in rs]
            g = statistics.fmean(gaps)
            x = bi + (si - 1) * width
            ax1.bar(x, g, width=width - 0.03, color=SOLVER_COLORS[name], edgecolor=BG, linewidth=1)
            ax1.text(x, g + 0.15, f"{g:.1f}", ha="center", va="bottom", fontsize=8, color=TEXT)
            row["solvers"][name] = {"gap_mean_pct": g, "matched_best_known": sum(r["solvers"][name]["matched_best_known"] for r in rs)}
        cp = [r["solvers"]["cpsat"] for r in rs]
        proven = [r for r in cp if r["proven"]]
        row["cpsat_proven"] = len(proven)
        row["cpsat_time_median_proven_s"] = statistics.median(r["time_median"] for r in proven) if proven else None
        row["cpsat_time_median_all_s"] = statistics.median(r["time_median"] for r in cp)
        data["buckets"].append(row)
        ax2.bar(bi, row["cpsat_time_median_all_s"], width=0.5, color=TEXT, edgecolor=BG)
        ax2.text(bi, row["cpsat_time_median_all_s"] * 1.15, f"{len(proven)}/{len(rs)} proven", ha="center", fontsize=8, color=MUTED)
    labels = [b["bucket"] for b in data["buckets"]]
    ax1.set_xticks(range(len(labels)))
    ax1.set_xticklabels(labels)
    ax1.set_xlabel("tasks per instance")
    ax1.set_ylabel("mean gap to published best known (%)")
    ax1.set_title("salbp-1: how far each solver lands above the published optimum", fontsize=11, pad=8)
    ax1.grid(axis="x", visible=False)
    for name in ["rpw", "comsoal", "cpsat"]:
        ax1.bar(0, 0, color=SOLVER_COLORS[name], label=SOLVER_NAMES[name])
    ax1.legend(loc="upper left", fontsize=9)
    ax2.set_xticks(range(len(labels)))
    ax2.set_xticklabels(labels)
    ax2.set_yscale("log")
    ax2.set_xlabel("tasks per instance")
    ax2.set_ylabel("cp-sat median solve time (s, log)")
    ax2.set_title(f"cp-sat time with a {doc['config']['time_limit']:.0f} s limit", fontsize=11, pad=8)
    ax2.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(out_dir / "gap_to_optimal.png", dpi=160)
    (out_dir / "gap_to_optimal.json").write_text(json.dumps(data, indent=1))
    plt.close(fig)


def comsoal_n(out_dir):
    p = out_dir / "comsoal_sweep.json"
    if not p.exists():
        return
    doc = json.loads(p.read_text())
    fig, ax = plt.subplots(figsize=(7, 4))
    data = {"ns": doc["ns"], "series": []}
    names = list(doc["sets"])
    for i, set_name in enumerate(names):
        agg = doc["sets"][set_name]["aggregate"]
        ns = [int(n) for n in agg]
        ys = [agg[str(n)]["gap_mean_pct"] if str(n) in agg else agg[n]["gap_mean_pct"] for n in ns]
        color = RAMP[1 + i * 2] if 1 + i * 2 < len(RAMP) else RAMP[-1]
        ax.plot(ns, ys, color=color, linewidth=2, marker="o", markersize=4, markerfacecolor=BG, markeredgewidth=1.5)
        ax.text(ns[-1] * 1.15, ys[-1], set_name.replace("otto-", "otto "), va="center", fontsize=9, color=MUTED)
        data["series"].append({"set": set_name, "n": ns, "gap_mean_pct": ys,
                               "instances": agg[str(ns[0])]["instances"] if str(ns[0]) in agg else agg[ns[0]]["instances"]})
    ax.set_xscale("log")
    ax.set_xlim(0.8, max(doc["ns"]) * 2.5)
    ax.set_xlabel("comsoal trials (log)")
    ax.set_ylabel("mean gap to published optimum (%)")
    ax.set_title("comsoal: quality against the number of random trials", fontsize=11, pad=8)
    fig.tight_layout()
    fig.savefig(out_dir / "comsoal_n.png", dpi=160)
    (out_dir / "comsoal_n.json").write_text(json.dumps(data, indent=1))
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    out_dir = Path(__file__).resolve().parents[1] / "results" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    charts = {"station_loading": station_loading, "throughput_vs_variability": throughput_vs_variability,
              "gap_to_optimal": gap_to_optimal, "comsoal_n": comsoal_n}
    for name, fn in charts.items():
        if args.only and name not in args.only:
            continue
        try:
            fn(out_dir)
            print("wrote", name)
        except FileNotFoundError as e:
            print(f"skipped {name}: {e}")


if __name__ == "__main__":
    main()
