import json
import math

from tests.synth import synthetic_log
from timelens.analysis.frontier import ALPHAS, FrontierPoint, cost_never_decreases, frontier
from timelens.mining.log import case_times, load_mapping, split_by_time
from timelens.model.process import load_process
from timelens.model.rules import load_levers

TEMPLATE = json.load(open("examples/bpi2017/loan_bpi.rules.template.json"))


def test_cost_is_non_decreasing_in_alpha_on_a_synthetic_log():
    times = case_times(synthetic_log(400, seed=5), load_mapping("config/mapping_bpi2017.yaml"))
    train, test = split_by_time(times)
    points = frontier(load_process("examples/bpi2017/loan_bpi.bpmn"), train, test, TEMPLATE,
                      load_levers("config/levers_bpi2017.yaml"), 19 * 1440, "test deadline")
    assert [p.alpha for p in points] == list(ALPHAS)
    assert cost_never_decreases(points)
    assert points[-1].cost > points[0].cost  # wider ranges cost more here
    risks = [p.risk for p in points]
    assert risks == sorted(risks, reverse=True)


def test_cost_check_flags_a_decrease_and_treats_no_repair_as_infinite():
    def pt(alpha, cost):
        return FrontierPoint(alpha, 0.1, "NOT_DC", "REPAIRED", cost, "", "")

    assert not cost_never_decreases([pt(0.8, 10.0), pt(0.9, 5.0)])
    assert cost_never_decreases([pt(0.8, 10.0), pt(0.9, math.nan)])
    assert not cost_never_decreases([pt(0.8, math.nan), pt(0.9, 10.0)])
