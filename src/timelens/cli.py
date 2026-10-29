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

import typer

from timelens.analysis.repair import repair as run_repair
from timelens.analysis.verdict import check_process
from timelens.errors import TimeLensError
from timelens.model.process import load_model
from timelens.model.rules import load_levers
from timelens.report.text import NO_COST_NOTE, check_report, header, render, repair_block

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
def repair(model: Path, rules: Path, levers: Path, json_out: JsonOut = None) -> None:
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
    raise typer.Exit(1 if result.status == "NO_REPAIR" else 0)
