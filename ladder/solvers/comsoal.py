"""comsoal (arcus, 1966): computer method of sequencing operations for assembly lines.

each trial builds a solution station by station. at every step the candidate list is
the set of unassigned tasks whose predecessors are all assigned and which fit in the
remaining station time; one is picked uniformly at random. with no candidate the next
station opens. n trials, keep the best (fewest stations, then lowest smoothness index).
"""
import math
import random
import time

from ladder.solvers import finish, salbp2_by_search


def _one_trial(inst, cycle_time, rng, times, preds):
    n = inst.n
    station_of = [-1] * n
    remaining_preds = [len(p) for p in preds]
    succs = inst.succs
    ready = [i for i in range(n) if remaining_preds[i] == 0]
    left = n
    k, room = 0, cycle_time
    while left:
        fit = [i for i in ready if times[i] <= room]
        if not fit:
            k += 1
            room = cycle_time
            continue
        i = fit[rng.randrange(len(fit))]
        station_of[i] = k
        room -= times[i]
        left -= 1
        ready.remove(i)
        for s in succs[i]:
            remaining_preds[s] -= 1
            if remaining_preds[s] == 0:
                ready.append(s)
    return station_of, k + 1


def _smoothness(inst, station_of, m):
    loads = [0] * m
    for i, k in enumerate(station_of):
        loads[k] += inst.times[i]
    mx = max(loads)
    return math.sqrt(sum((mx - l) ** 2 for l in loads))


def solve_salbp1(inst, cycle_time, trials=500, seed=0, trace=False, **_):
    """trace=True also records the best station count after each trial (for the n sweep)."""
    t0 = time.perf_counter()
    if max(inst.times) > cycle_time:
        raise ValueError(f"{inst.name}: task time {max(inst.times)} exceeds cycle time {cycle_time}")
    rng = random.Random(seed)
    times, preds = inst.times, inst.preds
    best, best_key = None, None
    curve = []
    lb = inst.lb_stations(cycle_time)
    for t in range(trials):
        sol, m = _one_trial(inst, cycle_time, rng, times, preds)
        if best is None or m < best_key[0]:
            key = (m, _smoothness(inst, sol, m))
            if best is None or key < best_key:
                best, best_key = sol, key
        elif m == best_key[0]:
            si = _smoothness(inst, sol, m)
            if si < best_key[1]:
                best, best_key = sol, (m, si)
        if trace:
            curve.append(best_key[0])
        if best_key[0] == lb and not trace:
            break  # already at the bound, more trials cannot help
    extra = {"trials": trials, "trials_used": t + 1}
    if trace:
        extra["best_by_trial"] = curve
    return finish("comsoal", inst, best, cycle_time, t0, **extra)


def solve_salbp2(inst, m, trials=500, seed=0, **_):
    return salbp2_by_search(solve_salbp1, inst, m, trials=trials, seed=seed)
