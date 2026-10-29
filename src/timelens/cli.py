"""TimeLens command line interface.

Exit codes: 0 success and DC, 1 success and NOT DC (or NO_REPAIR), 2 input error,
3 internal error.
"""

from __future__ import annotations

import functools
import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, ParamSpec, TypeVar

import pandas as pd
import typer

from timelens.analysis.alerts import evaluate, traces_from_times
from timelens.analysis.frontier import cost_never_decreases
from timelens.analysis.frontier import frontier as run_frontier
from timelens.analysis.repair import repair as run_repair
from timelens.analysis.verdict import check_process
from timelens.errors import TimeLensError
from timelens.mining.calibrate import (
    CalibrationResult,
    calibrate_template,
    case_duration_stats,
    default_deadline_days,
)
from timelens.mining.log import case_times, discover, load_log, load_mapping, split_by_time
from timelens.model.process import load_model, load_process
from timelens.model.rules import Rules, load_levers, rules_with_values
from timelens.report.text import (
    NO_COST_NOTE,
    check_report,
    header,
    render,
    render_markdown,
    repair_block,
)
from timelens.stnu.build import build_stnu
from timelens.units import format_minutes

app = typer.Typer(help="TimeLens: temporal constraint analysis for BPMN processes.",
                  no_args_is_help=True)

P = ParamSpec("P")
T = TypeVar("T")
JsonOut = Annotated[Path | None, typer.Option("--json", help="Write the JSON report here.")]


def guarded(fn: Callable[P, T]) -> Callable[P, T]:
    """Map input errors to exit code 2 and unexpected errors to exit code 3."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except TimeLensError as e:
            typer.echo(f"Input error: {e}", err=True)
            raise typer.Exit(2) from e
        except Exception as e:
            traceback.print_exc()
            typer.echo(f"Internal error: {e}", err=True)
            raise typer.Exit(3) from e

    return wrapper


def _write_json(path: Path | None, report: dict[str, Any]) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2))
        typer.echo(f"JSON report: {path}")


@app.command()
@guarded
def check(model: Path, rules: Path, json_out: JsonOut = None,
          force_schedule: Annotated[bool, typer.Option(help="Print the schedule even if not DC.")]
          = False) -> None:
    """Check consistency, strong and dynamic controllability; print schedule or conflicts."""
    process, r = load_model(model, rules)
    verdict = check_process(process, r)
    head = header({"model": str(model), "rules": str(rules)}, NO_COST_NOTE,
                  deadline_choice=r.notes)
    report = check_report(process, r, verdict, head, force_schedule)
    typer.echo(render(report))
    _write_json(json_out, report)
    raise typer.Exit(0 if verdict.dynamically_controllable == "DC" else 1)


@app.command()
@guarded
def repair(model: Path, rules: Path, levers: Path, json_out: JsonOut = None,
           rules_out: Annotated[Path | None, typer.Option(
               help="Write the repaired rules JSON here (input for alerts-eval).")] = None) -> None:
    """Find the cheapest lever changes that make the process dynamically controllable."""
    process, r = load_model(model, rules)
    lv = load_levers(levers)
    before = check_process(process, r)
    result = run_repair(process, r, lv)
    head = header({"model": str(model), "rules": str(rules), "levers": str(levers)},
                  lv.assumption_note, deadline_choice=r.notes)
    report = check_report(process, r, result.verdict, head, values=result.values)
    report["verdicts_before"] = {
        "consistent": before.consistent, "strongly_controllable": before.strongly_controllable,
        "dynamically_controllable": before.dynamically_controllable}
    report["repair"] = repair_block(result)
    typer.echo(render(report))
    _write_json(json_out, report)
    if rules_out is not None and result.status != "NO_REPAIR":
        rules_out.parent.mkdir(parents=True, exist_ok=True)
        rules_out.write_text(json.dumps(rules_with_values(r, result.values), indent=2))
        typer.echo(f"Repaired rules: {rules_out}")
    raise typer.Exit(1 if result.status == "NO_REPAIR" else 0)


@app.command("discover-log")
@guarded
def discover_log(log: Path) -> None:
    """Print every activity with its lifecycle values and counts."""
    table = discover(load_log(log))
    typer.echo(f"{'activity':<40}{'lifecycle':<16}{'count':>8}")
    for row in table.itertuples(index=False):
        typer.echo(f"{row[0]:<40}{row[1]:<16}{row[2]:>8}")


def _prepare(log: Path, mapping: Path) -> tuple[Any, Any]:
    """Return (train, test) case time tables, split 70/30 by case start."""
    times = case_times(load_log(log), load_mapping(mapping))
    return split_by_time(times)


def _deadline(train: Any, days: int | None) -> tuple[int, str]:
    """Return (deadline in minutes, reason text). Prints the case duration distribution."""
    st = case_duration_stats(train)
    typer.echo(f"Case duration (training set, n={st['n']}): median "
               f"{format_minutes(round(st['median']))}, p80 {format_minutes(round(st['p80']))}, "
               f"p90 {format_minutes(round(st['p90']))}")
    if days is not None:
        return days * 1440, f"Deadline {days} d, chosen by the user (assumption: the log has none)."
    d = default_deadline_days(st)
    return d * 1440, (f"Deadline {d} d = 90th percentile of training case durations "
                      f"({format_minutes(round(st['p90']))}) rounded up to whole days; "
                      "no user choice given (assumption: the log has no official deadline).")


def _print_calibration(res: CalibrationResult) -> None:
    typer.echo(f"{'task':<24}{'n':>7}{'dropped':>9}{'min':>14}{'max':>14}{'alpha':>7}")
    for c in res.table:
        flag = "" if c.calibrated else "  (not calibrated: < 30 samples)"
        typer.echo(f"{c.task:<24}{c.n:>7}{c.dropped:>9}{format_minutes(c.min):>14}"
                   f"{format_minutes(c.max):>14}{c.alpha:>7}{flag}")
    typer.echo(f"Joint coverage on the test set: {res.coverage:.3f} "
               f"({res.coverage_cases} cases), risk {res.risk:.3f}")


DeadlineDays = Annotated[int | None, typer.Option(
    help="Deadline in whole days. Default: p90 of case durations, rounded up.")]


@app.command()
@guarded
def calibrate(log: Path, mapping: Path, template: Path,
              out: Annotated[Path, typer.Option(help="Calibrated rules JSON to write.")],
              alpha: Annotated[float, typer.Option(min=0.5, max=0.999)] = 0.95,
              deadline_days: DeadlineDays = None) -> None:
    """Calibrate contingent duration ranges from the event log (train on the first 70 %)."""
    train, test = _prepare(log, mapping)
    deadline, reason = _deadline(train, deadline_days)
    typer.echo(reason)
    res = calibrate_template(train, test, json.loads(template.read_text()), alpha, deadline,
                             reason)
    Rules.model_validate(res.rules)
    _print_calibration(res)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res.rules, indent=2))
    typer.echo(f"Rules written: {out}")


ResultsDir = Annotated[Path, typer.Option(help="Directory for result files.")]


def _csv_header(head: dict[str, Any]) -> str:
    """Return the report header as '#' comment lines for CSV files."""
    lines = [f"date: {head['date']}", *[f"input {k}: {v}" for k, v in head["inputs"].items()],
             f"alpha: {head['alpha']}", f"deadline choice: {head['deadline_choice']}",
             f"assumptions: {head['assumption_note']}"]
    return "".join(f"# {x}\n" for x in lines)


@app.command()
@guarded
def frontier(model: Path, log: Path, mapping: Path, template: Path, levers: Path,
             deadline_days: DeadlineDays = None, out_dir: ResultsDir = Path("results")) -> None:
    """Risk vs cost frontier over alpha in 0.80, 0.85, 0.90, 0.95, 0.99."""
    from timelens.report.plots import frontier_png

    process, lv = load_process(model), load_levers(levers)
    train, test = _prepare(log, mapping)
    deadline, reason = _deadline(train, deadline_days)
    typer.echo(reason)
    points = run_frontier(process, train, test, json.loads(template.read_text()), lv, deadline,
                          reason)
    head = header({"model": str(model), "log": str(log), "mapping": str(mapping),
                   "template": str(template), "levers": str(levers)}, lv.assumption_note,
                  alpha="0.80,0.85,0.90,0.95,0.99", deadline_choice=reason)
    typer.echo(f"{'alpha':>6}{'risk %':>9}{'verdict':>10}{'status':>12}{'cost':>14}  changes")
    for p in points:
        typer.echo(f"{p.alpha:>6.2f}{p.risk * 100:>9.2f}{p.verdict:>10}{p.status:>12}"
                   f"{p.cost:>14,.0f}  {p.changes or '-'} {p.note}")
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [vars(p) for p in points]
    with (out_dir / "frontier.csv").open("w") as f:
        f.write(_csv_header(head))
        f.write(pd.DataFrame(rows).to_csv(index=False))
    frontier_png(points, out_dir / "frontier.png", lv.currency,
                 f"{lv.assumption_note} {reason}")
    typer.echo(f"Wrote {out_dir / 'frontier.csv'} and {out_dir / 'frontier.png'}")
    if not cost_never_decreases(points):
        typer.echo("BUG: minimum cost goes down when alpha goes up. Please report it.", err=True)
        raise typer.Exit(3)


def _score_line(name: str, sc: dict[str, Any]) -> str:
    lead = sc["median_lead_min"]
    lead_txt = "n/a" if lead != lead else format_minutes(round(lead))
    return (f"| {name} | {sc['alerts']} | {sc['tp']} | {sc['fp']} | {sc['fn']} | "
            f"{sc['precision']:.3f} | {sc['recall']:.3f} | {sc['f1']:.3f} | {lead_txt} |")


@app.command("alerts-eval")
@guarded
def alerts_eval(model: Path, rules: Path, log: Path, mapping: Path,
                out_dir: ResultsDir = Path("results")) -> None:
    """Replay the test cases (last 30 %) with run-time alerts; compare with a static rule."""
    process, r = load_model(model, rules)
    deadline_c = next((c for c in r.constraints if c.type == "deadline"), None)
    if deadline_c is None or deadline_c.max is None:
        raise TimeLensError("alerts-eval needs a deadline constraint in the rules")
    if check_process(process, r).dynamically_controllable != "DC":
        typer.echo("Warning: these rules are not DC, so the worst case already misses the "
                   "deadline and every case alerts at once. Pass repaired rules "
                   "(timelens repair ... --rules-out).", err=True)
    _, test = _prepare(log, mapping)
    traces, skipped = traces_from_times(test, process, process.tasks)
    names = {f"{t}:s": process.nodes[t].name for t in process.tasks}
    res = evaluate(build_stnu(process, r), traces, deadline_c.max, names)
    head = header({"model": str(model), "rules": str(rules), "log": str(log),
                   "mapping": str(mapping)}, NO_COST_NOTE, deadline_choice=r.notes)
    report = {"header": head, "deadline_min": deadline_c.max, "test_cases_used": len(traces),
              "test_cases_skipped": skipped, **res}
    table = "\n".join([
        f"Test cases used: {len(traces)}, skipped (missing or bad events): {skipped}. "
        f"Deadline: {format_minutes(deadline_c.max)}. Late: {res['timelens']['late']}.", "",
        "| method | alerts | TP | FP | FN | precision | recall | F1 | median lead |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        _score_line("TimeLens latest safe start", res["timelens"]),
        _score_line("Static: no decision by deadline - 3 d", res["static_baseline"]),
        "", "TimeLens is useful only if it alerts earlier at similar precision.",
    ])
    typer.echo(table)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "alerts_eval.json").write_text(json.dumps(report, indent=2))
    (out_dir / "alerts_eval.md").write_text(render_markdown("TimeLens alert evaluation",
                                                            report, table))
    typer.echo(f"Wrote {out_dir / 'alerts_eval.json'} and {out_dir / 'alerts_eval.md'}")
