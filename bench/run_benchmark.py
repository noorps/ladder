"""run every solver over the chosen instance sets and write one json.

per instance: value (stations for salbp-1, cycle time for salbp-2), gap to the published
best known value, whether it matched the published optimum, median solve time over
repeats, line efficiency, smoothness index, and for cp-sat whether optimality was proven.
"""
import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ladder import env
from ladder.instance import instance_set
from ladder.metrics import gap_pct, summary
from ladder.solvers import comsoal, exact, rpw

SOLVERS = {"rpw": rpw, "comsoal": comsoal, "cpsat": exact}
SALBP2_SETS = {"scholl-salbp2", "scholl-salbp2-all"}


def run_one(mod, name, inst, problem, repeats, kw):
    times, res = [], None
    for r in range(repeats):
        t0 = time.perf_counter()
        if problem == 1:
            out = mod.solve_salbp1(inst, inst.cycle_time, **kw)
        else:
            out = mod.solve_salbp2(inst, inst.published["m"], **kw)
        times.append(time.perf_counter() - t0)
        if res is None:
            res = out
    value = res.stations if problem == 1 else res.cycle_time
    pub = inst.published
    best_known = pub["optimum"] if pub["optimum"] is not None else pub["ub"]
    s = summary(inst, res.assignment, res.cycle_time)
    rec = {
        "value": value,
        "gap_pct": gap_pct(value, best_known),
        "matched_optimum": (pub["optimum"] is not None and value == pub["optimum"]),
        "matched_best_known": value == best_known,
        "below_best_known": value < best_known,
        "time_median": statistics.median(times),
        "time_min": min(times),
        "time_max": max(times),
        "repeats": repeats,
        "line_efficiency": s["line_efficiency"],
        "smoothness_index": s["smoothness_index"],
        "stations": s["stations"],
        "cycle_time": res.cycle_time,
        "assignment": res.assignment,
    }
    if name == "cpsat":
        rec["proven"] = res.proven
        rec["status"] = res.extra["status"]
        rec["bound"] = res.extra["bound"]
    if name == "comsoal":
        rec["trials_used"] = res.extra["trials_used"]
    return rec


def aggregate(records, problem):
    agg = {}
    for name in SOLVERS:
        rs = [r["solvers"][name] for r in records if name in r["solvers"]]
        if not rs:
            continue
        gaps = [r["gap_pct"] for r in rs if r["gap_pct"] is not None]
        known = [r for r, rec in zip(rs, records) if rec["published"]["optimum"] is not None]
        a = {
            "instances": len(rs),
            "with_known_optimum": len(known),
            "matched_optimum": sum(r["matched_optimum"] for r in rs),
            "matched_best_known": sum(r["matched_best_known"] for r in rs),
            "below_best_known": sum(r["below_best_known"] for r in rs),
            "gap_mean_pct": statistics.fmean(gaps) if gaps else None,
            "gap_median_pct": statistics.median(gaps) if gaps else None,
            "gap_max_pct": max(gaps) if gaps else None,
            "time_mean_s": statistics.fmean(r["time_median"] for r in rs),
            "time_median_s": statistics.median(r["time_median"] for r in rs),
            "time_max_s": max(r["time_median"] for r in rs),
            "efficiency_mean": statistics.fmean(r["line_efficiency"] for r in rs),
            "smoothness_mean": statistics.fmean(r["smoothness_index"] for r in rs),
        }
        if name == "cpsat":
            a["proven"] = sum(1 for r in rs if r["proven"])
            a["time_limit_hit"] = sum(1 for r in rs if not r["proven"])
        agg[name] = a
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--sets", nargs="+", default=["scholl-salbp1", "scholl-salbp2", "otto-n20", "otto-n50", "otto-n100"])
    ap.add_argument("--sample", type=int, default=40, help="otto instances per size (seeded sample)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=3, help="timing repeats for the heuristics")
    ap.add_argument("--exact-repeats", type=int, default=1, help="timing repeats for cp-sat")
    ap.add_argument("--time-limit", type=float, default=10.0, help="cp-sat seconds per instance")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--comsoal-trials", type=int, default=500)
    ap.add_argument("--solvers", nargs="+", default=list(SOLVERS))
    ap.add_argument("--limit", type=int, default=None, help="only the first k instances of each set (smoke test)")
    args = ap.parse_args()

    out_dir = Path(__file__).resolve().parents[1] / "results" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "label": args.label,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "env": env.stamp(),
        "config": vars(args),
        "sets": {},
    }
    t_start = time.perf_counter()
    for set_name in args.sets:
        problem = 2 if set_name in SALBP2_SETS else 1
        insts = instance_set(set_name, sample=args.sample, seed=args.seed)
        if args.limit:
            insts = insts[: args.limit]
        records = []
        for idx, inst in enumerate(insts):
            rec = {"name": inst.name, "n": inst.n, "problem": problem, "published": inst.published,
                   "cycle_time": inst.cycle_time, "m": inst.published.get("m"), "solvers": {}}
            hint = None
            for name in args.solvers:
                mod = SOLVERS[name]
                kw = {}
                if name == "comsoal":
                    kw = {"trials": args.comsoal_trials, "seed": args.seed}
                if name == "cpsat":
                    kw = {"time_limit": args.time_limit, "workers": args.workers, "seed": args.seed}
                rec["solvers"][name] = run_one(mod, name, inst, problem, args.exact_repeats if name == "cpsat" else args.repeats, kw)
            records.append(rec)
            line = " ".join(f"{k}={v['value']}" for k, v in rec["solvers"].items())
            best = inst.published["optimum"] if inst.published["optimum"] is not None else f"[{inst.published['lb']},{inst.published['ub']}]"
            print(f"[{set_name} {idx + 1}/{len(insts)}] {inst.name} n={inst.n} best={best} {line}"
                  + (f" proven={rec['solvers']['cpsat']['proven']} {rec['solvers']['cpsat']['time_median']:.2f}s" if "cpsat" in rec["solvers"] else ""),
                  flush=True)
        doc["sets"][set_name] = {"problem": problem, "instances": records, "aggregate": aggregate(records, problem)}
        (out_dir / "benchmark.json").write_text(json.dumps(doc, indent=1))
    doc["elapsed_s"] = time.perf_counter() - t_start
    doc["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out_dir / "benchmark.json").write_text(json.dumps(doc, indent=1))
    for set_name, s in doc["sets"].items():
        print(set_name)
        for name, a in s["aggregate"].items():
            print(f"  {name:8s} gap mean {a['gap_mean_pct']:.2f}%  matched optimum {a['matched_optimum']}/{a['with_known_optimum']}"
                  f"  time median {a['time_median_s']:.3f}s" + (f"  proven {a['proven']}/{a['instances']}" if name == "cpsat" else ""))


if __name__ == "__main__":
    main()
