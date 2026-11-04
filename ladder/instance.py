"""salbp instances: parsing the .alb (otto 2013) and .IN2 (scholl 1993) formats and
loading the named benchmark sets with their published optima."""
import json
import math
import random
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OPT = ROOT / "data" / "optima"

# spreadsheet graph names -> .IN2 file stems
SCHOLL_FILES = {
    "Arcus1": "ARC83", "Arcus2": "ARC111", "Barthol2": "BARTHOL2", "Barthold": "BARTHOLD",
    "Bowman": "BOWMAN8", "Buxey": "BUXEY", "Gunther": "GUNTHER", "Hahn": "HAHN",
    "Heskiaoff": "HESKIA", "Jackson": "JACKSON", "Jaeschke": "JAESCHKE", "Kilbridge": "KILBRID",
    "Lutz1": "LUTZ1", "Lutz2": "LUTZ2", "Lutz3": "LUTZ3", "Mansoor": "MANSOOR",
    "Mertens": "MERTENS", "Mitchell": "MITCHELL", "Mukherje": "MUKHERJE", "Roszieg": "ROSZIEG",
    "Sawyer": "SAWYER30", "Scholl": "SCHOLL", "Tonge": "TONGE70", "Warnecke": "WARNECKE",
    "Wee-mag": "WEE-MAG", "Wee-Mag": "WEE-MAG",
}


@dataclass
class Instance:
    name: str
    times: list            # task durations, index 0..n-1 (task ids are 1..n in the files)
    preds: list            # direct predecessors per task, 0-based
    cycle_time: int = None  # given cycle time (salbp-1) if the file carries one
    source: str = ""
    published: dict = field(default_factory=dict)  # published optimum info for this instance

    @property
    def n(self):
        return len(self.times)

    @property
    def total_time(self):
        return sum(self.times)

    @cached_property
    def succs(self):
        s = [[] for _ in range(self.n)]
        for j, ps in enumerate(self.preds):
            for i in ps:
                s[i].append(j)
        return s

    @cached_property
    def all_preds(self):
        """transitive predecessor sets."""
        out = [None] * self.n
        for i in self.topo_order:
            acc = set()
            for p in self.preds[i]:
                acc.add(p)
                acc |= out[p]
            out[i] = acc
        return out

    @cached_property
    def all_succs(self):
        out = [None] * self.n
        for i in reversed(self.topo_order):
            acc = set()
            for s in self.succs[i]:
                acc.add(s)
                acc |= out[s]
            out[i] = acc
        return out

    @cached_property
    def topo_order(self):
        indeg = [len(p) for p in self.preds]
        ready = [i for i in range(self.n) if indeg[i] == 0]
        order = []
        while ready:
            i = ready.pop(0)
            order.append(i)
            for s in self.succs[i]:
                indeg[s] -= 1
                if indeg[s] == 0:
                    ready.append(s)
        if len(order) != self.n:
            raise ValueError(f"{self.name}: precedence graph has a cycle")
        return order

    def lb_stations(self, c):
        """simple salbp-1 lower bound lm1 = ceil(sum t / c)."""
        return math.ceil(self.total_time / c)

    def lb_cycle_time(self, m):
        return max(max(self.times), math.ceil(self.total_time / m))

    def with_times(self, times, name=None):
        return Instance(name or self.name, list(times), [list(p) for p in self.preds],
                        self.cycle_time, self.source, {})

    def to_dict(self):
        return {"name": self.name, "n": self.n, "cycle_time": self.cycle_time,
                "tasks": [{"id": i + 1, "time": self.times[i], "preds": [p + 1 for p in self.preds[i]]}
                          for i in range(self.n)]}


def parse_alb(text, name):
    """otto 2013 .alb: tagged sections <number of tasks>, <cycle time>, <task times>, <precedence relations>."""
    sections = {}
    cur = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"<(.+)>$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur:
            sections[cur].append(line)
    n = int(sections["number of tasks"][0])
    c = int(sections["cycle time"][0]) if sections.get("cycle time") else None
    times = [0] * n
    for line in sections["task times"]:
        i, t = line.split()
        times[int(i) - 1] = int(t)
    preds = [[] for _ in range(n)]
    for line in sections.get("precedence relations", []):
        a, b = [int(x) for x in line.split(",")]
        preds[b - 1].append(a - 1)
    return Instance(name, times, preds, c, "otto2013")


def parse_in2(text, name):
    """scholl 1993 .IN2: n, then n task times, then 'i,j' arcs, terminated by -1,-1."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    n = int(lines[0])
    times = [int(x) for x in lines[1:n + 1]]
    preds = [[] for _ in range(n)]
    for line in lines[n + 1:]:
        a, b = [int(x) for x in line.split(",")]
        if a < 0:
            break
        preds[b - 1].append(a - 1)
    return Instance(name, times, preds, None, "scholl1993")


def _need_data():
    if not RAW.exists():
        raise FileNotFoundError("data/raw missing: run `python tools/fetch_data.py` first")


def load_scholl_graph(graph):
    """one scholl 1993 precedence graph by its spreadsheet name (e.g. 'Sawyer')."""
    _need_data()
    stem = SCHOLL_FILES[graph]
    return parse_in2((RAW / "scholl1993" / f"{stem}.IN2").read_text(), graph)


def scholl_salbp1():
    """all 269 (graph, cycle time) salbp-1 instances with published m*."""
    rows = json.loads((OPT / "scholl1993_salbp1.json").read_text())
    graphs = {}
    out = []
    for r in rows:
        g = graphs.setdefault(r["graph"], load_scholl_graph(r["graph"]))
        inst = Instance(f"{r['graph']}_c{r['c']}", g.times, g.preds, r["c"], "scholl1993",
                        {"optimum": r["optimum"], "lb": r.get("lb", r["optimum"]), "ub": r.get("ub", r["optimum"])})
        out.append(inst)
    return out


def scholl_salbp2(dataset=1):
    """scholl 1993 salbp-2 instances: (graph, m) with published c*. set 1 has 128, set 2 has 174."""
    rows = json.loads((OPT / "scholl1993_salbp2.json").read_text())
    graphs = {}
    out = []
    for r in rows:
        if dataset is not None and r["set"] != dataset:
            continue
        g = graphs.setdefault(r["graph"], load_scholl_graph(r["graph"]))
        inst = Instance(f"{r['graph']}_m{r['m']}", g.times, g.preds, None, "scholl1993",
                        {"m": r["m"], "optimum": r["optimum"], "lb": r.get("lb", r["optimum"]), "ub": r.get("ub", r["optimum"])})
        out.append(inst)
    return out


def otto2013(n, sample=None, seed=0):
    """otto 2013 instances of size n (20, 50, 100), optionally a seeded random sample."""
    _need_data()
    opt = json.loads((OPT / "otto2013.json").read_text())
    files = sorted((RAW / "otto2013" / f"n{n}").glob("*.alb"),
                   key=lambda p: int(re.search(r"_(\d+)\.alb$", p.name).group(1)))
    if sample is not None and sample < len(files):
        files = sorted(random.Random(seed).sample(files, sample), key=files.index)
    out = []
    for f in files:
        inst = parse_alb(f.read_text(), f.stem)
        inst.published = opt[f.stem]
        out.append(inst)
    return out


def instance_set(name, sample=None, seed=0):
    """named sets used by the benchmark runner."""
    if name == "scholl-salbp1":
        return scholl_salbp1()
    if name == "scholl-salbp2":
        return scholl_salbp2(1)
    if name == "scholl-salbp2-all":
        return scholl_salbp2(None)
    m = re.match(r"otto-n(\d+)$", name)
    if m:
        return otto2013(int(m.group(1)), sample, seed)
    raise KeyError(name)
