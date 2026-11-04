"""the one validator every solution goes through before any number is reported.

an assignment is a list station_of[i] in 0..m-1 for each task i. it is valid when
  - every task is assigned to exactly one station,
  - stations 0..m-1 are all non-empty (no gaps),
  - for every arc i -> j, station_of[i] <= station_of[j],
  - every station load is <= the cycle time.
anything else raises InfeasibleSolution, which callers are expected not to catch.
"""
from dataclasses import dataclass


class InfeasibleSolution(Exception):
    pass


@dataclass(frozen=True)
class Validated:
    stations: int
    cycle_time: int
    loads: tuple


def validate(inst, station_of, cycle_time):
    n = inst.n
    if len(station_of) != n:
        raise InfeasibleSolution(f"{inst.name}: {len(station_of)} assignments for {n} tasks")
    for i, k in enumerate(station_of):
        if not isinstance(k, int) or k < 0:
            raise InfeasibleSolution(f"{inst.name}: task {i + 1} has bad station {k!r}")
    m = max(station_of) + 1
    loads = [0] * m
    for i, k in enumerate(station_of):
        loads[k] += inst.times[i]
    for k, load in enumerate(loads):
        if load == 0:
            raise InfeasibleSolution(f"{inst.name}: station {k + 1} is empty")
        if load > cycle_time:
            raise InfeasibleSolution(f"{inst.name}: station {k + 1} load {load} > cycle time {cycle_time}")
    for j in range(n):
        for i in inst.preds[j]:
            if station_of[i] > station_of[j]:
                raise InfeasibleSolution(
                    f"{inst.name}: task {j + 1} at station {station_of[j] + 1} but its predecessor "
                    f"task {i + 1} is at station {station_of[i] + 1}")
    return Validated(m, cycle_time, tuple(loads))


def explain(inst, station_of, cycle_time):
    """like validate but returns a list of human readable problems instead of raising."""
    problems = []
    n = inst.n
    if len(station_of) != n:
        return [f"{len(station_of)} assignments for {n} tasks"]
    m = max(station_of) + 1
    loads = [0] * m
    for i, k in enumerate(station_of):
        loads[k] += inst.times[i]
    for k, load in enumerate(loads):
        if load == 0:
            problems.append(f"station {k + 1} is empty")
        if load > cycle_time:
            problems.append(f"station {k + 1} load {load} exceeds cycle time {cycle_time}")
    for j in range(n):
        for i in inst.preds[j]:
            if station_of[i] > station_of[j]:
                problems.append(f"task {j + 1} (station {station_of[j] + 1}) precedes its own predecessor "
                                f"task {i + 1} (station {station_of[i] + 1})")
    return problems
