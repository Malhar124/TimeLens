import json

from typer.testing import CliRunner

from timelens.cli import app

runner = CliRunner()


def test_check_both_examples_exit_1_with_valid_json(tmp_path, minimal_paths, full_paths):
    for paths in (minimal_paths, full_paths):
        out = tmp_path / "check.json"
        res = runner.invoke(app, ["check", *map(str, paths), "--json", str(out)])
        assert res.exit_code == 1, res.output
        report = json.loads(out.read_text())
        assert report["verdicts"]["dynamically_controllable"] == "NOT_DC"
        assert report["conflicts"] and report["header"]["assumption_note"]


def test_check_minimal_report_shape(tmp_path, minimal_paths):
    out = tmp_path / "check.json"
    runner.invoke(app, ["check", *map(str, minimal_paths), "--json", str(out),
                        "--force-schedule"])
    report = json.loads(out.read_text())
    assert report["verdicts"] == {"consistent": True, "strongly_controllable": False,
                                  "dynamically_controllable": "NOT_DC"}
    assert report["conflicts"][0]["shortfall_min"] == 1440
    deadline = next(t for t in report["conflicts"][0]["terms"] if t["param"] == "C_deadline.max")
    assert (deadline["coefficient"], deadline["value_min"]) == (1, 10080)
    assert report["schedule"] == []  # AllMax misses the deadline: no worst-case schedule


def test_repair_minimal_exit_0(tmp_path, minimal_paths):
    out = tmp_path / "repair.json"
    res = runner.invoke(app, ["repair", *map(str, minimal_paths), "config/levers_loan.yaml",
                              "--json", str(out)])
    assert res.exit_code == 0, res.output
    report = json.loads(out.read_text())
    assert report["repair"]["status"] == "REPAIRED"
    assert report["repair"]["total_cost"] == 20000
    assert report["repair"]["changes"][0] | {"cost": 20000} == {
        "lever": "add_kyc_staff", "label": "Add one KYC officer", "param": "Task_KYC.max",
        "old_min": 2880, "new_min": 1440, "cost": 20000}
    assert report["verdicts"]["dynamically_controllable"] == "DC"
    kyc = next(r for r in report["schedule"] if r["element"] == "Task_KYC" and
               r["point"] == "start")
    assert (kyc["est_min"], kyc["lst_min"], kyc["slack_min"]) == (7200, 7200, 0)


def test_input_error_exit_2(tmp_path, minimal_paths):
    bad = tmp_path / "bad.rules.json"
    bad.write_text("{}")
    res = runner.invoke(app, ["check", str(minimal_paths[0]), str(bad)])
    assert res.exit_code == 2
