"""the browser simulator must agree with the python one. web/data/sim_check.json holds the
python throughput for a grid of (cv, buffer) on the sawyer c=30 optimal balance with a fixed
seed; this runs the js simulator in node on the same grid and asserts agreement within 2%."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "web" / "data" / "sim_check.json"

pytestmark = pytest.mark.skipif(shutil.which("node") is None or not CHECK.exists(),
                                reason="needs node and web/data/sim_check.json (tools/export_web.py)")


def test_js_matches_python_grid():
    spec = json.loads(CHECK.read_text())
    out = subprocess.run(["node", str(ROOT / "web" / "sim_check.js"), json.dumps(spec)],
                         capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    assert len(js) == len(spec["grid"])
    worst = 0.0
    for cell, j in zip(spec["grid"], js):
        rel = abs(j["throughput"] - cell["python_throughput"]) / cell["python_throughput"]
        worst = max(worst, rel)
        assert rel <= spec["tolerance"], f"cv={cell['cv']} buffer={cell['buffer']}: js {j['throughput']} vs python {cell['python_throughput']}"
    print(f"worst relative difference {worst:.2e}")


def test_python_grid_is_current():
    """recompute two cells in python so the committed numbers cannot drift from the code."""
    from ladder.sim import simulate
    spec = json.loads(CHECK.read_text())
    for cell in (spec["grid"][0], spec["grid"][-1]):
        r = simulate(spec["loads"], cell["cv"], cell["buffer"], seed=spec["seed"], warmup=spec["warmup"], units=spec["units"])
        assert abs(r["throughput"] - cell["python_throughput"]) < 1e-9
