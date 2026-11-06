"""Date-times are read in whatever format the file uses, including fractions of a second of any length."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust.intake.common import parse_when  # noqa: E402


@pytest.mark.parametrize("text, expect", [
    ("2026-10-01T10:00:00.1234567", "2026-10-01 10:00:00.123456-04:00"),   # TCC last deployment (7 digits)
    ("2026-10-01T10:00:00.123", "2026-10-01 10:00:00.123000-04:00"),
    ("2026-10-01T10:00:00.1", "2026-10-01 10:00:00.100000-04:00"),
    ("2026-10-01T10:00:00.", "2026-10-01 10:00:00-04:00"),                 # bare dot
    ("2026-10-01T10:00:00.1234567Z", "2026-10-01 10:00:00.123456+00:00"),  # Z = UTC
    ("2026-10-01 10:00:00.123", "2026-10-01 10:00:00.123000-04:00"),
    ("10/01/2026 09:00:00.123 AM", "2026-10-01 09:00:00.123000-04:00"),
    ("10/01/2026 09:00:00.1234567 PM", "2026-10-01 21:00:00.123456-04:00"),
    ("10/01/2026 21:00:00.5", "2026-10-01 21:00:00.500000-04:00"),
    ("10/01/2026 02:15:00 PM", "2026-10-01 14:15:00-04:00"),
    ("2026-10-01T10:00:00Z", "2026-10-01 10:00:00+00:00"),                # postmortem style
    ("1/5/2026", "2026-01-05 00:00:00-05:00"),                            # actions style, winter time
])
def test_formats(text, expect):
    assert str(parse_when(text)) == expect


@pytest.mark.parametrize("text", ["", "soon", "N/A", None])
def test_not_a_date_is_none(text):
    assert parse_when(text) is None


def test_every_reader_uses_the_shared_date_reader():
    """No reader may parse dates on its own: all dates go through common.parse_when,
    so every input file gets the same handling (any format, fractions, New York default)."""
    intake = pathlib.Path(__file__).resolve().parents[1] / "backend" / "trust" / "intake"
    found = []
    for f in intake.glob("*.py"):
        if f.name == "common.py":
            continue
        text = f.read_text()
        for banned in ("strptime", "fromisoformat", "dateutil", "pd.to_datetime", "import datetime", "from datetime"):
            if banned in text:
                found.append(f"{f.name}: {banned}")
    assert found == [], "parse dates with common.parse_when instead: " + "; ".join(found)
