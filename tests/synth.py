"""Deterministic synthetic event logs shaped like BPI 2017 (activity names of the mapping)."""

import numpy as np
import pandas as pd

from timelens.mining.log import ACT, CASE, LIFE, TIME

BASE = pd.Timestamp("2016-01-01", tz="UTC")


def synthetic_log(n_cases: int = 300, seed: int = 1, slow_share: float = 0.2) -> pd.DataFrame:
    """Return an event log. A `slow_share` of cases has a long customer return."""
    rng = np.random.default_rng(seed)
    rows = []

    def ev(cid, act, life, t):
        rows.append((cid, act, life, t))

    for i in range(n_cases):
        cid, t = f"Application_{i}", BASE + pd.Timedelta(hours=6 * i)
        def mins(lo, hi):
            return pd.Timedelta(minutes=int(rng.integers(lo, hi)))

        ev(cid, "A_Create Application", "complete", t)
        t += mins(10, 120)
        ev(cid, "W_Complete application", "start", t)
        t += mins(60, 2880)
        ev(cid, "W_Complete application", "complete", t)
        t += mins(0, 60)
        ev(cid, "O_Sent (mail and online)", "complete", t)
        slow = rng.random() < slow_share
        t += mins(10 * 1440, 25 * 1440) if slow else mins(1440, 7 * 1440)
        ev(cid, "O_Returned", "complete", t)
        t += mins(0, 600)
        ev(cid, "W_Validate application", "start", t)
        t += mins(30, 1440)
        ev(cid, "W_Validate application", "complete", t)
        t += mins(0, 60)
        ev(cid, {3: "A_Denied", 7: "A_Cancelled"}.get(i % 10, "A_Pending"), "complete", t)
    return pd.DataFrame(rows, columns=[CASE, ACT, LIFE, TIME])
