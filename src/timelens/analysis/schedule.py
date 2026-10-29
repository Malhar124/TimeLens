"""Worst-case schedule on the AllMax projection: EST, LST, slack, critical path."""

from __future__ import annotations

from dataclasses import dataclass

from timelens.stnu.network import STNU, Edge, weighted
from timelens.stnu.stn import (
    Matrix,
    allmax_edges,
    distance_matrix,
    floyd_warshall,
    negative_diagonal,
)


@dataclass(frozen=True)
class PointTime:
    timepoint: str
    element: str
    point: str  # "start" or "end"
    est: float  # minutes
    lst: float  # minutes, inf if no upper bound applies
    slack: float


@dataclass(frozen=True)
class Schedule:
    rows: list[PointTime]
    critical_path: list[str]  # task element ids in topological order


def allmax_closure(stnu: STNU, extra: list[Edge] | None = None) -> Matrix | None:
    """Return the shortest-path matrix of the AllMax projection, or None if inconsistent. O(n^3)."""
    edges = stnu.edges + allmax_edges(stnu.links) + (extra or [])
    D = floyd_warshall(distance_matrix(len(stnu.timepoints), weighted(stnu, edges)))
    return None if negative_diagonal(D) is not None else D


def point_of(timepoint: str) -> str:
    return "end" if timepoint.endswith(":e") else "start"


def worst_case_schedule(stnu: STNU) -> Schedule | None:
    """Return EST/LST/slack of every timepoint with all contingent durations at their maximum.

    EST(X) = -D[X, Z], LST(X) = D[Z, X]. Returns None if the AllMax projection is inconsistent.
    The critical path lists tasks (timepoints ending in ':s') with zero start slack. O(n^3).
    """
    D = allmax_closure(stnu)
    if D is None:
        return None
    rows = []
    for i, tp in enumerate(stnu.timepoints):
        est, lst = -float(D[i, 0]), float(D[0, i])
        rows.append(PointTime(tp, stnu.origin[tp], point_of(tp), est, lst, lst - est))
    critical = [r.element for r in rows if r.timepoint.endswith(":s") and r.slack == 0]
    return Schedule(rows, critical)
