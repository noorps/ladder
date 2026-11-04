"""ranked positional weight (helgeson and birnie, 1961).

positional weight of a task = its own time plus the times of every task that must come
after it. tasks are considered in descending weight; a station is filled with the
highest weight task whose predecessors are all already assigned and which still fits,
until nothing fits, then the next station opens.
"""
import time

from ladder.solvers import finish, salbp2_by_search


def positional_weights(inst):
    return [inst.times[i] + sum(inst.times[j] for j in inst.all_succs[i]) for i in range(inst.n)]


def solve_salbp1(inst, cycle_time, **_):
    t0 = time.perf_counter()
    if max(inst.times) > cycle_time:
        raise ValueError(f"{inst.name}: task time {max(inst.times)} exceeds cycle time {cycle_time}")
    w = positional_weights(inst)
    ranked = sorted(range(inst.n), key=lambda i: (-w[i], i))
    station_of = [-1] * inst.n
    unassigned = set(range(inst.n))
    k, room = 0, cycle_time
    while unassigned:
        placed = False
        for i in ranked:
            if i in unassigned and inst.times[i] <= room and all(station_of[p] >= 0 for p in inst.preds[i]):
                station_of[i] = k
                room -= inst.times[i]
                unassigned.discard(i)
                placed = True
                break
        if not placed:
            k += 1
            room = cycle_time
    return finish("rpw", inst, station_of, cycle_time, t0)


def solve_salbp2(inst, m, **_):
    return salbp2_by_search(solve_salbp1, inst, m)
