"""fixed line change scenarios for the agent experiment, generated once with a seed and
committed as scenarios.json so every run scores the same 36 cases.

each scenario starts from a published scholl graph at one of its published cycle times,
with the rpw balance as the line's current state, and applies one change:
  fixture     a long task gets faster (a second fixture, a better tool)
  added_step  a task gets slower (an inline check was added)
  takt        the cycle time moves (demand went up or down)
  precedence  a new ordering constraint appears between two unrelated tasks
the modified instance is stored in full; the prompt only gets the change in prose.
"""
import json
import random
from pathlib import Path

from ladder.instance import Instance, load_scholl_graph
from ladder.metrics import station_loads
from ladder.solvers import exact, rpw

GRAPHS = ["Mitchell", "Roszieg", "Heskiaoff", "Buxey", "Sawyer", "Lutz1", "Gunther", "Kilbridge", "Hahn"]
TYPES = ["fixture", "added_step", "takt", "precedence"]
FIXTURES = ["screw-fastening fixture", "press station", "torque gun", "pick-and-place arm", "glue dispenser"]
HERE = Path(__file__).resolve().parent


def published_cycle_times(graph):
    rows = json.loads((HERE.parents[1] / "data" / "optima" / "scholl1993_salbp1.json").read_text())
    return sorted(r["c"] for r in rows if r["graph"] == graph)


def make_change(kind, inst, c, base, rng):
    """returns (modified instance, new cycle time, prose)."""
    times = list(inst.times)
    preds = [list(p) for p in inst.preds]
    loads = station_loads(inst, base.assignment)
    if kind == "fixture":
        k = max(range(len(loads)), key=lambda s: loads[s])
        on_k = [i for i in range(inst.n) if base.assignment[i] == k]
        i = max(on_k, key=lambda t: times[t])
        new = max(1, round(times[i] * rng.uniform(0.45, 0.65)))
        times[i] = new
        text = (f"station {k + 1} is the bottleneck. we are adding a second {rng.choice(FIXTURES)} for "
                f"task {i + 1}, so task {i + 1} drops from {inst.times[i]} to {new}.")
        return Instance(inst.name, times, preds), c, text
    if kind == "added_step":
        cands = [i for i in range(inst.n) if times[i] * 1.6 <= c]
        i = rng.choice(cands)
        new = min(c, max(times[i] + 1, round(times[i] * rng.uniform(1.3, 1.6))))
        times[i] = new
        text = (f"quality found a defect that traces back to task {i + 1}. an inline check was added to it, "
                f"so task {i + 1} goes from {inst.times[i]} to {new}.")
        return Instance(inst.name, times, preds), c, text
    if kind == "takt":
        if rng.random() < 0.5:
            new_c = max(max(times), round(c * 0.88))
            text = f"demand went up. the takt drops from {c} to {new_c}. same tasks, same times."
        else:
            new_c = round(c * 1.18)
            text = f"demand went down. the takt rises from {c} to {new_c}. same tasks, same times."
        return Instance(inst.name, times, preds), new_c, text
    if kind == "precedence":
        pairs = [(i, j) for i in range(inst.n) for j in range(inst.n)
                 if i != j and j not in inst.all_succs[i] and j not in inst.all_preds[i]]
        # prefer a pair the current balance does not already respect, so a rebalance is forced
        forced = [(i, j) for i, j in pairs if base.assignment[i] > base.assignment[j]]
        i, j = rng.choice(forced or pairs)
        preds[j].append(i)
        text = (f"engineering changed the build sequence: task {j + 1} now has to happen after task {i + 1} "
                f"(task {i + 1} seals an area that task {j + 1} would otherwise block). nothing else changes.")
        return Instance(inst.name, times, preds), c, text
    raise KeyError(kind)


def build(seed=7):
    rng = random.Random(seed)
    out = []
    for g in GRAPHS:
        inst = load_scholl_graph(g)
        cts = published_cycle_times(g)
        c = cts[len(cts) // 2]
        base = rpw.solve_salbp1(inst, c)
        for kind in TYPES:
            mod, new_c, text = make_change(kind, inst, c, base, rng)
            mod_rpw = rpw.solve_salbp1(mod, new_c)
            opt = exact.solve_salbp1(mod, new_c, time_limit=120)
            if not opt.proven:
                raise RuntimeError(f"optimum not proven for {g}/{kind}")
            out.append({
                "id": f"{g.lower()}-{kind}", "graph": g, "kind": kind, "n": inst.n,
                "base_cycle_time": c, "base_times": inst.times,
                "base_preds": [[p + 1 for p in ps] for ps in inst.preds],
                "base_assignment": base.assignment, "base_stations": base.stations,
                "change": text,
                "cycle_time": new_c, "times": mod.times,
                "preds": [[p + 1 for p in ps] for ps in mod.preds],
                "rpw_stations": mod_rpw.stations, "rpw_assignment": mod_rpw.assignment,
                "optimal_stations": opt.stations, "optimal_assignment": opt.assignment,
                "lb_stations": mod.lb_stations(new_c),
            })
            print(f"{out[-1]['id']}: c {c}->{new_c} rpw {base.stations}->{mod_rpw.stations} opt {opt.stations}  {text}")
    return out


def load():
    return json.loads((HERE / "scenarios.json").read_text())


def modified_instance(s):
    return Instance(s["id"], s["times"], [[p - 1 for p in ps] for ps in s["preds"]], s["cycle_time"])


if __name__ == "__main__":
    scen = build()
    (HERE / "scenarios.json").write_text(json.dumps(scen, indent=0))
    print(len(scen), "scenarios written")
