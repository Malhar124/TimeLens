"""Conflict-directed repair at minimum lever cost, after CDRU (Yu, Fang, Williams, ICAPS 2014)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.optimize import linprog

from timelens.analysis.conflict import Conflict, explain
from timelens.analysis.verdict import ProcessVerdict, check_process
from timelens.errors import RulesError
from timelens.model.process import ProcessGraph
from timelens.model.rules import Levers, Rules
from timelens.stnu.build import build_params

MAX_ITERATIONS = 100
RepairStatus = Literal["ALREADY_DC", "REPAIRED", "NO_REPAIR"]


@dataclass(frozen=True)
class Change:
    lever: str
    label: str
    param: str
    old_min: int
    new_min: int
    cost: float


@dataclass(frozen=True)
class Repair:
    status: RepairStatus
    currency: str
    assumption_note: str
    changes: list[Change]
    total_cost: float
    lp_cost: float
    rounds: int
    values: dict[str, int]  # parameter values after the repair
    verdict: ProcessVerdict  # verdict at `values`
    conflict: Conflict | None = None  # NO_REPAIR: the last conflict
    touching_levers: list[str] = field(default_factory=list)
    note: str = ""


def lever_bounds(levers: Levers, values: dict[str, int]) -> list[tuple[int, int]]:
    """Return (low, high) bounds of each lever's change in minutes. Raises RulesError."""
    out = []
    for lv in levers.levers:
        if lv.param not in values:
            raise RulesError(f"lever {lv.id}: unknown parameter {lv.param}")
        base, _, bound = lv.param.rpartition(".")
        lo, hi = (0, lv.max_change) if lv.direction == "increase" else (-lv.max_change, 0)
        if bound == "max" and f"{base}.min" in values:  # a max must not go below its min
            lo = max(lo, values[f"{base}.min"] - values[lv.param])
        if bound == "min" and f"{base}.max" in values:  # a min must not go above its max
            hi = min(hi, values[f"{base}.max"] - values[lv.param])
        out.append((lo, hi))
    return out


def _round(deltas: np.ndarray, bounds: list[tuple[int, int]], step: int) -> list[int]:
    """Round each change away from zero to a multiple of `step`, then clip to its bounds."""
    out = []
    for d, (lo, hi) in zip(deltas, bounds, strict=True):
        k = math.ceil(abs(float(d)) / step - 1e-9)
        out.append(min(hi, max(lo, int(math.copysign(k * step, d)))))
    return out


def repair(process: ProcessGraph, rules: Rules, levers: Levers) -> Repair:
    """Return the cheapest lever changes that make the process DC.

    Each round: check DC at the rounded changes; if not DC, add the cut sum_k a_k * delta_k >=
    -W(p0) from the conflict W and re-solve the LP from the original values with all cuts.
    O(iterations * (DC check + LP)).
    """
    base_params = build_params(process, rules)
    base = {k: p.value for k, p in base_params.items()}
    bounds = lever_bounds(levers, base)
    rate = np.array([lv.cost_per_day / 1440 for lv in levers.levers])
    sign = np.array([1.0 if lv.direction == "increase" else -1.0 for lv in levers.levers])
    cuts: list[tuple[list[int], int]] = []
    lp_deltas = np.zeros(len(levers.levers))
    lp_cost = 0.0

    def finish(status: RepairStatus, deltas: list[int], values: dict[str, int],
               verdict: ProcessVerdict, rounds: int, conflict: Conflict | None = None,
               touching: list[str] | None = None, note: str = "") -> Repair:
        changes = [Change(lv.id, lv.label, lv.param, base[lv.param], base[lv.param] + d,
                          float(rate[k] * abs(d)))
                   for k, (lv, d) in enumerate(zip(levers.levers, deltas, strict=True)) if d]
        return Repair(status, levers.currency, levers.assumption_note, changes,
                      sum(c.cost for c in changes), lp_cost, rounds, values, verdict,
                      conflict, touching or [], note)

    for rounds in range(1, MAX_ITERATIONS + 1):
        deltas = _round(lp_deltas, bounds, levers.granularity)
        values = dict(base)
        for lv, d in zip(levers.levers, deltas, strict=True):
            values[lv.param] += d
        verdict = check_process(process, rules, values)
        if verdict.dynamically_controllable == "DC":
            return finish("ALREADY_DC" if not any(deltas) else "REPAIRED", deltas, values,
                          verdict, rounds)
        target = verdict.repair_target()
        assert target is not None
        form = target.dc.conflict
        if form is None:
            return finish("NO_REPAIR", deltas, values, verdict, rounds,
                          note="Network too large for provenance (n > 200): no conflict cuts.")
        coef = [form.coefs.get(lv.param, 0) for lv in levers.levers]
        cuts.append((coef, -form.value(base_params)))
        conflict = explain(form, target.stnu.params, target.name)
        touching = [lv.id for lv, a in zip(levers.levers, coef, strict=True) if a]
        if not levers.levers:
            return finish("NO_REPAIR", deltas, values, verdict, rounds, conflict=conflict)
        res = linprog(rate * sign, A_ub=-np.array([c for c, _ in cuts], dtype=float),
                      b_ub=-np.array([r for _, r in cuts], dtype=float),
                      bounds=bounds, method="highs")
        if res.status == 2:  # infeasible
            return finish("NO_REPAIR", deltas, values, verdict, rounds, conflict, touching)
        if not res.success:
            raise RuntimeError(f"LP solver failed: {res.message}")
        lp_deltas, lp_cost = res.x, float(res.fun)
    raise RuntimeError("repair did not converge")
