"""Event log: load (XES or CSV, cached as parquet), map events to timepoints, split by time."""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from timelens.errors import LogMappingError

CASE, ACT = "case:concept:name", "concept:name"
LIFE, TIME = "lifecycle:transition", "time:timestamp"
COLUMNS = [CASE, ACT, LIFE, TIME]


def cache_path(path: Path) -> Path:
    """Return the parquet cache next to the log ("x.xes.gz" or "x.csv" -> "x.parquet")."""
    return path.with_name(re.sub(r"\.(xes(\.gz)?|csv)$", "", path.name) + ".parquet")


def _read_xes(path: Path) -> pd.DataFrame:
    import pm4py  # slow import with a banner: load only when parsing XES

    log = pm4py.read_xes(str(path))
    return log if isinstance(log, pd.DataFrame) else pm4py.convert_to_dataframe(log)


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV export with XES column names (as pm4py writes it), keeping only COLUMNS."""
    return pd.read_csv(path, usecols=lambda c: c in COLUMNS, dtype=str)


def load_log(path: str | Path) -> pd.DataFrame:
    """Return the log as a DataFrame with COLUMNS and UTC timestamps.

    Reads .xes / .xes.gz (pm4py), .csv (XES column names) or a .parquet cache. XES and CSV
    logs are cached as parquet next to the file.
    """
    path = Path(path)
    if not path.exists():
        raise LogMappingError(f"event log not found: {path}")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    cache = cache_path(path)
    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        return pd.read_parquet(cache)
    df = _read_csv(path) if path.suffix == ".csv" else _read_xes(path)
    if LIFE not in df.columns:
        df[LIFE] = "complete"
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise LogMappingError(f"{path}: log lacks columns {missing}")
    df = df[COLUMNS].copy()
    try:
        df[TIME] = pd.to_datetime(df[TIME], utc=True, format="ISO8601")
    except ValueError as e:
        raise LogMappingError(f"{path}: {TIME} is not an ISO 8601 timestamp: {e}") from e
    df[CASE] = df[CASE].astype(str)
    df.to_parquet(cache)
    return df


def discover(df: pd.DataFrame) -> pd.DataFrame:
    """Return every (activity, lifecycle) pair with its event count."""
    out = df.groupby([ACT, LIFE]).size().reset_index(name="count")
    return out.sort_values([ACT, LIFE]).reset_index(drop=True)


class Selector(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: str | None = None
    activity_any: list[str] | None = None
    lifecycle: str | None = None
    occurrence: Literal["first", "last"] = "first"

    @model_validator(mode="after")
    def _one(self) -> Selector:
        if (self.activity is None) == (self.activity_any is None):
            raise ValueError("give exactly one of 'activity' and 'activity_any'")
        return self

    @property
    def activities(self) -> list[str]:
        return [self.activity] if self.activity is not None else list(self.activity_any or [])


class TaskMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: Selector
    end: Selector


class LogMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_start: Selector
    case_end: Selector
    tasks: dict[str, TaskMap]

    def selectors(self) -> dict[str, Selector]:
        """Return every selector by its column name in the times table."""
        out = {"case_start": self.case_start, "case_end": self.case_end}
        for t, m in self.tasks.items():
            out[f"{t}:start"], out[f"{t}:end"] = m.start, m.end
        return out


def load_mapping(path: str | Path) -> LogMapping:
    """Return the validated mapping YAML. Raises LogMappingError."""
    try:
        return LogMapping.model_validate(yaml.safe_load(Path(path).read_text()))
    except (ValidationError, yaml.YAMLError, OSError) as e:
        raise LogMappingError(f"{path}: {e}") from e


def check_mapping(mapping: LogMapping, df: pd.DataFrame) -> None:
    """Raise LogMappingError if a mapped activity or lifecycle value is not in the log."""
    pairs = set(zip(df[ACT], df[LIFE], strict=True))
    acts = {a for a, _ in pairs}
    problems = []
    for col, sel in mapping.selectors().items():
        found = [a for a in sel.activities if a in acts]
        if sel.activity_any is not None and found:  # alternatives: one is enough, warn on others
            for a in sorted(set(sel.activities) - set(found)):
                warnings.warn(f"{col}: alternative activity {a!r} is not in the log",
                              stacklevel=2)
        else:
            problems += [f"{col}: activity {a!r} is not in the log"
                         for a in sel.activities if a not in acts]
        if sel.lifecycle is not None:
            problems += [f"{col}: activity {a!r} has no lifecycle {sel.lifecycle!r}"
                         for a in found if (a, sel.lifecycle) not in pairs]
    if problems:
        raise LogMappingError("mapping does not match the log (run discover-log):\n  "
                              + "\n  ".join(problems))


def case_times(df: pd.DataFrame, mapping: LogMapping) -> pd.DataFrame:
    """Return one row per case: a timestamp column per selector (NaT if the event is missing)."""
    check_mapping(mapping, df)
    cols = {}
    for col, sel in mapping.selectors().items():
        rows = df[df[ACT].isin(sel.activities)]
        if sel.lifecycle is not None:
            rows = rows[rows[LIFE] == sel.lifecycle]
        grouped = rows.groupby(CASE)[TIME]
        cols[col] = grouped.min() if sel.occurrence == "first" else grouped.max()
    cases = pd.Index(df[CASE].unique(), name=CASE)
    return pd.DataFrame(cols).reindex(cases)


def split_by_time(
    times: pd.DataFrame, train_share: float = 0.7
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sort cases by case start; return (first 70 %, last 30 %). Drops cases without a start."""
    ordered = times.dropna(subset=["case_start"]).sort_values("case_start", kind="stable")
    k = int(round(len(ordered) * train_share))
    return ordered.iloc[:k], ordered.iloc[k:]


def minutes_between(times: pd.DataFrame, start: str, end: str) -> pd.Series:
    """Return end - start in minutes per case (NaN if either is missing)."""
    return (times[end] - times[start]).dt.total_seconds() / 60.0
