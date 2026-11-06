"""Live-site details: who ran the newest calculation, and the firm tolerance setting (owner, 3 Nov 2026)."""
from trust import publish, score_month, storage


def test_run_info_records_who_and_with_what(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    assert storage.run_info("scored", "2026-09") is None
    storage.save_month("scored", "2026-09", {"x": 1}, by="R. Patel")
    run = storage.run_info("scored", "2026-09")
    assert run["by"] == "R. Patel" and run["at"] and len(run["settings_sha256"]) == 64
    # the run record must not look like another month to the month list
    assert storage.months("scored") == ["2026-09"]


def test_firm_tolerance_hidden_until_set(monkeypatch):
    monkeypatch.setattr(score_month, "thresholds_config", lambda: {"firm_tolerance": None})
    assert publish._firm_tolerance() is None
    monkeypatch.setattr(score_month, "thresholds_config", lambda: {"firm_tolerance": 85})
    assert publish._firm_tolerance() == {"value": 85}
    monkeypatch.setattr(score_month, "thresholds_config", lambda: {})
    assert publish._firm_tolerance() is None


def test_caps_are_settings():
    from trust import scoring
    red = {"status": "Red", "override": True}
    green = {"status": "Green"}
    ms = [("TE-01", green), ("TE-02", red), ("TE-03", green), ("TE-04", green)]   # average 75
    assert scoring.block(ms, {})[0]["score"] == 49                                # default automatic Red cap
    assert scoring.block(ms, {}, {"automatic_red_block": 39})[0]["score"] == 39
    plain = [("TE-01", green), ("TE-02", {"status": "Red"}), *[(f"X{i}", green) for i in range(8)]]   # average 90
    assert scoring.block(plain, {})[0]["score"] == 79
    assert scoring.block(plain, {}, {"red_metric_block": 69})[0]["score"] == 69
    # nonsense values are ignored, so a typo can't break scoring
    assert scoring.caps_from({"automatic_red_block": "abc", "red_metric_block": 150, "x": 1}) == scoring.CAPS


def test_percentage_limits_stay_between_0_and_100():
    cfg = {"amber_band_min_points": 5, "amber_band_spread_multiple": 1.5, "metrics": {"TE-02": {"basis": "Prevailing median"}, "SE-01": {"basis": "Prevailing median"}}}
    assert score_month.thresholds_for("TE-02", [100.0] * 5, False, cfg)["red"] == 100.0     # not 105%
    assert score_month.thresholds_for("SE-01", [2.0] * 5, True, cfg)["red"] == 0.0          # not -3%
