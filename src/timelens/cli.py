"""TimeLens command line interface."""

from __future__ import annotations

import typer

app = typer.Typer(help="TimeLens: temporal constraint analysis for BPMN processes.")


@app.callback()
def main() -> None:
    """TimeLens commands."""
