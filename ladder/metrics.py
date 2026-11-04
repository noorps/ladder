"""line metrics computed from a validated assignment."""
import math


def station_loads(inst, station_of):
    m = max(station_of) + 1
    loads = [0] * m
    for i, k in enumerate(station_of):
        loads[k] += inst.times[i]
    return loads


def line_efficiency(inst, loads, cycle_time):
    """total task time / (stations * cycle time)."""
    return inst.total_time / (len(loads) * cycle_time)


def balance_delay(inst, loads, cycle_time):
    return 1.0 - line_efficiency(inst, loads, cycle_time)


def smoothness_index(loads):
    """sqrt(sum over stations of (max load - load)^2). zero means perfectly level."""
    mx = max(loads)
    return math.sqrt(sum((mx - l) ** 2 for l in loads))


def paper_uph(cycle_time):
    """units per hour the paced line promises, treating task times as seconds."""
    return 3600.0 / cycle_time


def summary(inst, station_of, cycle_time):
    loads = station_loads(inst, station_of)
    return {
        "stations": len(loads),
        "cycle_time": cycle_time,
        "loads": loads,
        "max_load": max(loads),
        "line_efficiency": line_efficiency(inst, loads, cycle_time),
        "smoothness_index": smoothness_index(loads),
        "paper_uph": paper_uph(cycle_time),
    }


def gap_pct(value, best):
    """percentage above the published best value (0 means matched it)."""
    if best is None or best == 0:
        return None
    return 100.0 * (value - best) / best
