import pandas as pd
import pytest

from tests.helpers import example_stnu
from timelens.analysis.alerts import (
    CaseTrace,
    evaluate,
    first_alert,
    latest_safe_times,
    traces_from_times,
)
from timelens.model.process import load_process

D = 1440
NAMES = {"Task_KYC:s": "KYC check"}


@pytest.fixture
def stnu(minimal_paths):
    return example_stnu(minimal_paths, {"Task_KYC.max": D})  # repaired loan_minimal, DC


def _trace(cid, upload_end, kyc_start, approval_start, end):
    return CaseTrace(cid, {"Z": 0, "Task_Upload:s": 0, "Task_Upload:e": upload_end,
                           "Task_KYC:s": kyc_start, "Task_KYC:e": kyc_start + D,
                           "Task_Approval:s": approval_start, "Task_Approval:e":
                           approval_start + D, "EndEvent_1": end}, end)


ON_TIME = _trace("on_time", 2 * D, 2 * D, 3 * D, 4 * D)
LATE_EARLY_ALERT = _trace("late_alert", 3 * D, 6 * D, 7 * D, 8 * D)  # KYC starts after 5 d
LATE_NO_ALERT = _trace("late_quiet", 1 * D, 1 * D, 2 * D, 8 * D)  # delay after the last task


def test_latest_safe_start_of_kyc_is_five_days(stnu):
    lst = latest_safe_times(stnu, {"Z": 0, "Task_Upload:s": 0, "Task_Upload:e": 2 * D})
    assert lst[stnu.index["Task_KYC:s"]] == 5 * D


def test_inconsistent_observations_mean_risk(stnu):
    assert latest_safe_times(stnu, {"Z": 0, "Task_KYC:s": 6 * D}) is None


def test_alert_text_and_time(stnu):
    alert = first_alert(stnu, LATE_EARLY_ALERT, NAMES)
    assert alert is not None and alert.time == 5 * D and alert.timepoint == "Task_KYC:s"
    assert alert.message.startswith("Start KYC check by minute 7200")
    assert first_alert(stnu, ON_TIME, NAMES) is None
    assert first_alert(stnu, LATE_NO_ALERT, NAMES) is None


def test_replay_scores(stnu):
    res = evaluate(stnu, [ON_TIME, LATE_EARLY_ALERT, LATE_NO_ALERT], 7 * D, NAMES)
    ours = res["timelens"]
    assert (ours["precision"], ours["recall"]) == (1.0, 0.5)
    assert ours["f1"] == pytest.approx(2 / 3)
    assert ours["median_lead_min"] == 2 * D
    base = res["static_baseline"]
    assert (base["precision"], base["recall"], base["median_lead_min"]) == (1.0, 1.0, 3 * D)


def test_traces_skip_cases_with_missing_events(minimal_paths):
    t0 = pd.Timestamp("2016-01-01", tz="UTC")
    row = {"case_start": t0, "case_end": t0 + pd.Timedelta(days=4)}
    for i, task in enumerate(["Task_Upload", "Task_KYC", "Task_Approval"]):
        row[f"{task}:start"] = t0 + pd.Timedelta(days=i)
        row[f"{task}:end"] = t0 + pd.Timedelta(days=i + 1)
    times = pd.DataFrame([row, {**row, "Task_KYC:end": pd.NaT}], index=["a", "b"])
    traces, skipped = traces_from_times(times, load_process(minimal_paths[0]),
                                        ["Task_Upload", "Task_KYC", "Task_Approval"])
    assert (len(traces), skipped) == (1, 1)
    assert traces[0].times["Task_KYC:s"] == D and traces[0].duration == 4 * D
