"""Duration ranges from the event log at coverage alpha, joint coverage, deadline statistics."""

from __future__ import annotations

import copy
import math
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from timelens.mining.log import minutes_between
from timelens.units import parse_minutes

MIN_SAMPLES = 30


@dataclass(frozen=True)
class TaskCalibration:
    task: str
    n: int
    dropped: int  # cases with a missing start or end, or end < start
    min: int  # minutes
    max: int
    alpha: float
    calibrated: bool  # False if fewer than MIN_SAMPLES samples


def task_durations(times: pd.DataFrame, task: str) -> tuple[pd.Series, int]:
    """Return (valid durations in minutes, number of dropped cases)."""
    d = minutes_between(times, f"{task}:start", f"{task}:end")
    valid = d[d.notna() & (d >= 0)]
    return valid, len(d) - len(valid)


def quantile_range(values: np.ndarray, alpha: float) -> tuple[int, int]:
    """Return (floor of the (1-alpha)/2 quantile, ceil of the 1-(1-alpha)/2 quantile)."""
    lo = np.quantile(values, (1 - alpha) / 2, method="linear")
    hi = np.quantile(values, 1 - (1 - alpha) / 2, method="linear")
    return math.floor(lo), math.ceil(hi)


def calibrate(train: pd.DataFrame, tasks: list[str], alpha: float,
              fallback: dict[str, tuple[int, int]]) -> list[TaskCalibration]:
    """Return a range per task from training cases. Tasks with < 30 samples keep `fallback`."""
    out = []
    for t in tasks:
        d, dropped = task_durations(train, t)
        if len(d) < MIN_SAMPLES:
            warnings.warn(f"{t}: only {len(d)} samples (< {MIN_SAMPLES}), not calibrated",
                          stacklevel=2)
            lo, hi = fallback[t]
            out.append(TaskCalibration(t, len(d), dropped, lo, hi, alpha, False))
            continue
        lo, hi = quantile_range(d.to_numpy(), alpha)
        out.append(TaskCalibration(t, len(d), dropped, lo, hi, alpha, True))
    return out


def apply_calibration(template: dict[str, Any], cals: list[TaskCalibration],
                      deadline_min: int | None = None, note: str | None = None) -> dict[str, Any]:
    """Return a copy of the rules template with calibrated task ranges (and deadline, note)."""
    rules = copy.deepcopy(template)
    for c in cals:
        rules["tasks"][c.task]["min"], rules["tasks"][c.task]["max"] = c.min, c.max
    if deadline_min is not None:
        for con in rules.get("constraints", []):
            if con["id"] == "C_deadline":
                con["max"] = deadline_min
    if note is not None:
        rules["notes"] = note
    return rules


def joint_coverage(test: pd.DataFrame, ranges: dict[str, tuple[int, int]]) -> tuple[float, int]:
    """Return (share of test cases with every mapped task inside its range, cases used).

    Uses only cases that have a valid duration for every mapped task. Empirical: no
    independence assumption.
    """
    inside = pd.Series(True, index=test.index)
    valid = pd.Series(True, index=test.index)
    for t, (lo, hi) in ranges.items():
        d = minutes_between(test, f"{t}:start", f"{t}:end")
        valid &= d.notna() & (d >= 0)
        inside &= (d >= lo) & (d <= hi)
    n = int(valid.sum())
    return (float(inside[valid].mean()) if n else float("nan")), n


def case_duration_stats(train: pd.DataFrame) -> dict[str, float]:
    """Return median, p80 and p90 of case_end - case_start in minutes (training cases)."""
    d = minutes_between(train, "case_start", "case_end").dropna()
    d = d[d >= 0].to_numpy()
    if not len(d):
        return {"n": 0, "median": float("nan"), "p80": float("nan"), "p90": float("nan")}
    return {"n": len(d), "median": float(np.median(d)), "p80": float(np.quantile(d, 0.8)),
            "p90": float(np.quantile(d, 0.9))}


def default_deadline_days(stats: dict[str, float]) -> int:
    """Return the 90th percentile of the case duration rounded up to whole days."""
    return math.ceil(stats["p90"] / 1440)


@dataclass(frozen=True)
class CalibrationResult:
    rules: dict[str, Any]  # rules JSON content
    table: list[TaskCalibration]
    coverage: float  # empirical joint coverage on the test set
    coverage_cases: int

    @property
    def risk(self) -> float:
        return 1 - self.coverage


def calibrate_template(train: pd.DataFrame, test: pd.DataFrame, template: dict[str, Any],
                       alpha: float, deadline_min: int, note: str) -> CalibrationResult:
    """Return the template calibrated on `train`, with joint coverage measured on `test`."""
    tasks = [t for t in template["tasks"] if f"{t}:start" in train.columns]
    fallback = {t: (parse_minutes(template["tasks"][t]["min"]),
                    parse_minutes(template["tasks"][t]["max"])) for t in tasks}
    table = calibrate(train, tasks, alpha, fallback)
    rules = apply_calibration(template, table, deadline_min, note)
    cov, n = joint_coverage(test, {c.task: (c.min, c.max) for c in table})
    return CalibrationResult(rules, table, cov, n)
