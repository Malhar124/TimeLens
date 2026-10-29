"""Time values: parse to integer minutes, format for reports."""

from __future__ import annotations

import re
from decimal import Decimal

_TIME_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([mhdw]?)\s*$")
_FACTOR = {"": 1, "m": 1, "h": 60, "d": 1440, "w": 10080}


def parse_minutes(value: str | int) -> int:
    """Return `value` ("90m", "1.5h", "2d", "1w", "0" or an int of minutes) as integer minutes.

    Raises ValueError for bad syntax, negative values, or fractions of a minute. O(1).
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"invalid time value {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"negative time value {value!r}")
        return value
    match = _TIME_RE.match(value)
    if match is None:
        raise ValueError(f"invalid time value {value!r}, expected e.g. '90m', '4h', '2d', '1w'")
    minutes = Decimal(match.group(1)) * _FACTOR[match.group(2)]
    if minutes != minutes.to_integral_value():
        raise ValueError(f"time value {value!r} is not a whole number of minutes")
    return int(minutes)


def format_minutes(m: int | float) -> str:
    """Return minutes as "1 d 4 h 30 m" (zero parts omitted, "0 m" for zero, "inf" if infinite)."""
    if m == float("inf"):
        return "inf"
    if m == float("-inf"):
        return "-inf"
    m = int(m)
    if m == 0:
        return "0 m"
    sign, m = ("-", -m) if m < 0 else ("", m)
    days, rest = divmod(m, 1440)
    hours, mins = divmod(rest, 60)
    parts = [f"{v} {u}" for v, u in ((days, "d"), (hours, "h"), (mins, "m")) if v]
    return sign + " ".join(parts)
