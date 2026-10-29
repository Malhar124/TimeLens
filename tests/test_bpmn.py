import pytest

from timelens.errors import ModelError
from timelens.model.bpmn import parse_bpmn
from timelens.model.process import ProcessGraph, load_process

NS = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'


def _xml(body: str) -> str:
    return f'<bpmn:definitions {NS}><bpmn:process id="p">{body}</bpmn:process></bpmn:definitions>'


def _flow(i, s, d):
    return f'<bpmn:sequenceFlow id="F{i}" sourceRef="{s}" targetRef="{d}"/>'


def test_minimal_counts(minimal_paths):
    m = parse_bpmn(minimal_paths[0])
    assert (len(m.nodes), len(m.flows)) == (5, 4)
    assert m.nodes["Task_KYC"].name == "KYC check"


def test_full_counts(full_paths):
    m = parse_bpmn(full_paths[0])
    assert (len(m.nodes), len(m.flows)) == (13, 14)
    assert sum(n.kind == "task" for n in m.nodes.values()) == 7


def test_loop_is_rejected():
    body = ('<bpmn:startEvent id="S"/><bpmn:exclusiveGateway id="J"/><bpmn:task id="T"/>'
            '<bpmn:exclusiveGateway id="X"/><bpmn:endEvent id="E"/>'
            + _flow(1, "S", "J") + _flow(2, "J", "T") + _flow(3, "T", "X")
            + _flow(4, "X", "J") + _flow(5, "X", "E"))
    with pytest.raises(ModelError, match="loop"):
        ProcessGraph(parse_bpmn(_xml(body)))


def test_two_start_events_are_rejected():
    body = ('<bpmn:startEvent id="S1"/><bpmn:startEvent id="S2"/>'
            '<bpmn:parallelGateway id="J"/><bpmn:endEvent id="E"/>'
            + _flow(1, "S1", "J") + _flow(2, "S2", "J") + _flow(3, "J", "E"))
    with pytest.raises(ModelError, match="start event"):
        ProcessGraph(parse_bpmn(_xml(body)))


def test_unsupported_element_is_rejected():
    body = '<bpmn:startEvent id="S"/><bpmn:subProcess id="Sub"/><bpmn:endEvent id="E"/>'
    with pytest.raises(ModelError, match="subProcess"):
        parse_bpmn(_xml(body))


def test_gateway_both_split_and_join_is_rejected():
    body = ('<bpmn:startEvent id="S"/><bpmn:parallelGateway id="A"/><bpmn:task id="T1"/>'
            '<bpmn:task id="T2"/><bpmn:parallelGateway id="G"/><bpmn:task id="T3"/>'
            '<bpmn:task id="T4"/><bpmn:parallelGateway id="B"/><bpmn:endEvent id="E"/>'
            + _flow(1, "S", "A") + _flow(2, "A", "T1") + _flow(3, "A", "T2")
            + _flow(4, "T1", "G") + _flow(5, "T2", "G") + _flow(6, "G", "T3")
            + _flow(7, "G", "T4") + _flow(8, "T3", "B") + _flow(9, "T4", "B") + _flow(10, "B", "E"))
    with pytest.raises(ModelError, match="both a split and a join"):
        ProcessGraph(parse_bpmn(_xml(body)))


def test_unreachable_element_is_rejected():
    body = ('<bpmn:startEvent id="S"/><bpmn:parallelGateway id="A"/><bpmn:task id="T"/>'
            '<bpmn:task id="Dead"/><bpmn:parallelGateway id="B"/><bpmn:endEvent id="E"/>'
            + _flow(1, "S", "A") + _flow(2, "A", "T") + _flow(3, "T", "B") + _flow(4, "B", "E")
            + _flow(5, "Dead", "B"))
    with pytest.raises(ModelError):
        ProcessGraph(parse_bpmn(_xml(body)))


def test_diagram_section_is_ignored(minimal_paths):
    assert "bpmndi:BPMNDiagram" in minimal_paths[0].read_text()
    assert load_process(minimal_paths[0]).tasks == ["Task_Upload", "Task_KYC", "Task_Approval"]
