"""Shared test set-up."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))


@pytest.fixture(autouse=True)
def update_waits(monkeypatch):
    """Tests see a finished update straight away; test_update_in_background.py checks the real background path."""
    from trust import jobs
    monkeypatch.setattr(jobs, "WAIT", True)
