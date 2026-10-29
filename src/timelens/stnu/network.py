"""STNU data structure. Every weight is an integer linear form over named parameters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

ZERO_PARAM = "const.zero"


@dataclass(frozen=True)
class Param:
    id: str
    value: int  # minutes
    label: str  # business text, e.g. "KYC check, maximum"


@dataclass(frozen=True)
class LinForm:
    """sum(coef * param). Integer coefficients."""

    coefs: Mapping[str, int] = field(default_factory=dict)

    @staticmethod
    def of(param_id: str, coef: int = 1) -> LinForm:
        return LinForm({param_id: coef})

    def __neg__(self) -> LinForm:
        return LinForm({k: -v for k, v in self.coefs.items()})

    def __add__(self, other: LinForm) -> LinForm:
        out = dict(self.coefs)
        for k, v in other.coefs.items():
            out[k] = out.get(k, 0) + v
        return LinForm({k: v for k, v in out.items() if v})

    def value(self, params: Mapping[str, Param]) -> int:
        """Return the form evaluated at the parameter values. O(terms)."""
        return sum(c * params[p].value for p, c in self.coefs.items())

    def vector(self, index: Mapping[str, int]) -> npt.NDArray[np.int32]:
        """Return the coefficients as a dense vector in parameter `index` order."""
        v = np.zeros(len(index), dtype=np.int32)
        for p, c in self.coefs.items():
            v[index[p]] += c
        return v


ZERO = LinForm.of(ZERO_PARAM)


@dataclass(frozen=True)
class Edge:
    """Y - X <= weight, for src X and dst Y."""

    src: str
    dst: str
    weight: LinForm


@dataclass(frozen=True)
class ContingentLink:
    """`contingent` happens between `lower` and `upper` after `activation`. Nature picks."""

    activation: str
    contingent: str
    lower: LinForm
    upper: LinForm


@dataclass
class STNU:
    timepoints: list[str]  # index 0 MUST be "Z"
    edges: list[Edge]
    links: list[ContingentLink]
    params: dict[str, Param]
    origin: dict[str, str]  # timepoint -> BPMN element id

    def __post_init__(self) -> None:
        if not self.timepoints or self.timepoints[0] != "Z":
            raise ValueError("timepoint 0 must be Z")
        if len(set(self.timepoints)) != len(self.timepoints):
            raise ValueError("duplicate timepoints")
        known = set(self.timepoints)
        for e in self.edges:
            if e.src not in known or e.dst not in known:
                raise ValueError(f"edge {e.src} -> {e.dst} uses an unknown timepoint")
        ends = [lk.contingent for lk in self.links]
        if len(ends) != len(set(ends)):
            raise ValueError("a contingent end has more than one contingent link")
        for lk in self.links:
            if lk.activation not in known or lk.contingent not in known:
                raise ValueError(f"link to {lk.contingent} uses an unknown timepoint")
            if lk.activation in ends:
                raise ValueError(f"activation {lk.activation} is a contingent end")
            if lk.contingent == "Z":
                raise ValueError("Z cannot be a contingent end")
            lo, up = lk.lower.value(self.params), lk.upper.value(self.params)
            if not 0 <= lo <= up:
                raise ValueError(f"link {lk.activation} -> {lk.contingent}: need 0 <= {lo} <= {up}")

    @property
    def index(self) -> dict[str, int]:
        return {t: i for i, t in enumerate(self.timepoints)}

    @property
    def param_index(self) -> dict[str, int]:
        return {p: i for i, p in enumerate(self.params)}

    def param_values(self) -> npt.NDArray[np.int64]:
        return np.array([p.value for p in self.params.values()], dtype=np.int64)

    def contingent_ends(self) -> set[str]:
        return {lk.contingent for lk in self.links}

    def with_values(self, values: Mapping[str, int]) -> STNU:
        """Return a copy with some parameter values replaced."""
        params = {k: Param(k, values.get(k, p.value), p.label) for k, p in self.params.items()}
        return STNU(list(self.timepoints), list(self.edges), list(self.links), params,
                    dict(self.origin))


def weighted(stnu: STNU, edges: Iterable[Edge]) -> list[tuple[int, int, int]]:
    """Return edges as (src index, dst index, integer weight) triples."""
    idx = stnu.index
    return [(idx[e.src], idx[e.dst], e.weight.value(stnu.params)) for e in edges]
