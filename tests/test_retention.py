"""Retention (D-86, owner 5 Nov 2026): months older than the kept window are removed whole, locked or not;
a dry run removes nothing; the page is published again afterwards. Old-run pruning needs the database
(tests/test_database.py covers it)."""
import datetime
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import lock, retention, storage  # noqa: E402
from testdata import seed_store  # noqa: E402


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "cto.demo"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    seed_store(["2026-08", "2026-09", "2026-10"], families=5)
    return tmp_path / "store"


def test_first_kept_month_counts_the_current_month():
    assert retention.first_kept_month(datetime.date(2026, 11, 5)) == "2024-12"
    assert retention.first_kept_month(datetime.date(2026, 11, 5), keep_months=1) == "2026-11"
    assert retention.first_kept_month(datetime.date(2027, 1, 31), keep_months=2) == "2026-12"


def test_dry_run_lists_but_removes_nothing(seeded):
    today = datetime.date(2026, 10, 15)
    p = retention.run(write=False, today=today, keep_months=2, out=lambda *_: None)
    assert [m["month"] for m in p["months"]] == ["2026-08"]
    assert p["months"][0]["submission"] == 14 and p["months"][0]["kept_bytes"] > 0
    assert storage.months("scored") == ["2026-08", "2026-09", "2026-10"]
    assert (seeded / "uploads" / "2026-08").exists()


def test_write_removes_expired_months_locked_too_and_republishes(seeded):
    lock.acknowledge("2026-08", [w["key"] for w in lock.warnings("2026-08")], "Tech Risk")
    lock.lock("2026-08", "Tech Risk")
    today = datetime.date(2026, 10, 15)
    p = retention.run(write=True, by="Scheduler", today=today, keep_months=2, out=lambda *_: None)
    assert [m["month"] for m in p["months"]] == ["2026-08"] and p["months"][0]["locked"] is True
    assert storage.months("scored") == ["2026-09", "2026-10"]
    assert storage.upload_months() == ["2026-09", "2026-10"]
    assert not (seeded / "uploads" / "2026-08").exists()
    assert storage.month_status("2026-08")["status"] == "open"          # the lock record went with the month
    assert all(e["month"] != "2026-08" for e in storage.events(limit=10000))
    data = json.loads((seeded / "published" / "data.json").read_text())
    assert list(data["periods"]) == ["2026-09", "2026-10"]
    last = [e for e in storage.events(limit=10000) if e["action"] == "retention"]
    assert len(last) == 1 and last[0]["detail"]["months"][0]["month"] == "2026-08"


def test_nothing_expired_changes_nothing(seeded):
    p = retention.run(write=True, today=datetime.date(2026, 10, 15), keep_months=24, out=lambda *_: None)
    assert p["months"] == [] and p["runs"] == []
    assert storage.months("scored") == ["2026-08", "2026-09", "2026-10"]
    assert not [e for e in storage.events(limit=10000) if e["action"] == "retention"]


def test_a_locked_month_is_frozen_as_shown_at_the_lock(seeded, monkeypatch):
    """Owner, 5 Nov 2026: locked months need to be LOCKED. Re-scoring September must not move what
    locked October shows (its change arrows and prior values came from September at the lock)."""
    import json as _json
    from trust import publish, score_month
    lock.acknowledge("2026-10", [w["key"] for w in lock.warnings("2026-10")], "Tech Risk")
    lock.lock("2026-10", "Tech Risk")
    before = _json.loads((seeded / "published" / "data.json").read_text())["periods"]["2026-10"]
    fam = next(iter(before["families"]))
    assert before["families"][fam].get("delta") is not None           # October had a change vs September
    # September is re-scored with a different threshold rule, which would change its scores and so
    # October's arrows if they were worked out again.
    monkeypatch.setattr(score_month, "min_families", lambda cfg: 99)   # no thresholds at all: everything N/A
    score_month.run("2026-09")
    publish.run()
    after = _json.loads((seeded / "published" / "data.json").read_text())["periods"]
    assert after["2026-09"]["families"][fam]["trust"] != before["families"][fam]["trust"] or \
        after["2026-09"]["families"][fam]["trust"] is None              # September really did move
    for k in ("families", "watch_list", "firm", "firm_trust", "firm_trust_delta", "firm_blocks"):
        assert after["2026-10"].get(k) == before.get(k), k
    assert after["2026-10"]["meta"]["status"] == "Locked" and "shown" not in after["2026-10"]["seal"]
    assert after["2026-10"]["seal"]["shown_sha256"]
    # Reopened, it follows the live data again.
    lock.reopen("2026-10", "Tech Risk", "test")
    live = _json.loads((seeded / "published" / "data.json").read_text())["periods"]["2026-10"]
    assert live["families"][fam].get("delta") != before["families"][fam].get("delta")


def test_informational_notes_never_block_the_lock(seeded):
    """Owner, 5 Nov 2026: notes that report nothing wrong are shown for information and need no acknowledgement."""
    allw = lock.warnings("2026-10", include_info=True)
    info = [w for w in allw if w["info"]]
    assert {w["feed"] for w in info} >= {"cx_sast", "cx_sca", "hr_mapping", "ntcc"}
    assert all(not w["info"] for w in lock.warnings("2026-10"))
    lock.acknowledge("2026-10", [w["key"] for w in lock.warnings("2026-10")], "Tech Risk")
    assert lock.lock("2026-10", "Tech Risk")["status"] == "locked"          # the info notes didn't stop it
    period = storage.load_month("scored", "2026-10")["period"]
    assert period["files_needed"]["missing"] == [] and "tcc" in period["files_needed"]["needed"]
    assert "ntcc" in period["files_needed"]["optional_received"]
