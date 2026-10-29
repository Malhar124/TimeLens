import json
import warnings

import pandas as pd
import pytest
from typer.testing import CliRunner

from tests.synth import BASE, synthetic_log
from timelens.cli import app
from timelens.errors import LogMappingError
from timelens.mining.calibrate import calibrate, joint_coverage, quantile_range
from timelens.mining.log import case_times, discover, load_mapping, split_by_time
from timelens.model.rules import Rules

MAPPING = "config/mapping_bpi2017.yaml"
TEMPLATE = "examples/bpi2017/loan_bpi.rules.template.json"


def _times(durations):
    """One case per duration, started one hour apart."""
    starts = [BASE + pd.Timedelta(hours=i) for i in range(len(durations))]
    return pd.DataFrame({
        "case_start": starts,
        "T:start": starts,
        "T:end": [s + pd.Timedelta(minutes=d) for s, d in zip(starts, durations, strict=True)],
    })


def test_quantiles_are_exact_on_known_durations():
    cal = calibrate(_times(range(1, 101)), ["T"], 0.9, {"T": (0, 0)})[0]
    # linear quantiles of 1..100: q(0.05) = 5.95 -> floor 5, q(0.95) = 95.05 -> ceil 96
    assert (cal.n, cal.min, cal.max, cal.calibrated) == (100, 5, 96, True)
    assert quantile_range(pd.Series(range(1, 101)).to_numpy(), 1.0) == (1, 100)


def test_split_is_chronological():
    times = _times(range(1, 101)).sample(frac=1.0, random_state=3)
    train, test = split_by_time(times)
    assert (len(train), len(test)) == (70, 30)
    assert train["case_start"].max() < test["case_start"].min()


def test_fewer_than_30_samples_warns_and_keeps_fallback():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cal = calibrate(_times(range(1, 21)), ["T"], 0.95, {"T": (7, 9)})[0]
    assert any("only 20 samples" in str(x.message) for x in w)
    assert (cal.calibrated, cal.min, cal.max) == (False, 7, 9)


def test_bad_durations_are_dropped():
    times = _times([10, 20, -5])
    times.loc[1, "T:end"] = pd.NaT
    with pytest.warns(UserWarning, match="only 1 samples"):
        assert calibrate(times, ["T"], 0.9, {"T": (0, 0)})[0].dropped == 2


def test_joint_coverage_counts_cases_inside_every_range():
    times = _times([5, 10, 50, 100])
    assert joint_coverage(times, {"T": (5, 50)}) == (0.75, 4)


def test_mapping_extracts_case_times():
    times = case_times(synthetic_log(10), load_mapping(MAPPING))
    assert len(times) == 10 and not times.isna().any().any()
    assert (times["Task_Validate:end"] > times["Task_Validate:start"]).all()


def test_missing_alternative_end_activity_only_warns():
    log = synthetic_log(10)
    log = log[log["concept:name"] != "A_Denied"]
    with pytest.warns(UserWarning, match="A_Denied"):
        case_times(log, load_mapping(MAPPING))


def test_unknown_activity_in_mapping_is_an_error(tmp_path):
    bad = tmp_path / "m.yaml"
    bad.write_text(open(MAPPING).read().replace("O_Returned", "O_Back"))
    with pytest.raises(LogMappingError, match="O_Back"):
        case_times(synthetic_log(10), load_mapping(bad))


def test_discover_lists_lifecycles():
    table = discover(synthetic_log(5))
    row = table[table["concept:name"] == "W_Complete application"]
    assert set(row["lifecycle:transition"]) == {"start", "complete"}
    assert row["count"].tolist() == [5, 5]


def test_cli_calibrate_writes_valid_rules(tmp_path):
    log = tmp_path / "synthetic.parquet"
    synthetic_log(200).to_parquet(log)
    out = tmp_path / "rules.json"
    res = CliRunner().invoke(app, ["calibrate", str(log), MAPPING, TEMPLATE, "--alpha", "0.9",
                                   "--out", str(out)])
    assert res.exit_code == 0, res.output
    rules = Rules.model_validate(json.loads(out.read_text()))
    assert "90th percentile" in (rules.notes or "")
    assert rules.tasks["Task_CustomerReturn"].max > 1440
    assert "Joint coverage on the test set" in res.output
