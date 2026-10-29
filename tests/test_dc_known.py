import pytest

from tests.helpers import example_stnu, make_stnu
from timelens.stnu.dc import dc_check
from timelens.stnu.dc_reference import dc_check_reference
from timelens.stnu.sc import strong_controllability
from timelens.stnu.stn import is_consistent

K1 = make_stnu(["Z", "A", "C"], [("A", "Z", 0)], [("A", 1, 3, "C")])
# 1 <= C - B <= 2: B must precede C but cannot see it
K2 = make_stnu(["Z", "A", "B", "C"], [("B", "C", 2), ("C", "B", -1)], [("A", 1, 5, "C")])
# 0 <= B - C <= 1: B reacts to C
K3 = make_stnu(["Z", "A", "B", "C"], [("C", "B", 1), ("B", "C", 0)], [("A", 1, 3, "C")])

ENGINES = [lambda s: dc_check(s).dc, lambda s: dc_check(s, provenance=False).dc,
           dc_check_reference]


@pytest.mark.parametrize("engine", ENGINES, ids=["fast", "fast-noprov", "reference"])
@pytest.mark.parametrize("name,expected", [("K1", True), ("K2", False), ("K3", True),
                                           ("K4", False), ("K5", True)])
def test_known_cases(engine, name, expected, minimal_paths):
    net = {"K1": K1, "K2": K2, "K3": K3,
           "K4": example_stnu(minimal_paths),
           "K5": example_stnu(minimal_paths, {"Task_KYC.max": 1440})}[name]
    assert engine(net) is expected


def test_k6_sc_false_consistent_true():
    assert not strong_controllability(K2).controllable
    assert is_consistent(K2)


def test_k4_conflict_form(minimal_paths):
    stnu = example_stnu(minimal_paths)
    res = dc_check(stnu)
    assert res.conflict is not None
    assert res.conflict.value(stnu.params) == -1440
    terms = {k: v for k, v in res.conflict.coefs.items() if stnu.params[k].value != 0}
    assert terms == {"C_deadline.max": 1, "Task_Upload.max": -1, "Task_KYC.max": -1,
                     "Task_Approval.min": -1}


def test_full_union_is_not_dc(full_paths):
    assert not dc_check(example_stnu(full_paths)).dc
