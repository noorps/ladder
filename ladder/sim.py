"""discrete event simulation of a balanced line on simpy.

the balance says each station takes its load every cycle. the simulator lets station
times vary (lognormal around the nominal load, cv a parameter), puts a finite buffer
between neighbouring stations, and lets stations block (downstream full) and starve
(upstream empty). the first station never starves and the last never blocks.

buffer b means b units can wait between two stations, not counting the unit each station
is working on. b = 0 is a direct hand off: the upstream station holds its finished unit
until the downstream station is free.
"""
from collections import deque

import simpy

from ladder.rng import LognormalDraw, station_seed

STARVED, BUSY, BLOCKED = 0, 1, 2


class Line:
    def __init__(self, env, loads, cv, buffer, seed, on_complete=None):
        self.env = env
        self.on_complete = on_complete
        self.loads = list(loads)
        self.m = len(loads)
        self.buffer = buffer
        self.draw = [LognormalDraw(loads[k], cv, station_seed(seed, k)) for k in range(self.m)]
        self.buf = [deque() for _ in range(self.m - 1)]
        self.waiting = [False] * self.m
        self.wake = [None] * self.m
        self.state = [STARVED] * self.m
        self.since = [0.0] * self.m
        self.acc = [[0.0, 0.0, 0.0] for _ in range(self.m)]
        self.completed = 0
        self.next_id = 0
        for k in range(self.m):
            env.process(self._station(k))

    def _set(self, k, state):
        now = self.env.now
        self.acc[k][self.state[k]] += now - self.since[k]
        self.state[k] = state
        self.since[k] = now

    def reset_accounting(self):
        now = self.env.now
        for k in range(self.m):
            self.acc[k] = [0.0, 0.0, 0.0]
            self.since[k] = now

    def close_accounting(self):
        for k in range(self.m):
            self._set(k, self.state[k])

    def _notify(self, k):
        ev = self.wake[k]
        if ev is not None and not ev.triggered:
            ev.succeed()

    def _wait(self, k):
        self.wake[k] = self.env.event()
        return self.wake[k]

    def _has_room(self, k):
        return len(self.buf[k]) < self.buffer or self.waiting[k + 1]

    def _station(self, k):
        env = self.env
        while True:
            if k == 0:
                unit = self.next_id
                self.next_id += 1
            else:
                while not self.buf[k - 1]:
                    self._set(k, STARVED)
                    self.waiting[k] = True
                    self._notify(k - 1)
                    yield self._wait(k)
                self.waiting[k] = False
                unit = self.buf[k - 1].popleft()
                self._notify(k - 1)
            self._set(k, BUSY)
            yield env.timeout(self.draw[k]())
            if k == self.m - 1:
                self.completed += 1
                if self.on_complete:
                    self.on_complete(self.completed, env.now)
            else:
                while not self._has_room(k):
                    self._set(k, BLOCKED)
                    yield self._wait(k)
                self.buf[k].append(unit)
                self._notify(k + 1)


def simulate(loads, cv, buffer, seed=1, warmup=500, units=5000):
    """run one line. returns throughput (units per time unit, measured after warm-up)
    and per-station time fractions."""
    env = simpy.Environment()
    target = warmup + units
    done = env.event()
    t_warm = [None]

    def on_complete(count, now):
        if count == warmup:
            t_warm[0] = now
            line.reset_accounting()
        elif count == target:
            done.succeed()

    line = Line(env, loads, cv, buffer, seed, on_complete)
    env.run(until=done)
    line.close_accounting()
    span = env.now - t_warm[0]
    per_station = [{"busy": b / span, "starved": s / span, "blocked": bl / span} for s, b, bl in line.acc]
    return {"throughput": units / span, "span": span, "t_warm": t_warm[0], "stations": per_station}


def line_report(loads, cycle_time, cv, buffer, seed=1, warmup=500, units=5000):
    """the figures the readme reports, with the assumptions behind the oee terms spelled out."""
    r = simulate(loads, cv, buffer, seed, warmup, units)
    m = len(loads)
    paper_uph = 3600.0 / cycle_time
    bottleneck_uph = 3600.0 / max(loads)
    actual_uph = 3600.0 * r["throughput"]
    availability = 1.0   # no downtime modelled
    quality = 1.0        # no defects or rework modelled
    performance = actual_uph / paper_uph
    return {
        "cv": cv, "buffer": buffer, "seed": seed, "warmup": warmup, "units": units,
        "stations": m, "cycle_time": cycle_time, "loads": list(loads),
        "paper_uph": paper_uph, "bottleneck_uph": bottleneck_uph, "actual_uph": actual_uph,
        "actual_over_paper": actual_uph / paper_uph,
        "uph_loss_pct": 100.0 * (1.0 - actual_uph / paper_uph),
        "paper_upph": paper_uph / m, "actual_upph": actual_uph / m,
        "utilization": [s["busy"] for s in r["stations"]],
        "starved": [s["starved"] for s in r["stations"]],
        "blocked": [s["blocked"] for s in r["stations"]],
        "mean_utilization": sum(s["busy"] for s in r["stations"]) / m,
        "oee": {"availability": availability, "performance": performance, "quality": quality,
                "oee": availability * performance * quality,
                "assumptions": "availability 1.0 (no breakdowns or changeovers modelled), "
                               "quality 1.0 (no defects or rework modelled), "
                               "performance = simulated uph / paper uph (3600 / cycle time)"},
    }
