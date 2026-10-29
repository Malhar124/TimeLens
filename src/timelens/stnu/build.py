"""Map a ProcessGraph plus time rules to an STNU, per XOR scenario or for the union network.

XOR verdicts (Section 6.3 of the build guide):

* Per-scenario DC is NECESSARY for the process to be DC. Proof: a strategy for the whole
  process, restricted to the cases where one scenario happens, is a strategy for that scenario's
  network, because it meets every constraint of that scenario.
* Union DC is SUFFICIENT. Proof: the union network contains every timepoint and every constraint
  of each scenario. A scenario XOR join has one edge from its one active branch; the union join
  has edges from all branches, so the scenario join constraint is weaker. Hence every union
  schedule (and every union strategy) satisfies each scenario network; the extra timepoints of
  inactive branches are only ignored.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from timelens.model.process import ProcessGraph, Scenario
from timelens.model.rules import Rules
from timelens.stnu.network import STNU, ZERO, ZERO_PARAM, ContingentLink, Edge, LinForm, Param


def timepoint(process: ProcessGraph, element: str, point: str) -> str:
    """Return the timepoint name of an element's start or end point."""
    node = process.nodes[element]
    if node.kind == "start":
        return "Z"
    if node.kind == "task":
        return f"{element}:{'s' if point == 'start' else 'e'}"
    return element


def build_params(
    process: ProcessGraph, rules: Rules, values: Mapping[str, int] | None = None
) -> dict[str, Param]:
    """Return every parameter of the rules file with its business label. `values` overrides."""
    out = [Param(ZERO_PARAM, 0, "zero")]
    for tid, t in rules.tasks.items():
        name = process.nodes[tid].name
        who = f" ({t.owner})" if t.owner not in (None, "staff") else ""
        out.append(Param(f"{tid}.min", t.min, f"{name}{who}, minimum"))
        out.append(Param(f"{tid}.max", t.max, f"{name}{who}, maximum"))
    for c in rules.constraints:
        label = c.label or c.id
        both = c.min is not None and c.max is not None
        for bound, v in (("min", c.min), ("max", c.max)):
            if v is not None:
                suffix = f", {bound}imum" if both else ""
                out.append(Param(f"{c.id}.{bound}", v, label + suffix))
    for g in rules.flow_gaps:
        f = process.flows[g.flow]
        base = f"Gap {process.nodes[f.src].name} -> {process.nodes[f.dst].name}"
        out.append(Param(f"{g.flow}.min", g.min, f"{base}, minimum"))
        if g.max is not None:
            out.append(Param(f"{g.flow}.max", g.max, f"{base}, maximum"))
    values = values or {}
    return {p.id: Param(p.id, values.get(p.id, p.value), p.label) for p in out}


def build_stnu(
    process: ProcessGraph,
    rules: Rules,
    scenario: Scenario | None = None,
    values: Mapping[str, int] | None = None,
    drop: Collection[str] = (),
) -> STNU:
    """Return the STNU of one scenario (default: the union network). O(nodes + rules).

    `values` overrides parameter values (used by repair); `drop` removes user constraints and
    flow gaps by id (used by the deletion filter).
    """
    scenario = scenario or process.union()
    params = build_params(process, rules, values)
    active = scenario.nodes
    tps, origin = ["Z"], {"Z": process.start}
    edges: list[Edge] = []
    links: list[ContingentLink] = []
    for n in process.topo:
        if n not in active or n == process.start:
            continue
        if process.nodes[n].kind != "task":
            tps.append(n)
            origin[n] = n
            continue
        s, e = f"{n}:s", f"{n}:e"
        tps += [s, e]
        origin[s] = origin[e] = n
        lo, up = LinForm.of(f"{n}.min"), LinForm.of(f"{n}.max")
        task = rules.tasks[n]
        if task.kind == "contingent" and params[f"{n}.min"].value < params[f"{n}.max"].value:
            links.append(ContingentLink(s, e, lo, up))
        else:
            edges += [Edge(s, e, up), Edge(e, s, -lo)]

    gaps = {g.flow: g for g in rules.flow_gaps if g.flow not in drop}
    for fid in sorted(scenario.flows):
        f = process.flows[fid]
        p_out, s_in = timepoint(process, f.src, "end"), timepoint(process, f.dst, "start")
        gap = gaps.get(fid)
        edges.append(Edge(s_in, p_out, -LinForm.of(f"{fid}.min") if gap else -ZERO))
        if gap is not None and gap.max is not None:
            edges.append(Edge(p_out, s_in, LinForm.of(f"{fid}.max")))

    for c in rules.constraints:
        if c.id in drop or c.from_.element not in active or c.to.element not in active:
            continue
        x = timepoint(process, c.from_.element, c.from_.point)
        y = timepoint(process, c.to.element, c.to.point)
        if c.max is not None:
            edges.append(Edge(x, y, LinForm.of(f"{c.id}.max")))
        if c.min is not None:
            edges.append(Edge(y, x, -LinForm.of(f"{c.id}.min")))

    edges += [Edge(t, "Z", ZERO) for t in tps[1:]]  # nothing happens before the case starts
    return STNU(tps, edges, links, params, origin)


def user_constraint_ids(rules: Rules) -> list[str]:
    """Return the ids the deletion filter may drop: lags, deadlines, flow gaps."""
    return [c.id for c in rules.constraints] + [g.flow for g in rules.flow_gaps]
