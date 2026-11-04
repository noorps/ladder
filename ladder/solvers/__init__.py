"""solvers share one result type and one way of turning a salbp-1 routine into a salbp-2 one."""
import time
from dataclasses import dataclass, field

from ladder.validate import validate


@dataclass
class Result:
    solver: str
    assignment: list          # station index per task, 0-based
    stations: int
    cycle_time: int
    seconds: float
    proven: bool = None       # exact solver only: did it prove optimality
    extra: dict = field(default_factory=dict)


def finish(solver, inst, assignment, cycle_time, t0, proven=None, **extra):
    """validate, then wrap. validation failure raises; nothing unvalidated leaves a solver."""
    v = validate(inst, assignment, cycle_time)
    return Result(solver, list(assignment), v.stations, cycle_time, time.perf_counter() - t0, proven, extra)


def salbp2_by_search(solve1, inst, m, **kw):
    """salbp-2 for a constructive heuristic: find the smallest cycle time at which the
    heuristic needs at most m stations. the heuristic is not monotone in c, so this is a
    bisection on [lb, sum t] followed by a downward linear sweep from the bisection answer
    as long as the heuristic keeps succeeding."""
    t0 = time.perf_counter()
    lo, hi = inst.lb_cycle_time(m), inst.total_time
    best = None
    while lo < hi:
        mid = (lo + hi) // 2
        r = solve1(inst, mid, **kw)
        if r.stations <= m:
            best, hi = r, mid
        else:
            lo = mid + 1
    if best is None or best.cycle_time != lo:
        best = solve1(inst, lo, **kw)
        if best.stations > m:
            # bisection landed on an infeasible c because of non-monotonicity; walk up
            c = lo
            while best.stations > m:
                c += 1
                best = solve1(inst, c, **kw)
    # tighten: the achieved cycle time is the max station load, which may sit below c
    c = max(sum(inst.times[i] for i in range(inst.n) if best.assignment[i] == k) for k in range(best.stations))
    probe = c - 1
    while probe >= inst.lb_cycle_time(m):
        r = solve1(inst, probe, **kw)
        if r.stations > m:
            break
        best = r
        c = max(sum(inst.times[i] for i in range(inst.n) if r.assignment[i] == k) for k in range(r.stations))
        probe = c - 1
    return finish(best.solver, inst, best.assignment, c, t0, **best.extra)
