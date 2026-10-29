"""Risk vs cost frontier: calibrate at each alpha, check DC, repair at minimum cost."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from timelens.analysis.repair import repair
from timelens.analysis.verdict import check_process
from timelens.mining.calibrate import calibrate_template
from timelens.model.process import ProcessGraph
from timelens.model.rules import Levers, Rules

ALPHAS = (0.80, 0.85, 0.90, 0.95, 0.99)


@dataclass(frozen=True)
class FrontierPoint:
    alpha: float
    risk: float  # 1 - empirical joint coverage on the test set
    verdict: str  # DC verdict before repair
    status: str  # ALREADY_DC, REPAIRED or NO_REPAIR
    cost: float  # minimum repair cost, NaN if NO_REPAIR
    changes: str
    note: str


def frontier(process: ProcessGraph, train: pd.DataFrame, test: pd.DataFrame,
             template: dict[str, Any], levers: Levers, deadline_min: int, deadline_note: str,
             alphas: tuple[float, ...] = ALPHAS) -> list[FrontierPoint]:
    """Return one frontier point per alpha. O(alphas * repair)."""
    points = []
    for alpha in alphas:
        cal = calibrate_template(train, test, template, alpha, deadline_min, deadline_note)
        rules = Rules.model_validate(cal.rules)
        rules.check_against(set(process.tasks), set(process.nodes), set(process.flows))
        verdict = check_process(process, rules).dynamically_controllable
        r = repair(process, rules, levers)
        cost = math.nan if r.status == "NO_REPAIR" else r.total_cost
        changes = "; ".join(f"{c.lever} {c.new_min - c.old_min:+d} m" for c in r.changes)
        note = "no repair within the lever limits" if r.status == "NO_REPAIR" else ""
        points.append(FrontierPoint(alpha, cal.risk, verdict, r.status, cost, changes, note))
    return points


def cost_never_decreases(points: list[FrontierPoint]) -> bool:
    """Return True if cost is non-decreasing in alpha (NO_REPAIR counts as infinite cost)."""
    costs = [math.inf if math.isnan(p.cost) else p.cost for p in sorted(points,
                                                                         key=lambda p: p.alpha)]
    return all(a <= b + 1e-6 for a, b in zip(costs, costs[1:], strict=False))
