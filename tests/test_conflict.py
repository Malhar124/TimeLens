from timelens.analysis.conflict import deletion_filter, explain
from timelens.analysis.verdict import check_process
from timelens.model.process import load_model


def _conflict(paths):
    process, rules = load_model(*paths)
    net = check_process(process, rules).failing()[0]
    assert net.dc.conflict is not None
    return explain(net.dc.conflict, net.stnu.params, net.name)


def test_minimal_budget_and_demand(minimal_paths):
    c = _conflict(minimal_paths)
    assert {t.param: t.coefficient for t in c.budget} == {"C_deadline.max": 1}
    assert {t.param: t.coefficient for t in c.demand} == {
        "Task_Upload.max": -1, "Task_KYC.max": -1, "Task_Approval.min": -1}
    assert c.shortfall_min == 1440


def test_minimal_text(minimal_paths):
    text = _conflict(minimal_paths).text
    assert text.splitlines()[0] == "Not dynamically controllable."
    assert "Budget:  Decision within 7 days of application ...." in text
    assert "Upload documents (customer), maximum" in text
    assert "Total demand" in text and text.rstrip().endswith("Shortfall: 1 d")


def test_full_conflicts_per_scenario(full_paths):
    process, rules = load_model(*full_paths)
    v = check_process(process, rules)
    found = {}
    for net in v.failing():
        c = explain(net.dc.conflict, net.stnu.params, net.name)
        found[net.name] = c.shortfall_min
        assert {"Task_Upload.max", "Task_KYC.max", "C_deadline.max"} <= {t.param for t in c.terms}
    assert sorted(found.values()) == [1 * 1440 + 7 * 60, 2 * 1440 + 6 * 60]


def test_deletion_filter_keeps_the_deadline(full_paths):
    process, rules = load_model(*full_paths)
    assert deletion_filter(process, rules) == ["C_deadline"]
