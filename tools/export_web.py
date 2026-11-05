"""export what the browser demo needs: the sawyer instance, cp-sat proven optima at a few
cycle times, and the simulator cross-check grid (python numbers, then js numbers from node)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ladder.instance import load_scholl_graph
from ladder.metrics import station_loads, summary
from ladder.sim import simulate
from ladder.solvers import exact, rpw

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "data"
CYCLE_TIMES = [30, 36, 41, 47]
CHECK_CVS = [0.0, 0.1, 0.3, 0.5, 1.0]
CHECK_BUFFERS = [0, 1, 2, 8]
CHECK_SEED, CHECK_WARMUP, CHECK_UNITS = 1, 300, 3000


def main():
    WEB.mkdir(parents=True, exist_ok=True)
    inst = load_scholl_graph("Sawyer")
    instance = {"name": "sawyer", "source": "scholl (1993) precedence graph SAWYER30, assembly-line-balancing.de",
                "n": inst.n, "total_time": inst.total_time,
                "tasks": [{"id": i + 1, "time": inst.times[i], "preds": [p + 1 for p in inst.preds[i]]} for i in range(inst.n)]}
    optimal = {"instance": "sawyer", "solver": "or-tools cp-sat", "balances": []}
    for c in CYCLE_TIMES:
        r = exact.solve_salbp1(inst, c, time_limit=120)
        if not r.proven:
            raise RuntimeError(f"not proven at c={c}")
        s = summary(inst, r.assignment, c)
        h = rpw.solve_salbp1(inst, c)
        optimal["balances"].append({"cycle_time": c, "stations": r.stations, "proven": True,
                                    "assignment": [k + 1 for k in r.assignment], "loads": s["loads"],
                                    "line_efficiency": s["line_efficiency"], "smoothness_index": s["smoothness_index"],
                                    "rpw_stations": h.stations, "rpw_assignment": [k + 1 for k in h.assignment]})
        print(f"c={c}: optimal {r.stations} stations, rpw {h.stations}")
    (WEB / "instance.json").write_text(json.dumps(instance, indent=1))
    (WEB / "optimal.json").write_text(json.dumps(optimal, indent=1))

    # cross-check grid on the c=30 optimal balance
    loads = optimal["balances"][0]["loads"]
    grid = []
    for cv in CHECK_CVS:
        for b in CHECK_BUFFERS:
            r = simulate(loads, cv, b, seed=CHECK_SEED, warmup=CHECK_WARMUP, units=CHECK_UNITS)
            grid.append({"cv": cv, "buffer": b, "python_throughput": r["throughput"],
                         "python_utilization": [s["busy"] for s in r["stations"]]})
            print(f"python cv={cv} b={b}: {3600 * r['throughput']:.3f} uph")
    check = {"loads": loads, "cycle_time": 30, "seed": CHECK_SEED, "warmup": CHECK_WARMUP, "units": CHECK_UNITS,
             "tolerance": 0.02, "grid": grid}
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, str(ROOT / "web" / "sim_check.js"), json.dumps(check)], capture_output=True, text=True, check=True)
        js = json.loads(out.stdout)
        worst = 0.0
        for cell, j in zip(grid, js):
            cell["js_throughput"] = j["throughput"]
            cell["js_utilization"] = j["utilization"]
            cell["rel_diff"] = abs(j["throughput"] - cell["python_throughput"]) / cell["python_throughput"]
            worst = max(worst, cell["rel_diff"])
            print(f"js     cv={cell['cv']} b={cell['buffer']}: {3600 * j['throughput']:.3f} uph  rel diff {cell['rel_diff']:.2e}")
        check["worst_rel_diff"] = worst
        check["node"] = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        if worst > check["tolerance"]:
            raise SystemExit(f"js simulator disagrees with python by {100 * worst:.2f}%")
    else:
        print("node not found, js side of the cross-check not run")
    (WEB / "sim_check.json").write_text(json.dumps(check, indent=1))
    # the same data as a script so the page works from file:// where fetch() is blocked
    (WEB / "data.js").write_text("window.LADDER_DATA = " + json.dumps({"instance": instance, "optimal": optimal,
                                                                           "sim_check": {k: v for k, v in check.items() if k != "grid"}}) + ";\n")


if __name__ == "__main__":
    main()
