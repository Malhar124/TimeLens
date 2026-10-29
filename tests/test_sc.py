from tests.helpers import example_stnu, make_stnu
from timelens.stnu.sc import strong_controllability
from timelens.stnu.stn import is_consistent

K2 = make_stnu(["Z", "A", "B", "C"], [("B", "C", 2), ("C", "B", -1)], [("A", 1, 5, "C")])


def test_minimal_is_not_sc(minimal_paths):
    stnu = example_stnu(minimal_paths)
    res = strong_controllability(stnu)
    assert not res.controllable
    # KYC end varies by 1 d, but Approval must start within 4 h of it: no fixed start works
    assert res.conflict is not None and res.conflict.value(stnu.params) < 0
    assert res.conflict.coefs == {"Task_KYC.min": 1, "Task_KYC.max": -1,
                                  "Flow_3.min": -1, "Flow_3.max": 1}


def test_k6_not_sc_but_consistent():
    assert not strong_controllability(K2).controllable
    assert not strong_controllability(K2, provenance=False).controllable
    assert is_consistent(K2)


def test_simple_link_is_sc():
    k1 = make_stnu(["Z", "A", "C"], [("A", "Z", 0)], [("A", 1, 3, "C")])
    assert strong_controllability(k1).controllable


def test_sc_when_waiting_for_contingent_is_not_needed():
    # B must follow C within [0, 10]: a fixed B at A + 3 works for every C in [1, 3]
    net = make_stnu(["Z", "A", "B", "C"], [("C", "B", 10), ("B", "C", 0)], [("A", 1, 3, "C")])
    assert strong_controllability(net).controllable
