"""sweep coefficient of variation and buffer size on an optimal balance and record how far
simulated throughput falls below the paper rate."""
import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ladder import env
from ladder.instance import load_scholl_graph, otto2013
from ladder.metrics import station_loads
from ladder.sim import line_report
from ladder.solvers import exact

CVS = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]
BUFFERS = [0, 1, 2, 4, 8]


def balance(inst, c):
    r = exact.solve_salbp1(inst, c, time_limit=60)
    if not r.proven:
        raise RuntimeError(f"could not prove optimality for {inst.name} at c={c}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--units", type=int, default=5000)
    ap.add_argument("--warmup", type=int, default=500)
    ap.add_argument("--quick", action="store_true", help="smaller grid for a smoke test")
    args = ap.parse_args()
    out_dir = Path(__file__).resolve().parents[1] / "results" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    cvs, buffers = (CVS, BUFFERS) if not args.quick else ([0.0, 0.3, 1.0], [0, 2])

    lines = []
    saw = load_scholl_graph("Sawyer")
    lines.append(("Sawyer_c30", saw, 30))
    otto = otto2013(50, sample=None)[0]
    lines.append((otto.name + "_c1000", otto, 1000))

    doc = {"label": args.label, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "env": env.stamp(), "config": vars(args), "cvs": cvs, "buffers": buffers, "lines": []}
    t0 = time.perf_counter()
    for name, inst, c in lines:
        r = balance(inst, c)
        loads = station_loads(inst, r.assignment)
        entry = {"name": name, "n": inst.n, "cycle_time": c, "stations": r.stations, "loads": loads,
                 "assignment": r.assignment, "line_efficiency": inst.total_time / (r.stations * c),
                 "paper_uph": 3600.0 / c, "grid": [], "reference_point": None}
        for cv in cvs:
            for b in buffers:
                runs = [line_report(loads, c, cv, b, seed=s + 1, warmup=args.warmup, units=args.units)
                        for s in range(args.seeds)]
                ratios = [x["actual_over_paper"] for x in runs]
                cell = {"cv": cv, "buffer": b,
                        "actual_uph_mean": statistics.fmean(x["actual_uph"] for x in runs),
                        "actual_over_paper_mean": statistics.fmean(ratios),
                        "actual_over_paper_min": min(ratios), "actual_over_paper_max": max(ratios),
                        "mean_utilization": statistics.fmean(x["mean_utilization"] for x in runs),
                        "seeds": [x["seed"] for x in runs]}
                entry["grid"].append(cell)
                print(f"{name} cv={cv:<5} b={b}: actual/paper {cell['actual_over_paper_mean']:.3f} "
                      f"[{cell['actual_over_paper_min']:.3f},{cell['actual_over_paper_max']:.3f}]", flush=True)
        # one fully reported point for the readme (per-station blocked/starved, oee terms)
        entry["reference_point"] = line_report(loads, c, 0.3, 1, seed=1, warmup=args.warmup, units=args.units)
        entry["reference_point_cv0"] = line_report(loads, c, 0.0, 0, seed=1, warmup=args.warmup, units=args.units)
        doc["lines"].append(entry)
        (out_dir / "sim_sweep.json").write_text(json.dumps(doc, indent=1))
    doc["elapsed_s"] = time.perf_counter() - t0
    (out_dir / "sim_sweep.json").write_text(json.dumps(doc, indent=1))


if __name__ == "__main__":
    main()
