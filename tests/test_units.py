import pytest

from timelens.units import format_minutes, parse_minutes


@pytest.mark.parametrize("text,minutes", [
    ("90m", 90), ("1.5h", 90), ("2d", 2880), ("1w", 10080), ("0", 0), (45, 45), (" 4 h ", 240),
])
def test_parse_accepts_valid_values(text, minutes):
    assert parse_minutes(text) == minutes


@pytest.mark.parametrize("bad", ["1.3m", "5x", "-1d", "", "d", -5, 1.5, True])
def test_parse_rejects_invalid_values(bad):
    with pytest.raises(ValueError):
        parse_minutes(bad)


@pytest.mark.parametrize("m,text", [(0, "0 m"), (1710, "1 d 4 h 30 m"), (60, "1 h"),
                                    (-1440, "-1 d"), (10080, "7 d")])
def test_format_minutes(m, text):
    assert format_minutes(m) == text


@pytest.mark.parametrize("m", [0, 1, 59, 61, 1439, 1441, 98765, -3000])
def test_format_round_trips_through_parse(m):
    text = format_minutes(m)
    sign = -1 if text.startswith("-") else 1
    parts = text.lstrip("-").split(" ")
    total = sum(parse_minutes(v + u) for v, u in zip(parts[::2], parts[1::2], strict=True))
    assert sign * total == m
