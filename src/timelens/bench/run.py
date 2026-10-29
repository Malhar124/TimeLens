"""Timing benchmark of the consistency, SC and DC checks on random structured processes."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import numpy as np
import pandas as pd

from timelens.bench.generate import random_model, random_rules
from timelens.model.process import ProcessGraph
from timelens.stnu.build import build_stnu
from timelens.stnu.dc import dc_check
from timelens.stnu.sc import strong_controllability
from timelens.stnu.stn import PROVENANCE_MAX_N, is_consistent

SIZES = (10, 25, 50, 100, 200, 300)
T = TypeVar("T")


def _timed(fn: Callable[..., T], *args: object) -> tuple[T, float]:
    t0 = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - t0


def run_bench(sizes: tuple[int, ...] = SIZES, models: int = 20, seed: int = 7,
              progress: Callable[[str], None] | None = None) -> pd.DataFrame:
    """Return one row per model: size, verdicts and wall times (s) on the union network."""
    rng = np.random.default_rng(seed)
    rows = []
    for size in sizes:
        for m in range(models):
            process = ProcessGraph(random_model(size, rng))
            stnu = build_stnu(process, random_rules(process, rng))
            n = len(stnu.timepoints)
            cons, t_cons = _timed(is_consistent, stnu)
            sc, t_sc = _timed(strong_controllability, stnu, False)
            dc, t_dc = _timed(dc_check, stnu, False)
            t_prov = float("nan")
            if n <= PROVENANCE_MAX_N:
                dc_p, t_prov = _timed(dc_check, stnu, True)
                assert dc_p.dc == dc.dc, "provenance mode changed the verdict"
            rows.append({"tasks": size, "model": m, "timepoints": n, "links": len(stnu.links),
                         "consistent": cons, "sc": sc.controllable, "dc": dc.dc,
                         "consistency_s": t_cons, "sc_s": t_sc, "dc_s": t_dc,
                         "dc_prov_s": t_prov})
            if progress:
                progress(f"size {size} model {m}: n={n} dc={dc.dc} {t_dc:.3f}s")
    return pd.DataFrame(rows)
