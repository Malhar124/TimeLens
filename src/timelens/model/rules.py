"""Pydantic schema for the time rules file (`*.rules.json`) and the levers file."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from timelens.errors import RulesError
from timelens.units import parse_minutes

Minutes = Annotated[int, BeforeValidator(parse_minutes)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TaskRule(_Strict):
    kind: Literal["contingent", "controllable"]
    owner: str | None = None
    min: Minutes
    max: Minutes

    @model_validator(mode="after")
    def _bounds(self) -> TaskRule:
        if self.min > self.max:
            raise ValueError(f"min ({self.min} m) > max ({self.max} m)")
        return self

    @property
    def is_contingent(self) -> bool:
        """True if nature picks the duration. A fixed contingent (min == max) is controllable."""
        return self.kind == "contingent" and self.min < self.max


class PointRef(_Strict):
    element: str
    point: Literal["start", "end"] = "start"


class Constraint(_Strict):
    id: str
    type: Literal["deadline", "lag"]
    label: str | None = None
    from_: PointRef = Field(alias="from")
    to: PointRef
    min: Minutes | None = None
    max: Minutes | None = None

    @model_validator(mode="after")
    def _bounds(self) -> Constraint:
        if self.type == "deadline" and (self.max is None or self.min is not None):
            raise ValueError(f"deadline {self.id}: needs 'max' and no 'min'")
        if self.type == "lag" and self.min is None and self.max is None:
            raise ValueError(f"lag {self.id}: needs 'min', 'max', or both")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"constraint {self.id}: min > max")
        return self


class FlowGap(_Strict):
    flow: str
    min: Minutes = 0
    max: Minutes | None = None

    @model_validator(mode="after")
    def _bounds(self) -> FlowGap:
        if self.max is not None and self.min > self.max:
            raise ValueError(f"flow gap {self.flow}: min > max")
        return self


class Rules(_Strict):
    process_id: str
    notes: str | None = None
    xor_outcome_known_at: Literal["start", "split"] = "split"
    tasks: dict[str, TaskRule]
    constraints: list[Constraint] = []
    flow_gaps: list[FlowGap] = []

    @model_validator(mode="after")
    def _unique(self) -> Rules:
        for what, ids in (
            ("constraint id", [c.id for c in self.constraints]),
            ("flow gap", [g.flow for g in self.flow_gaps]),
        ):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            if dupes:
                raise ValueError(f"duplicate {what}: {', '.join(dupes)}")
        return self

    def check_against(self, task_ids: set[str], element_ids: set[str], flow_ids: set[str]) -> None:
        """Raise RulesError if the rules do not match the BPMN ids. Warn on fixed contingents."""
        missing = sorted(task_ids - self.tasks.keys())
        if missing:
            raise RulesError(f"tasks without a time rule: {', '.join(missing)}")
        unknown = sorted(self.tasks.keys() - task_ids)
        if unknown:
            raise RulesError(f"time rules for unknown tasks: {', '.join(unknown)}")
        for c in self.constraints:
            if c.id in element_ids:
                raise RulesError(f"constraint id {c.id} clashes with a BPMN element id")
            for ref in (c.from_, c.to):
                if ref.element not in element_ids:
                    raise RulesError(f"constraint {c.id}: unknown element {ref.element}")
        for g in self.flow_gaps:
            if g.flow not in flow_ids:
                raise RulesError(f"flow gap: unknown sequence flow {g.flow}")
        for tid, t in self.tasks.items():
            if t.kind == "contingent" and t.min == t.max:
                warnings.warn(f"{tid}: contingent with min == max, treated as controllable",
                              stacklevel=2)


def load_rules(path: str | Path) -> Rules:
    """Return the validated rules file at `path`. Raises RulesError."""
    try:
        return Rules.model_validate(json.loads(Path(path).read_text()))
    except (ValidationError, json.JSONDecodeError, OSError) as e:
        raise RulesError(f"{path}: {e}") from e


class Lever(_Strict):
    id: str
    label: str
    param: str
    direction: Literal["increase", "decrease"]
    cost_per_day: float = Field(ge=0)
    max_change: Minutes


class Levers(_Strict):
    currency: str
    assumption_note: str
    granularity: Minutes = 1
    levers: list[Lever] = []

    @model_validator(mode="after")
    def _check(self) -> Levers:
        ids = [lv.id for lv in self.levers]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate lever id")
        if self.granularity < 1:
            raise ValueError("granularity must be at least 1 minute")
        return self


def load_levers(path: str | Path) -> Levers:
    """Return the validated levers YAML file at `path`. Raises RulesError."""
    try:
        return Levers.model_validate(yaml.safe_load(Path(path).read_text()))
    except (ValidationError, yaml.YAMLError, OSError) as e:
        raise RulesError(f"{path}: {e}") from e
