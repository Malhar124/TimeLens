import json
import warnings

import pytest

from timelens.errors import RulesError
from timelens.model.process import load_model, load_process
from timelens.model.rules import Rules, load_levers, load_rules


def _write(tmp_path, data):
    p = tmp_path / "r.rules.json"
    p.write_text(json.dumps(data))
    return p


def _base(minimal_paths):
    return json.loads(minimal_paths[1].read_text())


def test_examples_load(minimal_paths, full_paths):
    for bpmn, rules in (minimal_paths, full_paths):
        process, r = load_model(bpmn, rules)
        assert set(r.tasks) == set(process.tasks)
    assert load_rules(minimal_paths[1]).tasks["Task_Upload"].max == 7200


def test_missing_task_entry_is_an_error(tmp_path, minimal_paths):
    data = _base(minimal_paths)
    del data["tasks"]["Task_KYC"]
    with pytest.raises(RulesError, match="Task_KYC"):
        load_model(minimal_paths[0], _write(tmp_path, data))


def test_unknown_element_is_an_error(tmp_path, minimal_paths):
    data = _base(minimal_paths)
    data["constraints"][0]["to"]["element"] = "EndEvent_X"
    with pytest.raises(RulesError, match="EndEvent_X"):
        load_model(minimal_paths[0], _write(tmp_path, data))


def test_unknown_flow_is_an_error(tmp_path, minimal_paths):
    data = _base(minimal_paths)
    data["flow_gaps"][0]["flow"] = "Flow_99"
    with pytest.raises(RulesError, match="Flow_99"):
        load_model(minimal_paths[0], _write(tmp_path, data))


def test_min_greater_than_max_is_an_error(tmp_path, minimal_paths):
    data = _base(minimal_paths)
    data["tasks"]["Task_KYC"]["min"] = "3d"
    with pytest.raises(RulesError, match="min"):
        load_rules(_write(tmp_path, data))


def test_duplicate_constraint_ids_are_an_error(tmp_path, minimal_paths):
    data = _base(minimal_paths)
    data["constraints"].append(dict(data["constraints"][0]))
    with pytest.raises(RulesError, match="duplicate constraint id"):
        load_rules(_write(tmp_path, data))


def test_deadline_needs_max(minimal_paths):
    data = _base(minimal_paths)
    del data["constraints"][0]["max"]
    with pytest.raises(ValueError, match="deadline"):
        Rules.model_validate(data)


def test_fixed_contingent_warns_and_is_controllable(minimal_paths):
    data = _base(minimal_paths)
    data["tasks"]["Task_KYC"]["max"] = "1d"
    rules = Rules.model_validate(data)
    process = load_process(minimal_paths[0])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rules.check_against(set(process.tasks), set(process.nodes), set(process.flows))
    assert any("Task_KYC" in str(x.message) for x in w)
    assert not rules.tasks["Task_KYC"].is_contingent


def test_levers_file_loads():
    levers = load_levers("config/levers_loan.yaml")
    assert levers.granularity == 60
    assert [lv.max_change for lv in levers.levers] == [1440, 2880, 4320]
