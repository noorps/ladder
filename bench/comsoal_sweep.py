"""how comsoal quality moves with the number of trials: one traced run of n_max trials per
instance gives the best station count after every trial, so every smaller n is read off
the same run."""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ladder import env
from ladder.instance import instance_set
from ladder.solvers import comsoal

NS = [1, 3, 10, 30, 100, 300, 1000, 3000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--sets", nargs="+", default=["otto-n20", "otto-n50", "otto-n100"])
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--trials", type=int, default=NS[-1])
    args = ap.parse_args()
    out_dir = Path(__file__).resolve().parents[1] / "results" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"label": args.label, "env": env.stamp(), "config": vars(args), "ns": NS, "sets": {}}
    for set_name in args.sets:
        insts = [i for i in instance_set(set_name, sample=args.sample, seed=args.seed) if i.published["optimum"] is not None]
        per = []
        for inst in insts:
            r = comsoal.solve_salbp1(inst, inst.cycle_time, trials=args.trials, seed=args.seed, trace=True)
            curve = r.extra["best_by_trial"]
            opt = inst.published["optimum"]
            per.append({"name": inst.name, "optimum": opt,
                        "stations_at_n": {n: curve[n - 1] for n in NS if n <= args.trials},
                        "gap_at_n": {n: 100.0 * (curve[n - 1] - opt) / opt for n in NS if n <= args.trials}})
            print(f"{set_name} {inst.name}: opt {opt} " + " ".join(f"n{n}={curve[n - 1]}" for n in NS if n <= args.trials), flush=True)
        agg = {n: {"gap_mean_pct": statistics.fmean(p["gap_at_n"][n] for p in per),
                   "matched_optimum": sum(1 for p in per if p["stations_at_n"][n] == p["optimum"]),
                   "instances": len(per)} for n in NS if n <= args.trials}
        doc["sets"][set_name] = {"instances": per, "aggregate": agg}
        (out_dir / "comsoal_sweep.json").write_text(json.dumps(doc, indent=1))
    for set_name, s in doc["sets"].items():
        print(set_name, " ".join(f"n{n}:{a['gap_mean_pct']:.2f}%/{a['matched_optimum']}" for n, a in s["aggregate"].items()))


if __name__ == "__main__":
    main()
