import pytest

from timelens.analysis.repair import repair
from timelens.analysis.schedule import worst_case_schedule
from timelens.model.process import load_model
from timelens.model.rules import load_levers

LEVERS = "config/levers_loan.yaml"


def _levers(drop=()):
    lv = load_levers(LEVERS)
    return lv.model_copy(update={"levers": [x for x in lv.levers if x.id not in drop]})


def test_minimal_repair_adds_kyc_staff(minimal_paths):
    r = repair(*load_model(*minimal_paths), _levers())
    assert r.status == "REPAIRED"
    assert [(c.lever, c.old_min, c.new_min) for c in r.changes] == [("add_kyc_staff", 2880, 1440)]
    assert r.total_cost == pytest.approx(20000)
    assert r.lp_cost == pytest.approx(r.total_cost)
    assert r.verdict.dynamically_controllable == "DC"
    assert r.currency == "INR" and "assumption" in r.assumption_note


def test_minimal_repair_without_kyc_lever_nudges_customer(minimal_paths):
    r = repair(*load_model(*minimal_paths), _levers({"add_kyc_staff"}))
    assert [(c.lever, c.new_min - c.old_min) for c in r.changes] == [("nudge_customer", -1440)]
    assert r.total_cost == pytest.approx(30000)


def test_minimal_without_levers_has_no_repair(minimal_paths):
    r = repair(*load_model(*minimal_paths), _levers({"add_kyc_staff", "nudge_customer",
                                                     "extend_deadline"}))
    assert r.status == "NO_REPAIR"
    assert r.conflict is not None and r.conflict.shortfall_min == 1440


def test_minimal_schedule_after_repair(minimal_paths):
    r = repair(*load_model(*minimal_paths), _levers())
    sched = worst_case_schedule(r.verdict.union.stnu)
    kyc = next(x for x in sched.rows if x.timepoint == "Task_KYC:s")
    assert (kyc.est, kyc.lst, kyc.slack) == (7200, 7200, 0)
    assert "Task_KYC" in sched.critical_path


def test_full_repair_makes_it_dc(full_paths):
    r = repair(*load_model(*full_paths), _levers())
    assert r.status == "REPAIRED"
    assert r.verdict.dynamically_controllable == "DC"
    shortfall = 2 * 1440 + 6 * 60  # manual review path
    assert sum(abs(c.new_min - c.old_min) for c in r.changes) == shortfall
    assert r.total_cost == pytest.approx(20000 + 30000 * 1800 / 1440)


def test_already_dc_costs_nothing(minimal_paths):
    process, rules = load_model(*minimal_paths)
    rules.tasks["Task_KYC"].max = 1440
    r = repair(process, rules, _levers())
    assert (r.status, r.total_cost, r.changes) == ("ALREADY_DC", 0, [])
