from tests.test_bpmn import _flow, _xml
from timelens.analysis.verdict import check_process
from timelens.model.bpmn import parse_bpmn
from timelens.model.process import ProcessGraph, load_model
from timelens.model.rules import Rules


def test_minimal_verdicts(minimal_paths):
    v = check_process(*load_model(*minimal_paths))
    assert (v.consistent, v.strongly_controllable, v.dynamically_controllable) == (
        True, False, "NOT_DC")


def test_full_is_not_dc_in_both_scenarios(full_paths):
    v = check_process(*load_model(*full_paths))
    assert v.dynamically_controllable == "NOT_DC"
    assert v.scenarios is not None and len(v.failing()) == 2


def test_full_is_dc_with_a_long_deadline(full_paths):
    v = check_process(*load_model(*full_paths), values={"C_deadline.max": 14 * 1440})
    assert v.dynamically_controllable == "DC"


def test_split_mode_unknown_when_only_the_union_fails():
    # XOR with branches A and B; a lag A.end -> B.start exists only in the union network
    body = ('<bpmn:startEvent id="S"/><bpmn:exclusiveGateway id="X"/><bpmn:task id="A"/>'
            '<bpmn:task id="B"/><bpmn:exclusiveGateway id="J"/><bpmn:endEvent id="E"/>'
            + _flow(1, "S", "X") + _flow(2, "X", "A") + _flow(3, "X", "B")
            + _flow(4, "A", "J") + _flow(5, "B", "J") + _flow(6, "J", "E"))
    process = ProcessGraph(parse_bpmn(_xml(body)))
    rules = Rules.model_validate({
        "process_id": "p", "xor_outcome_known_at": "split",
        "tasks": {"A": {"kind": "contingent", "min": "0", "max": "5h"},
                  "B": {"kind": "contingent", "min": "0", "max": "5h"}},
        "constraints": [
            {"id": "D", "type": "deadline", "from": {"element": "S"},
             "to": {"element": "E"}, "max": "6h"},
            {"id": "L", "type": "lag", "from": {"element": "A", "point": "end"},
             "to": {"element": "B", "point": "start"}, "min": "0"}]})
    v = check_process(process, rules)
    assert v.dynamically_controllable == "UNKNOWN_XOR"
    assert "CSTNU" in v.note
    start_mode = rules.model_copy(update={"xor_outcome_known_at": "start"})
    assert check_process(process, start_mode).dynamically_controllable == "DC"
