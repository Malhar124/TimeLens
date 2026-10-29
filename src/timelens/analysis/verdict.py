"""Process-level verdicts: consistency, SC and DC over XOR scenarios and the union network."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from timelens.model.process import ProcessGraph, Scenario
from timelens.model.rules import Rules
from timelens.stnu.build import build_stnu
from timelens.stnu.dc import DCResult, dc_check
from timelens.stnu.network import STNU
from timelens.stnu.sc import SCResult, strong_controllability
from timelens.stnu.stn import is_consistent

DCVerdict = Literal["DC", "NOT_DC", "UNKNOWN_XOR"]

UNKNOWN_NOTE = (
    "Every XOR scenario is DC (necessary), but the union network is not DC (only sufficient). "
    "With xor_outcome_known_at = 'split' the exact verdict needs a CSTNU solver; "
    "the CSTNU Tool oracle is not configured."
)


@dataclass(frozen=True)
class NetworkResult:
    name: str
    stnu: STNU
    consistent: bool
    sc: SCResult
    dc: DCResult


@dataclass(frozen=True)
class ProcessVerdict:
    xor_mode: str
    scenarios: list[NetworkResult] | None  # None if above the scenario cap
    union: NetworkResult
    consistent: bool
    strongly_controllable: bool | None  # None: unknown (XOR split mode)
    dynamically_controllable: DCVerdict
    note: str

    def failing(self) -> list[NetworkResult]:
        """Return the networks whose conflicts explain a NOT_DC or UNKNOWN_XOR verdict."""
        bad = [s for s in self.scenarios or [] if not s.dc.dc]
        return bad or ([self.union] if not self.union.dc.dc else [])

    def repair_target(self) -> NetworkResult | None:
        """Return the network to cut on: first failing scenario ('start'), else the union."""
        if self.dynamically_controllable == "DC":
            return None
        if self.xor_mode == "start" and self.scenarios:
            return next((s for s in self.scenarios if not s.dc.dc), self.union)
        return self.union


def analyze(stnu: STNU, name: str, provenance: bool | None = None) -> NetworkResult:
    """Run the consistency, SC and DC checks on one network."""
    return NetworkResult(name, stnu, is_consistent(stnu), strong_controllability(stnu, provenance),
                         dc_check(stnu, provenance))


def _combine(union_ok: bool, scenario_oks: list[bool] | None) -> bool | None:
    """Union OK is sufficient; a failing scenario is decisive; else unknown."""
    if union_ok:
        return True
    if scenario_oks is not None and not all(scenario_oks):
        return False
    return None


def check_process(
    process: ProcessGraph,
    rules: Rules,
    values: Mapping[str, int] | None = None,
    provenance: bool | None = None,
) -> ProcessVerdict:
    """Return the process verdicts for the XOR mode of `rules`. O(scenarios * DC check)."""
    mode = rules.xor_outcome_known_at
    union = analyze(build_stnu(process, rules, None, values), "union", provenance)
    if not process.has_xor():
        default = NetworkResult("default", union.stnu, union.consistent, union.sc, union.dc)
        return ProcessVerdict(mode, [default], default, default.consistent,
                              default.sc.controllable, "DC" if default.dc.dc else "NOT_DC", "")
    found: list[Scenario] | None = process.scenarios()
    scen = None if found is None else [
        analyze(build_stnu(process, rules, s, values), s.name, provenance) for s in found]
    note = "" if scen is not None else "More than 256 XOR scenarios: only the union check ran."
    consistent = all(s.consistent for s in scen) if scen is not None else union.consistent
    if mode == "start" and scen is not None:
        sc: bool | None = all(s.sc.controllable for s in scen)
        dc: DCVerdict = "DC" if all(s.dc.dc for s in scen) else "NOT_DC"
    else:
        sc = _combine(union.sc.controllable, None if scen is None else
                      [s.sc.controllable for s in scen])
        verdict = _combine(union.dc.dc, None if scen is None else [s.dc.dc for s in scen])
        dc = "DC" if verdict else "NOT_DC" if verdict is False else "UNKNOWN_XOR"
        if dc == "UNKNOWN_XOR":
            note = (note + " " + UNKNOWN_NOTE).strip()
    return ProcessVerdict(mode, scen, union, consistent, sc, dc, note)
