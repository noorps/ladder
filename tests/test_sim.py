from ladder.rng import LognormalDraw, Mulberry32
from ladder.sim import line_report, simulate


def test_mulberry32_is_deterministic():
    a, b = Mulberry32(42), Mulberry32(42)
    xs = [a.random() for _ in range(5)]
    assert xs == [b.random() for _ in range(5)]
    assert all(0.0 <= x < 1.0 for x in xs)


def test_lognormal_moments():
    d = LognormalDraw(10.0, 0.5, 7)
    xs = [d() for _ in range(20000)]
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    assert abs(mean - 10.0) < 0.15
    assert abs((var ** 0.5) / mean - 0.5) < 0.03


def test_deterministic_line_hits_paper_rate():
    loads = [30, 29, 28, 30, 27, 30]
    r = line_report(loads, 30, 0.0, 0, units=500, warmup=50)
    assert abs(r["actual_over_paper"] - 1.0) < 1e-9
    assert all(s == 0.0 for s in r["blocked"])


def test_variability_costs_throughput_and_buffers_recover_some():
    loads = [30, 29, 28, 30, 27, 30]
    r0 = line_report(loads, 30, 0.5, 0, units=2000, warmup=200)
    r8 = line_report(loads, 30, 0.5, 8, units=2000, warmup=200)
    assert r0["actual_over_paper"] < 0.9
    assert r8["actual_over_paper"] > r0["actual_over_paper"]


def test_state_fractions_sum_to_one():
    r = simulate([10, 12, 9], 0.3, 1, units=500, warmup=50)
    for s in r["stations"]:
        assert abs(s["busy"] + s["starved"] + s["blocked"] - 1.0) < 1e-9


def test_same_seed_same_result():
    a = simulate([10, 12, 9], 0.3, 1, seed=5, units=300, warmup=30)
    b = simulate([10, 12, 9], 0.3, 1, seed=5, units=300, warmup=30)
    assert a["throughput"] == b["throughput"]
