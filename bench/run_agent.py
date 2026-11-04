"""score an llm's rebalances over the fixed scenarios: feasibility rate, gap to the cp-sat
optimum when feasible, and how often it beats rpw on the same changed line."""
import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ladder.agent import rebalance, scenarios
from ladder.metrics import summary
from ladder.validate import validate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default="command-a-plus-05-2026")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--thinking", default=None, help="'off', a token budget, or unset for the model default")
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    out_dir = Path(__file__).resolve().parents[1] / "results" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    scen = scenarios.load()[: args.limit]
    tag = f"{args.model}-think{args.thinking}" if args.thinking else args.model
    doc = {"label": args.label, "model": args.model, "thinking": args.thinking, "temperature": args.temperature,
           "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "scenarios": []}
    for s in scen:
        inst = scenarios.modified_instance(s)
        prompt = rebalance.describe(s)
        text, latency, meta = rebalance.ask(args.model, prompt, args.temperature, args.max_tokens, thinking=args.thinking)
        assignment, failure = rebalance.parse(text, s["n"])
        rec = {"id": s["id"], "kind": s["kind"], "n": s["n"], "cycle_time": s["cycle_time"],
               "rpw_stations": s["rpw_stations"], "optimal_stations": s["optimal_stations"],
               "latency_s": latency, "raw": text, "meta": meta, "failure": failure, "problems": []}
        if assignment is not None:
            failure, problems = rebalance.classify(inst, assignment, s["cycle_time"])
            rec["failure"] = failure
            rec["problems"] = problems[:5]
            rec["assignment"] = assignment
        if rec["failure"] is None:
            v = validate(inst, assignment, s["cycle_time"])  # the real check, raises if wrong
            m = v.stations
            sm = summary(inst, assignment, s["cycle_time"])
            rec.update({"feasible": True, "stations": m,
                        "gap_pct": 100.0 * (m - s["optimal_stations"]) / s["optimal_stations"],
                        "vs_rpw": "beats" if m < s["rpw_stations"] else ("ties" if m == s["rpw_stations"] else "loses"),
                        "line_efficiency": sm["line_efficiency"], "smoothness_index": sm["smoothness_index"]})
        else:
            rec["feasible"] = False
        doc["scenarios"].append(rec)
        print(f"{s['id']:28s} {'ok' if rec['feasible'] else 'FAIL ' + str(rec['failure']):28s}"
              + (f" stations {rec['stations']} opt {s['optimal_stations']} rpw {s['rpw_stations']} {rec['vs_rpw']}" if rec["feasible"] else "")
              + f"  {latency:.1f}s", flush=True)
        (out_dir / f"agent-{tag}.json").write_text(json.dumps(doc, indent=1))
    feas = [r for r in doc["scenarios"] if r["feasible"]]
    doc["summary"] = {
        "scenarios": len(doc["scenarios"]),
        "feasible": len(feas),
        "feasibility_rate": len(feas) / len(doc["scenarios"]),
        "gap_mean_pct": statistics.fmean(r["gap_pct"] for r in feas) if feas else None,
        "gap_median_pct": statistics.median(r["gap_pct"] for r in feas) if feas else None,
        "matched_optimum": sum(1 for r in feas if r["stations"] == r["optimal_stations"]),
        "beats_rpw": sum(1 for r in feas if r["vs_rpw"] == "beats"),
        "ties_rpw": sum(1 for r in feas if r["vs_rpw"] == "ties"),
        "loses_to_rpw": sum(1 for r in feas if r["vs_rpw"] == "loses"),
        "rpw_beatable": sum(1 for r in doc["scenarios"] if r["rpw_stations"] > r["optimal_stations"]),
        "failure_modes": dict(Counter(r["failure"] for r in doc["scenarios"] if not r["feasible"])),
        "by_kind": {k: {"feasible": sum(1 for r in doc["scenarios"] if r["kind"] == k and r["feasible"]),
                        "total": sum(1 for r in doc["scenarios"] if r["kind"] == k)} for k in scenarios.TYPES},
        "latency_mean_s": statistics.fmean(r["latency_s"] for r in doc["scenarios"]),
    }
    doc["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out_dir / f"agent-{tag}.json").write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc["summary"], indent=1))


if __name__ == "__main__":
    main()
