"""Run-time alerts: latest safe start times from the design-time network, replay on past cases."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from timelens.model.process import ProcessGraph
from timelens.stnu.network import STNU, weighted
from timelens.stnu.stn import allmax_edges, distance_matrix, floyd_warshall, negative_diagonal

STATIC_MARGIN_MIN = 3 * 1440  # baseline: alert if no decision by deadline - 3 days


@dataclass(frozen=True)
class CaseTrace:
    case_id: str
    times: dict[str, int]  # observed timepoint -> integer minutes after case start (Z = 0)
    duration: int  # case_end - case_start, minutes


@dataclass(frozen=True)
class Alert:
    time: float  # minutes after case start
    timepoint: str  # the task start at risk ("" if the observations are already inconsistent)
    message: str


def latest_safe_times(stnu: STNU, observed: Mapping[str, int]) -> npt.NDArray[np.float64] | None:
    """Return LST(X) = D[Z, X] for every timepoint, or None if the case is already at risk.

    AllMax projection; observed timepoints pinned to their times; a contingent link whose end
    is observed uses the observed time instead of its maximum. O(n^3).
    """
    idx = stnu.index
    links = [lk for lk in stnu.links if lk.contingent not in observed]
    triples: list[tuple[int, int, float]] = list(weighted(stnu, stnu.edges + allmax_edges(links)))
    for tp, t in observed.items():
        triples += [(0, idx[tp], t), (idx[tp], 0, -t)]
    D = floyd_warshall(distance_matrix(len(stnu.timepoints), triples))
    return None if negative_diagonal(D) is not None else D[0].copy()


def first_alert(stnu: STNU, trace: CaseTrace, names: Mapping[str, str]) -> Alert | None:
    """Replay one case and return its first alert, or None.

    After event k at t_k (next event at t_k+1), a pending task start X with LST(X) < t_k+1
    raises an alert at max(LST(X), t_k). O(events * n^3).
    """
    events = sorted(trace.times.items(), key=lambda kv: kv[1])
    idx = stnu.index
    watch = [tp for tp in stnu.timepoints if tp.endswith(":s")]
    for k in range(len(events) - 1):
        t_k, t_next = events[k][1], events[k + 1][1]
        observed = dict(events[: k + 1])
        lst = latest_safe_times(stnu, observed)
        if lst is None:
            return Alert(t_k, "", "Observed times already break a time rule: deadline at risk.")
        late = [(max(float(lst[idx[x]]), t_k), x) for x in watch
                if x not in observed and lst[idx[x]] < t_next]
        if late:
            at, x = min(late)
            return Alert(at, x, f"Start {names.get(x, x)} by minute {at:.0f}, "
                                f"else the deadline is at risk.")
    return None


def scores(alert_times: list[float | None], late: list[bool], deadline: int) -> dict[str, Any]:
    """Return precision, recall, F1 and median lead time (deadline - alert time) of true hits."""
    tp = sum(a is not None and lt for a, lt in zip(alert_times, late, strict=True))
    fp = sum(a is not None and not lt for a, lt in zip(alert_times, late, strict=True))
    fn = sum(a is None and lt for a, lt in zip(alert_times, late, strict=True))
    precision = tp / (tp + fp) if tp + fp else math.nan
    recall = tp / (tp + fn) if tp + fn else math.nan
    f1 = (2 * precision * recall / (precision + recall)
          if tp and precision + recall else math.nan)
    leads = [deadline - a for a, lt in zip(alert_times, late, strict=True)
             if a is not None and lt]
    return {"cases": len(late), "late": sum(late), "alerts": tp + fp, "tp": tp, "fp": fp,
            "fn": fn, "precision": precision, "recall": recall, "f1": f1,
            "median_lead_min": statistics.median(leads) if leads else math.nan}


def static_alert(trace: CaseTrace, deadline: int) -> float | None:
    """Baseline: alert at deadline - 3 days if the case has no decision by then."""
    at = max(0, deadline - STATIC_MARGIN_MIN)
    return float(at) if trace.duration > at else None


def evaluate(stnu: STNU, traces: list[CaseTrace], deadline: int,
             names: Mapping[str, str]) -> dict[str, Any]:
    """Return TimeLens and static-baseline scores on `traces`. A case is late if
    case_end - case_start > deadline."""
    late = [t.duration > deadline for t in traces]
    ours = [first_alert(stnu, t, names) for t in traces]
    return {"timelens": scores([a.time if a else None for a in ours], late, deadline),
            "static_baseline": scores([static_alert(t, deadline) for t in traces], late,
                                      deadline)}


def traces_from_times(times: pd.DataFrame, process: ProcessGraph,
                      tasks: list[str]) -> tuple[list[CaseTrace], int]:
    """Return (traces with every mapped event, number of skipped cases).

    Columns: case_start -> Z, case_end -> end event, <task>:start/:end -> <task>:s/:e.
    """
    cols = {"case_start": "Z", "case_end": process.end}
    for t in tasks:
        cols[f"{t}:start"], cols[f"{t}:end"] = f"{t}:s", f"{t}:e"
    full = times.dropna(subset=list(cols))
    rel = {c: ((full[c] - full["case_start"]).dt.total_seconds() // 60).astype(int) for c in cols}
    traces = [CaseTrace(str(case), {tp: int(rel[c][case]) for c, tp in cols.items()},
                        int(rel["case_end"][case])) for case in full.index]
    # Events before the case start or task ends before task starts are data errors: skip them.
    traces = [tr for tr in traces if min(tr.times.values()) >= 0
              and all(tr.times[f"{t}:e"] >= tr.times[f"{t}:s"] for t in tasks)]
    return traces, len(times) - len(traces)
