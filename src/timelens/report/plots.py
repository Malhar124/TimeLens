"""PNG plots: risk vs cost frontier and benchmark timings. Uses Figure, so no GUI backend."""

from __future__ import annotations

import math
import textwrap
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

from timelens.analysis.frontier import FrontierPoint


def frontier_png(points: list[FrontierPoint], path: Path, currency: str, caption: str) -> None:
    """Write the frontier: x = risk in %, y = minimum repair cost, one labeled point per alpha."""
    fig = Figure(figsize=(7, 4.5))
    ax = fig.subplots()
    ok = [p for p in points if not math.isnan(p.cost)]
    ax.plot([p.risk * 100 for p in ok], [p.cost for p in ok], "o-", color="#1f5f99")
    for p in ok:
        ax.annotate(f"alpha={p.alpha:.2f}", (p.risk * 100, p.cost), textcoords="offset points",
                    xytext=(6, 6), fontsize=8)
    for p in points:
        if math.isnan(p.cost):  # plotted as a marker so the axis range includes it
            ax.plot(p.risk * 100, 0, "x", color="#b03030", markersize=9)
            ax.annotate(f"alpha={p.alpha:.2f}: no repair", (p.risk * 100, 0),
                        textcoords="offset points", xytext=(6, 6), fontsize=8, color="#b03030")
    ax.set_xlabel("Risk: test cases outside a calibrated range (%)")
    ax.set_ylabel(f"Minimum repair cost ({currency}, assumption)")
    ax.set_title("TimeLens risk vs cost frontier")
    ax.grid(alpha=0.3)
    fig.text(0.01, 0.01, textwrap.fill(caption, 120), fontsize=7)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=130)


def bench_png(table: pd.DataFrame, path: Path) -> None:
    """Write median wall time per model size and check, log scale."""
    fig = Figure(figsize=(7, 4.5))
    ax = fig.subplots()
    med = table.groupby("tasks").median(numeric_only=True)
    for col, label in (("consistency_s", "consistency"), ("sc_s", "strong controllability"),
                       ("dc_s", "DC (fast engine)"), ("dc_prov_s", "DC with provenance")):
        if col in med and med[col].notna().any():
            ax.plot(med.index, med[col], "o-", label=label)
    ax.set_yscale("log")
    ax.set_xlabel("tasks per model")
    ax.set_ylabel("median wall time (s)")
    ax.set_title("TimeLens benchmark")
    ax.grid(alpha=0.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
