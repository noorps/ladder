import pytest

from ladder.instance import load_scholl_graph
from ladder.solvers import comsoal, exact, rpw
from ladder.validate import validate

pytestmark = pytest.mark.skipif(not (__import__("ladder.instance").instance.RAW).exists(),
                                reason="run tools/fetch_data.py first")

# published optima for sawyer (scholl 1993 salbp-1 table)
SAWYER_OPT = {25: 14, 30: 12, 36: 10, 41: 8, 47: 7, 75: 5}


@pytest.fixture(scope="module")
def sawyer():
    return load_scholl_graph("Sawyer")


@pytest.mark.parametrize("c", sorted(SAWYER_OPT))
def test_salbp1_all_solvers_validate_and_order(sawyer, c):
    r1 = rpw.solve_salbp1(sawyer, c)
    r2 = comsoal.solve_salbp1(sawyer, c, trials=200)
    r3 = exact.solve_salbp1(sawyer, c, time_limit=20)
    for r in (r1, r2, r3):
        validate(sawyer, r.assignment, c)
    assert r3.proven
    assert r3.stations == SAWYER_OPT[c]
    assert r1.stations >= r3.stations and r2.stations >= r3.stations


def test_salbp2(sawyer):
    r3 = exact.solve_salbp2(sawyer, 7, time_limit=20)
    assert r3.proven and r3.cycle_time == 47  # published c* for sawyer, m=7
    r1 = rpw.solve_salbp2(sawyer, 7)
    r2 = comsoal.solve_salbp2(sawyer, 7, trials=200)
    assert r1.stations <= 7 and r2.stations <= 7
    assert r1.cycle_time >= 47 and r2.cycle_time >= 47


def test_comsoal_trace_is_monotone(sawyer):
    r = comsoal.solve_salbp1(sawyer, 30, trials=100, trace=True)
    curve = r.extra["best_by_trial"]
    assert len(curve) == 100 and all(a >= b for a, b in zip(curve, curve[1:]))


def test_comsoal_seeded(sawyer):
    a = comsoal.solve_salbp1(sawyer, 30, trials=50, seed=3)
    b = comsoal.solve_salbp1(sawyer, 30, trials=50, seed=3)
    assert a.assignment == b.assignment
