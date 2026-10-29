"""Report dictionaries (JSON shape of Section 9) and their console and markdown text."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from timelens.analysis.conflict import deletion_filter, explain
from timelens.analysis.repair import Repair
from timelens.analysis.schedule import worst_case_schedule
from timelens.analysis.verdict import NetworkResult, ProcessVerdict
from timelens.model.process import ProcessGraph
from timelens.model.rules import Rules
from timelens.units import format_minutes

NO_COST_NOTE = "No costs in this report. Durations and deadlines are model inputs."
Report = dict[str, Any]


def header(inputs: dict[str, str], assumption_note: str, alpha: float | None = None,
           deadline_choice: str | None = None) -> Report:
    """Return the header every report file starts with."""
    return {"date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"), "inputs": inputs,
            "alpha": alpha, "deadline_choice": deadline_choice,
            "assumption_note": assumption_note}


def _minutes(v: float) -> int | None:
    return None if math.isinf(v) else int(v)


def _conflict(process: ProcessGraph, rules: Rules, net: NetworkResult,
              values: dict[str, int] | None) -> Report:
    if net.dc.conflict is not None:
        c = explain(net.dc.conflict, net.stnu.params, net.name)
        return {"scenario": net.name, "shortfall_min": c.shortfall_min,
                "terms": [{"param": t.param, "label": t.label, "coefficient": t.coefficient,
                           "value_min": t.value_min} for t in c.terms],
                "text": c.text}
    scenario = next((s for s in process.scenarios() or [] if s.name == net.name), None)
    kept = deletion_filter(process, rules, scenario, values)
    return {"scenario": net.name, "shortfall_min": None, "terms": [], "kept_constraints": kept,
            "text": "Not dynamically controllable (network too large for provenance).\n"
                    f"These user constraints are enough to keep it NOT DC: {', '.join(kept)}"}


def check_report(process: ProcessGraph, rules: Rules, verdict: ProcessVerdict, head: Report,
                 force_schedule: bool = False, values: dict[str, int] | None = None) -> Report:
    """Return the `check` report: verdicts, worst-case schedule, critical path, conflicts."""
    dc = verdict.dynamically_controllable
    report: Report = {
        "header": head, "model": process.process_id, "xor_mode": verdict.xor_mode,
        "verdicts": {"consistent": verdict.consistent,
                     "strongly_controllable": verdict.strongly_controllable,
                     "dynamically_controllable": dc},
        "note": verdict.note, "schedule": [], "critical_path": [], "conflicts": [],
    }
    if dc == "DC" or force_schedule:
        sched = worst_case_schedule(verdict.union.stnu)
        if sched is not None:
            report["schedule"] = [
                {"element": r.element, "name": process.nodes[r.element].name, "point": r.point,
                 "est_min": _minutes(r.est), "lst_min": _minutes(r.lst),
                 "slack_min": _minutes(r.slack)} for r in sched.rows]
            report["critical_path"] = sched.critical_path
    if dc != "DC":
        report["conflicts"] = [_conflict(process, rules, n, values) for n in verdict.failing()]
    return report


def repair_block(r: Repair) -> Report:
    """Return the `repair` part of the report."""
    out: Report = {
        "status": r.status, "currency": r.currency, "total_cost": round(r.total_cost, 2),
        "lp_cost": round(r.lp_cost, 2), "lp_rounds": r.rounds,
        "assumption_note": r.assumption_note,
        "changes": [{"lever": c.lever, "label": c.label, "param": c.param, "old_min": c.old_min,
                     "new_min": c.new_min, "cost": round(c.cost, 2)} for c in r.changes],
    }
    if r.status == "NO_REPAIR":
        out["touching_levers"] = r.touching_levers
        out["last_conflict"] = r.conflict.text if r.conflict else None
        out["note"] = r.note
    return out


def _fmt(v: int | None) -> str:
    return "inf" if v is None else format_minutes(v)


def render(report: Report) -> str:
    """Return console text for a check or repair report."""
    h, v = report["header"], report["verdicts"]
    yes = {True: "yes", False: "no", None: "unknown"}
    lines = [f"TimeLens report  {h['date']}",
             "Inputs: " + ", ".join(f"{k}={p}" for k, p in h["inputs"].items())]
    if h["alpha"] is not None:
        lines.append(f"Calibration alpha: {h['alpha']}")
    if h["deadline_choice"]:
        lines.append(f"Deadline choice: {h['deadline_choice']}")
    lines.append(f"Assumptions: {h['assumption_note']}")
    if "repair" in report:
        rp = report["repair"]
        lines += ["", f"Repair: {rp['status']}  (LP rounds: {rp['lp_rounds']})"]
        for c in rp["changes"]:
            lines.append(f"  {c['label']} [{c['param']}]: {format_minutes(c['old_min'])} -> "
                         f"{format_minutes(c['new_min'])}, cost {c['cost']:,.0f} {rp['currency']}")
        lines.append(f"  Total cost: {rp['total_cost']:,.0f} {rp['currency']} (assumption)")
        if rp["status"] == "NO_REPAIR":
            lines.append(f"  Levers that touch the conflict: {rp['touching_levers'] or 'none'}")
            if rp.get("note"):
                lines.append(f"  {rp['note']}")
        lines += ["", "After repair:"]
    lines += [
        "", f"Model: {report['model']}  (XOR outcome known at: {report['xor_mode']})",
        f"Consistent:               {yes[v['consistent']]}",
        f"Strongly controllable:    {yes[v['strongly_controllable']]}",
        f"Dynamically controllable: {v['dynamically_controllable']}",
    ]
    if report["note"]:
        lines.append(f"Note: {report['note']}")
    if report["schedule"]:
        lines += ["", "Worst-case schedule (every contingent duration at its maximum):",
                  f"  {'element':<24}{'point':<7}{'EST':>14}{'LST':>14}{'slack':>14}"]
        for r in report["schedule"]:
            lines.append(f"  {r['name'][:23]:<24}{r['point']:<7}{_fmt(r['est_min']):>14}"
                         f"{_fmt(r['lst_min']):>14}{_fmt(r['slack_min']):>14}")
        lines.append("Critical path: " + " -> ".join(report["critical_path"]))
    for c in report["conflicts"]:
        lines += ["", f"Conflict in scenario '{c['scenario']}':", c["text"]]
    return "\n".join(lines)


def render_markdown(title: str, report: Report, body: str) -> str:
    """Return a markdown file: title, header block, then `body`."""
    h = report["header"]
    lines = [f"# {title}", "", f"- Date: {h['date']}",
             *[f"- Input {k}: `{p}`" for k, p in h["inputs"].items()],
             f"- Alpha: {h['alpha'] if h['alpha'] is not None else 'n/a'}",
             f"- Deadline choice: {h['deadline_choice'] or 'n/a'}",
             f"- Assumptions: {h['assumption_note']}", "", body, ""]
    return "\n".join(lines)
