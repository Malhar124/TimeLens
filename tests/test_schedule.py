from tests.helpers import example_stnu
from timelens.analysis.schedule import worst_case_schedule


def test_minimal_after_repair_schedule(minimal_paths):
    sched = worst_case_schedule(example_stnu(minimal_paths, {"Task_KYC.max": 1440}))
    assert sched is not None
    kyc = next(r for r in sched.rows if r.timepoint == "Task_KYC:s")
    assert (kyc.est, kyc.lst, kyc.slack) == (7200, 7200, 0)
    assert sched.critical_path == ["Task_Upload", "Task_KYC", "Task_Approval"]


def test_allmax_schedule_is_none_when_worst_case_misses_deadline(minimal_paths):
    assert worst_case_schedule(example_stnu(minimal_paths)) is None


def test_full_allmax_est_of_end(full_paths):
    sched = worst_case_schedule(example_stnu(full_paths, {"C_deadline.max": 20160}))
    assert sched is not None
    end = next(r for r in sched.rows if r.timepoint == "EndEvent_1")
    assert end.est == 5 * 1440 + 2 * 1440 + 6 * 60 + 1440 + 1440  # union: manual review path
