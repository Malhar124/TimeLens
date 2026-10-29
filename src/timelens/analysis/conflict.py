"""Conflict explanation: a negative cycle as budget vs demand in business words."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from timelens.model.process import ProcessGraph, Scenario
from timelens.model.rules import Rules
from timelens.stnu.build import build_stnu, user_constraint_ids
from timelens.stnu.dc import dc_check
from timelens.stnu.network import ZERO_PARAM, LinForm, Param
from timelens.units import format_minutes

_WIDTH = 58


@dataclass(frozen=True)
class Term:
    param: str
    label: str
    coefficient: int
    value_min: int


@dataclass(frozen=True)
class Conflict:
    scenario: str
    shortfall_min: int
    budget: list[Term]  # coefficient > 0: upper bounds such as deadlines
    demand: list[Term]  # coefficient < 0: maxima of contingent durations, minimum durations
    text: str

    @property
    def terms(self) -> list[Term]:
        return self.budget + self.demand


def _line(prefix: str, label: str, minutes: int) -> str:
    head = f"{prefix}{label} "
    return f"{head}{'.' * max(3, _WIDTH - len(head))} {format_minutes(minutes)}"


def explain(
    form: LinForm, params: Mapping[str, Param], scenario: str,
    title: str = "Not dynamically controllable.",
) -> Conflict:
    """Return the conflict for a negative cycle form. Zero-valued terms are left out. O(terms)."""
    terms = [Term(p, params[p].label, c, params[p].value)
             for p, c in form.coefs.items() if p != ZERO_PARAM and params[p].value != 0]
    order = list(params)
    terms.sort(key=lambda t: order.index(t.param))
    budget = [t for t in terms if t.coefficient > 0]
    demand = [t for t in terms if t.coefficient < 0]

    def show(t: Term) -> str:
        k = abs(t.coefficient)
        return t.label if k == 1 else f"{k} x {t.label}"

    def total(ts: list[Term]) -> int:
        return sum(abs(t.coefficient) * t.value_min for t in ts)

    lines = [title]
    for prefix, group, name in (("Budget:  ", budget, "budget"), ("Demand:  ", demand, "demand")):
        for k, t in enumerate(group):
            lines.append(_line(prefix if k == 0 else " " * 9, show(t), t.value_min))
        if len(group) > 1:
            lines.append(_line(" " * 9, f"Total {name}", total(group)))
    shortfall = -form.value(params)
    lines.append(f"Shortfall: {format_minutes(shortfall)}")
    return Conflict(scenario, shortfall, budget, demand, "\n".join(lines))


def deletion_filter(
    process: ProcessGraph,
    rules: Rules,
    scenario: Scenario | None = None,
    values: Mapping[str, int] | None = None,
) -> list[str]:
    """Return a minimal set of user constraints (lags, deadlines, flow gaps) that keeps the
    network NOT DC. Uses the fast engine without provenance. O(constraints * DC check)."""
    dropped: set[str] = set()
    ids = user_constraint_ids(rules)
    for cid in ids:
        trial: Collection[str] = dropped | {cid}
        if not dc_check(build_stnu(process, rules, scenario, values, trial), False).dc:
            dropped.add(cid)
    return [c for c in ids if c not in dropped]
