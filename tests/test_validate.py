import pytest

from ladder.instance import Instance
from ladder.validate import InfeasibleSolution, explain, validate


def chain():
    # 1 -> 2 -> 3, times 3, 4, 5
    return Instance("chain", [3, 4, 5], [[], [0], [1]])


def test_valid():
    v = validate(chain(), [0, 0, 1], 7)
    assert v.stations == 2 and v.loads == (7, 5)


def test_precedence_violation():
    with pytest.raises(InfeasibleSolution, match="predecessor"):
        validate(chain(), [1, 0, 1], 10)


def test_overload():
    with pytest.raises(InfeasibleSolution, match="cycle time"):
        validate(chain(), [0, 0, 0], 7)


def test_empty_station():
    with pytest.raises(InfeasibleSolution, match="empty"):
        validate(chain(), [0, 0, 2], 7)


def test_wrong_length():
    with pytest.raises(InfeasibleSolution):
        validate(chain(), [0, 0], 7)


def test_explain_lists_problems():
    probs = explain(chain(), [1, 0, 0], 7)
    assert any("predecessor" in p for p in probs)
