import pytest

from tests.test_bpmn import _flow, _xml
from timelens.errors import ModelError
from timelens.model.bpmn import parse_bpmn
from timelens.model.process import ProcessGraph, load_process


def test_full_has_two_scenarios(full_paths):
    scenarios = load_process(full_paths[0]).scenarios()
    assert scenarios is not None and len(scenarios) == 2
    assert {("Task_AutoApprove" in s.nodes, "Task_ManualReview" in s.nodes) for s in scenarios} == {
        (True, False), (False, True)}


def test_minimal_has_one_default_scenario(minimal_paths):
    scenarios = load_process(minimal_paths[0]).scenarios()
    assert scenarios is not None and [s.name for s in scenarios] == ["default"]


def test_xor_split_into_and_join_is_rejected():
    body = ('<bpmn:startEvent id="S"/><bpmn:exclusiveGateway id="X"/><bpmn:task id="T1"/>'
            '<bpmn:task id="T2"/><bpmn:parallelGateway id="J"/><bpmn:endEvent id="E"/>'
            + _flow(1, "S", "X") + _flow(2, "X", "T1") + _flow(3, "X", "T2")
            + _flow(4, "T1", "J") + _flow(5, "T2", "J") + _flow(6, "J", "E"))
    with pytest.raises(ModelError, match="AND join J"):
        ProcessGraph(parse_bpmn(_xml(body))).scenarios()


def test_scenario_cap_returns_none():
    # 9 XOR blocks in sequence: 2^9 = 512 scenarios > 256
    body, prev, i = '<bpmn:startEvent id="S"/><bpmn:endEvent id="E"/>', "S", 0
    for b in range(9):
        body += (f'<bpmn:exclusiveGateway id="X{b}"/><bpmn:task id="A{b}"/><bpmn:task id="B{b}"/>'
                 f'<bpmn:exclusiveGateway id="J{b}"/>')
        for s, d in ((prev, f"X{b}"), (f"X{b}", f"A{b}"), (f"X{b}", f"B{b}"),
                     (f"A{b}", f"J{b}"), (f"B{b}", f"J{b}")):
            i += 1
            body += _flow(i, s, d)
        prev = f"J{b}"
    body += _flow(i + 1, prev, "E")
    g = ProcessGraph(parse_bpmn(_xml(body)))
    assert g.scenarios() is None
    assert len(g.scenarios(cap=1024) or []) == 512
