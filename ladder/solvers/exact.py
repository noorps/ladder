"""exact solver on or-tools cp-sat.

salbp-1: binary x[i,k] (task i at station k), y[k] (station k open), minimise sum y.
salbp-2: binary x[i,k] over a fixed m stations, integer c, minimise c.
station windows [e_i, l_i] from the usual head/tail bounds shrink the model a lot, and a
heuristic solution is passed in as a hint and as the upper bound on the station count.
`proven` is True only when cp-sat reports OPTIMAL within the time limit.
"""
import math
import time

from ortools.sat.python import cp_model

from ladder.solvers import finish
from ladder.solvers import rpw


def _windows(inst, c, m):
    """earliest and latest station (0-based) each task can sit in with m stations of size c."""
    e, l = [], []
    for i in range(inst.n):
        head = inst.times[i] + sum(inst.times[p] for p in inst.all_preds[i])
        tail = inst.times[i] + sum(inst.times[s] for s in inst.all_succs[i])
        e.append(math.ceil(head / c) - 1)
        l.append(m - math.ceil(tail / c))
    return e, l


def _compact(station_of):
    used = sorted(set(station_of))
    remap = {k: j for j, k in enumerate(used)}
    return [remap[k] for k in station_of]


def _solver(time_limit, workers, seed):
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = time_limit
    s.parameters.num_workers = workers
    s.parameters.random_seed = seed
    return s


def solve_salbp1(inst, cycle_time, time_limit=10.0, workers=8, seed=0, hint=None, **_):
    t0 = time.perf_counter()
    hint = hint or rpw.solve_salbp1(inst, cycle_time)
    ub = hint.stations
    lb = inst.lb_stations(cycle_time)
    e, l = _windows(inst, cycle_time, ub)
    model = cp_model.CpModel()
    x = {}
    for i in range(inst.n):
        for k in range(e[i], l[i] + 1):
            x[i, k] = model.NewBoolVar(f"x{i}_{k}")
        model.AddExactlyOne(x[i, k] for k in range(e[i], l[i] + 1))
    y = [model.NewBoolVar(f"y{k}") for k in range(ub)]
    for k in range(ub):
        terms = [(i, x[i, k]) for i in range(inst.n) if (i, k) in x]
        model.Add(sum(inst.times[i] * v for i, v in terms) <= cycle_time * y[k])
        if k + 1 < ub:
            model.Add(y[k] >= y[k + 1])
    for j in range(inst.n):
        for i in inst.preds[j]:
            model.Add(sum(k * x[i, k] for k in range(e[i], l[i] + 1))
                      <= sum(k * x[j, k] for k in range(e[j], l[j] + 1)))
    model.Add(sum(y) >= lb)
    model.Minimize(sum(y))
    for i, k in enumerate(hint.assignment):
        for kk in range(e[i], l[i] + 1):
            model.AddHint(x[i, kk], int(kk == k))
    for k in range(ub):
        model.AddHint(y[k], 1)
    solver = _solver(time_limit, workers, seed)
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"{inst.name}: cp-sat returned {name} despite a feasible hint")
    station_of = _compact([next(k for k in range(e[i], l[i] + 1) if solver.Value(x[i, k])) for i in range(inst.n)])
    return finish("cpsat", inst, station_of, cycle_time, t0, proven=(status == cp_model.OPTIMAL),
                  status=name, bound=int(round(solver.BestObjectiveBound())), heuristic_ub=ub, lb1=lb,
                  solver_wall=solver.WallTime())


def solve_salbp2(inst, m, time_limit=10.0, workers=8, seed=0, hint=None, **_):
    t0 = time.perf_counter()
    hint = hint or rpw.solve_salbp2(inst, m)
    c_ub = hint.cycle_time
    c_lb = inst.lb_cycle_time(m)
    e, l = _windows(inst, c_ub, m)
    model = cp_model.CpModel()
    x = {}
    for i in range(inst.n):
        for k in range(e[i], l[i] + 1):
            x[i, k] = model.NewBoolVar(f"x{i}_{k}")
        model.AddExactlyOne(x[i, k] for k in range(e[i], l[i] + 1))
    c = model.NewIntVar(c_lb, c_ub, "c")
    for k in range(m):
        terms = [(i, x[i, k]) for i in range(inst.n) if (i, k) in x]
        model.Add(sum(inst.times[i] * v for i, v in terms) <= c)
    for j in range(inst.n):
        for i in inst.preds[j]:
            model.Add(sum(k * x[i, k] for k in range(e[i], l[i] + 1))
                      <= sum(k * x[j, k] for k in range(e[j], l[j] + 1)))
    model.Minimize(c)
    for i, k in enumerate(hint.assignment):
        for kk in range(e[i], l[i] + 1):
            model.AddHint(x[i, kk], int(kk == k))
    model.AddHint(c, c_ub)
    solver = _solver(time_limit, workers, seed)
    status = solver.Solve(model)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"{inst.name}: cp-sat returned {name} despite a feasible hint")
    station_of = _compact([next(k for k in range(e[i], l[i] + 1) if solver.Value(x[i, k])) for i in range(inst.n)])
    achieved = int(solver.Value(c))
    return finish("cpsat", inst, station_of, achieved, t0, proven=(status == cp_model.OPTIMAL),
                  status=name, bound=int(round(solver.BestObjectiveBound())), heuristic_ub=c_ub, lb=c_lb,
                  solver_wall=solver.WallTime())
