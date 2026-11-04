"""print the readme tables straight from the results json, so no number is typed by hand."""
import argparse
import json
import statistics
from pathlib import Path

SOLVER_NAMES = {"rpw": "rpw", "comsoal": "comsoal", "cpsat": "cp-sat"}


def fmt_t(x):
    return f"{x * 1000:.0f} ms" if x < 1 else f"{x:.1f} s"


def benchmark_tables(out_dir):
    doc = json.loads((out_dir / "benchmark.json").read_text())
    e, c = doc["env"], doc["config"]
    print(f"environment: {e['cpu']}, {e['logical_cpus']} logical cpus, {e['os']}, python {e['python']}, "
          f"or-tools {e['ortools']}, simpy {e['simpy']}. heuristics timed as the median of {c['repeats']} runs, "
          f"cp-sat run {c['exact_repeats']} time with {c['workers']} workers and a {c['time_limit']:.0f} s limit, "
          f"comsoal {c['comsoal_trials']} trials, otto sample {c['sample']} per size (seed {c['seed']}).")
    print()
    for set_name, s in doc["sets"].items():
        insts = s["instances"]
        ns = sorted(r["n"] for r in insts)
        unit = "stations" if s["problem"] == 1 else "cycle time"
        open_n = sum(1 for r in insts if r["published"]["optimum"] is None)
        print(f"**{set_name}** (salbp-{s['problem']}, {len(insts)} instances, {ns[0]} to {ns[-1]} tasks"
              + (f", {open_n} with no proven optimum, gap taken to the best known value" if open_n else "") + ")")
        print()
        print(f"| solver | mean gap | median gap | max gap | matched published optimum | time median | time max | mean efficiency | mean smoothness |")
        print("|---|---|---|---|---|---|---|---|---|")
        for name, a in s["aggregate"].items():
            extra = f" ({a['proven']} proven)" if name == "cpsat" else ""
            print(f"| {SOLVER_NAMES[name]} | {a['gap_mean_pct']:.2f}% | {a['gap_median_pct']:.2f}% | {a['gap_max_pct']:.1f}% | "
                  f"{a['matched_optimum']}/{a['with_known_optimum']}{extra} | {fmt_t(a['time_median_s'])} | {fmt_t(a['time_max_s'])} | "
                  f"{100 * a['efficiency_mean']:.1f}% | {a['smoothness_mean']:.1f} |")
        print()
    # time-to-prove by size across salbp-1 sets
    recs = [r for s in doc["sets"].values() if s["problem"] == 1 for r in s["instances"]]
    print("**cp-sat time to prove optimality by instance size (salbp-1, all sets pooled)**")
    print()
    print("| tasks | instances | proven within limit | median time (proven) | max time (proven) | mean gap when not proven |")
    print("|---|---|---|---|---|---|")
    for lo, hi, label in [(1, 25, "<= 25"), (26, 50, "26-50"), (51, 100, "51-100"), (101, 150, "101-150"), (151, 10000, "> 150")]:
        rs = [r for r in recs if lo <= r["n"] <= hi]
        if not rs:
            continue
        cp = [r["solvers"]["cpsat"] for r in rs]
        pr = [x for x in cp if x["proven"]]
        npr = [x for x in cp if not x["proven"]]
        print(f"| {label} | {len(rs)} | {len(pr)} | {fmt_t(statistics.median(x['time_median'] for x in pr)) if pr else '-'} | "
              f"{fmt_t(max(x['time_median'] for x in pr)) if pr else '-'} | "
              f"{(f'{statistics.fmean(x['gap_pct'] for x in npr):.2f}%') if npr else '-'} |")
    print()
    # surprises: heuristics beating best known / cp-sat improving a bound
    below = [(sn, r["name"], name, r["solvers"][name]["value"], r["published"]) for sn, s in doc["sets"].items()
             for r in s["instances"] for name in r["solvers"] if r["solvers"][name]["below_best_known"]]
    if below:
        print("below the published best known value:", below)
    print(f"elapsed {doc.get('elapsed_s', 0) / 60:.0f} min")


def comsoal_table(out_dir):
    p = out_dir / "comsoal_sweep.json"
    if not p.exists():
        return
    doc = json.loads(p.read_text())
    ns = doc["ns"]
    print("**comsoal: mean gap to the published optimum against trials**")
    print()
    print("| set | instances | " + " | ".join(f"n={n}" for n in ns) + " |")
    print("|---|---|" + "---|" * len(ns))
    for set_name, s in doc["sets"].items():
        a = s["aggregate"]
        cells = [a.get(str(n), a.get(n)) for n in ns]
        print(f"| {set_name} | {cells[0]['instances']} | " + " | ".join(f"{x['gap_mean_pct']:.2f}% ({x['matched_optimum']} opt)" for x in cells) + " |")
    print()


def sim_tables(out_dir):
    p = out_dir / "sim_sweep.json"
    if not p.exists():
        return
    doc = json.loads(p.read_text())
    c = doc["config"]
    print(f"simulation: {c['units']} units measured after a {c['warmup']} unit warm-up, {c['seeds']} seeds per cell.")
    print()
    for line in doc["lines"]:
        print(f"**{line['name']}**: {line['stations']} stations, cycle time {line['cycle_time']}, paper rate {line['paper_uph']:.1f} uph, "
              f"line efficiency {100 * line['line_efficiency']:.1f}%. cells are simulated throughput as a share of the paper rate (mean, min-max over seeds).")
        print()
        print("| cv | " + " | ".join(f"buffer {b}" for b in doc["buffers"]) + " |")
        print("|---|" + "---|" * len(doc["buffers"]))
        for cv in doc["cvs"]:
            cells = []
            for b in doc["buffers"]:
                g = next(x for x in line["grid"] if x["cv"] == cv and x["buffer"] == b)
                cells.append(f"{100 * g['actual_over_paper_mean']:.1f}% ({100 * g['actual_over_paper_min']:.1f}-{100 * g['actual_over_paper_max']:.1f})")
            print(f"| {cv} | " + " | ".join(cells) + " |")
        print()
        r = line["reference_point"]
        print(f"reference point cv={r['cv']}, buffer={r['buffer']}, seed {r['seed']}: actual {r['actual_uph']:.1f} uph vs paper {r['paper_uph']:.1f} "
              f"(bottleneck rate {r['bottleneck_uph']:.1f}), upph {r['actual_upph']:.2f} vs {r['paper_upph']:.2f} paper, "
              f"mean utilization {100 * r['mean_utilization']:.1f}%, oee {100 * r['oee']['oee']:.1f}% "
              f"(availability {r['oee']['availability']}, performance {100 * r['oee']['performance']:.1f}%, quality {r['oee']['quality']}).")
        print()
        print("| station | load | utilization | starved | blocked |")
        print("|---|---|---|---|---|")
        for k in range(r["stations"]):
            print(f"| {k + 1} | {r['loads'][k]} | {100 * r['utilization'][k]:.1f}% | {100 * r['starved'][k]:.1f}% | {100 * r['blocked'][k]:.1f}% |")
        print()


def agent_tables(out_dir):
    files = sorted(out_dir.glob("agent-*.json"))
    if not files:
        return
    print("| model | feasible | mean gap when feasible | matched optimum | beats rpw | ties rpw | loses to rpw | failure modes | mean latency |")
    print("|---|---|---|---|---|---|---|---|---|")
    for f in files:
        d = json.loads(f.read_text())
        if "summary" not in d:
            print(f"| {d['model']} | (run incomplete: {len(d['scenarios'])} scenarios) |")
            continue
        s = d["summary"]
        fm = ", ".join(f"{k} {v}" for k, v in sorted(s["failure_modes"].items(), key=lambda kv: -kv[1])) or "-"
        gap = f"{s['gap_mean_pct']:.1f}%" if s["gap_mean_pct"] is not None else "-"
        print(f"| {d['model']}{' (thinking ' + str(d['thinking']) + ')' if d.get('thinking') else ''} | {s['feasible']}/{s['scenarios']} | {gap} | "
              f"{s['matched_optimum']}/{s['feasible']} | {s['beats_rpw']} | {s['ties_rpw']} | {s['loses_to_rpw']} | {fm} | {s['latency_mean_s']:.0f} s |")
    print()
    for f in files:
        d = json.loads(f.read_text())
        if "summary" in d:
            bk = d["summary"]["by_kind"]
            print(f"{d['model']} feasibility by change type: " + ", ".join(f"{k} {v['feasible']}/{v['total']}" for k, v in bk.items())
                  + f"; rpw was beatable (rpw > optimum) in {d['summary']['rpw_beatable']} scenarios.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    out_dir = Path(__file__).resolve().parents[1] / "results" / args.label
    benchmark_tables(out_dir)
    comsoal_table(out_dir)
    sim_tables(out_dir)
    agent_tables(out_dir)


if __name__ == "__main__":
    main()
