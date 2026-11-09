"""Score and publish: counts per family, statuses, blocks/TRUST through scoring.py, and the front-end data."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import __main__ as cli, mapping, publish, score_month, store  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"
ALL = (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("tcc", "tcc_export.csv"),
       ("ntcc", "ntcc_export.csv"), ("actions", "actions_export.csv"), ("postmortems", "postmortems_export.csv"),
       ("cx_sast", "final_checkmarx_sast_report.json"), ("cx_sca", "final_checkmarx_sca_report 1.json"),
       ("app_inventory", "app_inventory.csv"))          # UN-01's denominator (owner, 9 Nov 2026)


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    return tmp_path


def load(month, feeds=ALL):
    for feed, name in feeds:
        store.upload(feed, month, (FIX / name).read_bytes(), name, "Tester")
    mapping.map_month(month)
    return score_month.run(month)


def test_counts_statuses_and_scores(tmp_store):
    p = load("2026-09")["period"]
    pay = p["families"]["payments"]["metrics"]
    # TE-01 (owner, 8 Nov 2026): deployed changes through TCC / all deployed changes, TCC + Non-TCC, by created date
    assert (pay["TE-01"]["numerator"], pay["TE-01"]["denominator"]) == (2, 3)
    # prevailing median: only 2 families have a result here and 5 are needed, so no tolerance threshold yet
    assert pay["TE-01"]["status"] == "N/A" and "No tolerance threshold yet" in pay["TE-01"]["reason"]
    # Automatic Red rules are off (owner, 9 Nov 2026): client impact no longer forces Red; too few families for a median
    assert pay["TE-02"]["status"] == "N/A" and not pay["TE-02"]["override"]
    # Nothing open is not scored (owner, 9 Nov 2026; was Green under D-100); 1-2 items = Low confidence, not scored
    assert p["families"]["lending"]["metrics"]["UN-02"]["status"] == "N/A"
    assert "No postmortem actions open" in p["families"]["lending"]["metrics"]["UN-02"]["reason"]
    assert pay["UN-02"]["status"] == "Low confidence"
    # Checkmarx: repos reach a family only through a matching GitHub repo (none loaded here), so not scored; firm still counts
    assert pay["SE-01"]["status"] == "N/A" and "matching GitHub repo" in pay["SE-01"]["reason"]
    assert p["firm_totals"]["SE-01"] == 66.7 and p["unattributed_pct"]["Cyber"] == 100.0
    # Feeds not received are No data and left out
    assert pay["TR-01"]["status"] == "DNR" and "Arch" in p["dnr"]
    # Neither TE metric is scored here, so Releases has no score and Payments has no TRUST score
    assert p["families"]["payments"]["blocks"]["REL"]["score"] is None and p["families"]["payments"]["trust"] is None
    assert p["coverage"] == {"block_min_share": 0, "trust_min_blocks": 1}
    # Firm TRUST is scored from the pooled firm-wide results, not averaged from the families (owner, 4 Nov 2026):
    # No tolerance threshold for either TE metric yet, and no automatic Red rule, so the firm has no TRUST score
    assert p["firm"]["TE-01"]["status"] == "N/A" and p["firm"]["TE-02"]["status"] == "N/A" and not p["firm"]["TE-02"].get("override")
    assert p["firm_blocks"]["REL"]["score"] is None and p["firm_trust"] is None
    # A result's 'provisional' means "carried over" in the front end; never set here
    assert not any(r["provisional"] for f in p["families"].values() for r in f["metrics"].values())
    # Mapping notes reach the Data sources page as {rule, detail}, each rule unique within its file
    for s in p["submissions"]:
        assert all(set(w) == {"rule", "detail"} for w in s["warnings"])
        assert len({w["rule"] for w in s["warnings"]}) == len(s["warnings"])


def test_a_month_with_only_checkmarx_still_scores(tmp_store):
    p = load("2026-10", (("cx_sca", "final_checkmarx_sca_report 1.json"),))["period"]
    assert p["families"] == {}                                   # no owners file: no families yet
    assert p["firm_totals"]["SE-02"] == 66.7 and p["firm"]["SE-02"]["denominator"] == 3


def test_publish_builds_front_end_data(tmp_store):
    load("2026-09")
    out = publish.run()
    d = json.loads((out / "data.json").read_text())
    assert list(d["periods"]) == ["2026-09"] and {f["id"] for f in d["families"]} >= {"payments", "cards"}
    assert d["entries"] == [] and d["connectors"] == []          # nothing synthetic carried over
    assert d["env_label"] == "Live data"
    assert all(f["tier01"] is None for f in d["families"])       # unknown until the app inventory arrives
    html = (out / "index.html").read_text()
    assert '"env_label": "Live data"' in html and (out / "evidence.json").exists()


def test_second_month_gets_prior_values_and_watch_list(tmp_store):
    load("2026-09")
    raw = (FIX / "tcc_export.csv").read_bytes().replace(b"09/28/2026", b"10/28/2026")
    store.upload("tcc", "2026-10", raw, "tcc_export.csv", "Tester")
    for feed, name in ALL:
        if feed != "tcc":
            store.upload(feed, "2026-10", (FIX / name).read_bytes(), name, "Tester")
    mapping.map_month("2026-10")
    score_month.run("2026-10")
    d = publish.build()
    te02 = d["periods"]["2026-10"]["families"]["payments"]["metrics"]["TE-02"]
    assert te02["prior_status"] == "N/A" and te02["history"] == ["N/A", te02["status"]]
    assert d["trend"]["months"] == ["2026-09", "2026-10"]


def test_command_line_score_and_publish(tmp_store, capsys):
    for feed, name in ALL:
        assert cli.main(["upload", feed, str(FIX / name), "--month", "2026-09", "--by", "Tester"]) == 0
    assert cli.main(["map", "2026-09"]) == 0
    assert cli.main(["score", "2026-09"]) == 0
    assert cli.main(["publish"]) == 0
    assert "index.html" in capsys.readouterr().out


def test_un01_unique_incidents_and_un03_coming_soon(tmp_store):
    """Owner, 2 Nov 2026: no incidents file, so UN-01 = unique Critical and SWE incident_ids in the
    postmortem file. UN-03 is client incidents, with no source yet: Coming soon, left out of every score."""
    p = load("2026-09")["period"]
    fam = p["families"]
    # INC-A (DEFCON 3, critical) has actions in Payments and Cards: once in each, once firm-wide.
    # INC-B is DEFCON 0 (out); INC-C is DEFCON Not Available (neither Critical nor SWE: listed, not counted);
    # INC-D has no end date (listed).
    assert fam["payments"]["metrics"]["UN-01"]["numerator"] == 1
    assert fam["cards"]["metrics"]["UN-01"]["numerator"] == 1
    assert p["firm"]["UN-01"]["numerator"] == 1
    assert any("INC-D" in n for n in p.get("notes", []))
    assert any("INC-C" in n and "neither Critical nor SWE" in n for n in p.get("notes", []))
    # Owner, 9 Nov 2026: per 10 confirmed apps in the app inventory (Payments 5 apps, Cards 2), against the prevailing
    # median; only with at least 5 families, so no threshold in this 4-family month and not scored (rate still shown)
    assert (fam["payments"]["metrics"]["UN-01"]["denominator"], fam["payments"]["metrics"]["UN-01"]["value"]) == (5, 2.0)
    assert fam["cards"]["metrics"]["UN-01"]["value"] == 5.0
    assert "UN-01" not in p["thresholds"]
    assert fam["payments"]["metrics"]["UN-01"]["status"] == "N/A" and "5 are needed" in fam["payments"]["metrics"]["UN-01"]["reason"]
    # A family with no confirmed apps has no rate
    assert fam["lending"]["metrics"]["UN-01"]["value"] is None and "No confirmed apps" in fam["lending"]["metrics"]["UN-01"]["reason"]
    assert (p["firm"]["UN-01"]["numerator"], p["firm"]["UN-01"]["denominator"], p["firm"]["UN-01"]["value"]) == (1, 7, 1.4)
    # UN-03: Coming soon everywhere; not counted as missing data and not in the block
    assert fam["payments"]["metrics"]["UN-03"]["status"] == "Coming soon"
    assert p["firm"]["UN-03"]["status"] == "Coming soon"
    assert fam["payments"]["blocks"]["STA"]["applicable"] == 2   # UN-01 and UN-02; UN-03 is left out
    assert fam["payments"]["blocks"]["STA"]["missing"] == 0
    d = publish.build()
    ms = {m["id"]: m for m in d["metrics"]}
    assert ms["UN-01"]["unit"] == "per 10 apps" and ms["UN-03"].get("coming_soon") is True


def test_un01_with_only_the_postmortem_file(tmp_store):
    feeds = (("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"), ("postmortems", "postmortems_export.csv"))
    p = load("2026-09", feeds)["period"]
    # UN-01 needs the app inventory too (its denominator, owner 9 Nov 2026), so without it: No data
    assert p["families"]["cards"]["metrics"]["UN-01"]["status"] == "DNR" and p["firm"]["UN-01"]["status"] == "DNR"
    assert p["families"]["cards"]["metrics"]["UN-02"]["status"] == "DNR"     # no action file


def test_te02_release_counts_when_its_7_day_window_ends(tmp_store):
    """A release on 28 Sep has its 7-day window end on 5 Oct, so it counts in October's TE-02."""
    raw = (FIX / "tcc_export.csv").read_bytes().replace(b"2026-09-15 10:00:00", b"2026-09-28 10:00:00")
    for m in ("2026-09", "2026-10"):
        store.upload("tcc", m, raw, "tcc_export.csv", "Tester")
        for feed, name in ALL:
            if feed != "tcc":
                store.upload(feed, m, (FIX / name).read_bytes(), name, "Tester")
        mapping.map_month(m)
    sep = score_month.run("2026-09")["period"]["families"]["payments"]["metrics"]["TE-02"]
    octo = score_month.run("2026-10")["period"]["families"]["payments"]["metrics"]["TE-02"]
    assert sep["status"] == "N/A"                       # nothing whose window closed in September
    assert octo["denominator"] >= 1                     # 1004 now counts in October


def test_unrated_incidents_are_shown_but_not_scored(tmp_store):
    """Owner, 2 Nov 2026: incidents with no rating (DEFCON Not Available or blank) are never hidden,
    but stay out of the score: not in UN-01's count, and their actions not in UN-02's rate."""
    raw = (FIX / "postmortems_export.csv").read_bytes().replace(b",Critical/SWE,3,critical,", b",Critical/SWE,Not Available,,")
    for feed, name in ALL:
        data = raw if feed == "postmortems" else (FIX / name).read_bytes()
        store.upload(feed, "2026-09", data, name, "Tester")
    mapping.map_month("2026-09")
    p = score_month.run("2026-09")["period"]
    pay = p["families"]["payments"]["metrics"]
    # INC-A is now unrated: not counted in UN-01, but shown
    assert pay["UN-01"]["numerator"] == 0 and pay["UN-01"]["unrated"] == 1
    assert "no rating" in pay["UN-01"]["reason"]
    # Its open actions are out of UN-02's rate, counted separately and named in the reason
    assert pay["UN-02"].get("unrated_open", 0) >= 1
    assert "Not in the score" in pay["UN-02"]["reason"]
    assert (pay["UN-02"]["denominator"] or 0) == 0


def test_thresholds_need_five_families(tmp_store):
    """Owner, 3 Nov 2026: no static starting values; the prevailing median comes from the month's own data.
    Owner, 4 Nov 2026: and needs at least 5 family results (setting min_families_for_threshold)."""
    from trust import score_month
    cfg = score_month.thresholds_config()
    assert score_month.thresholds_for("TE-02", [10.0, 30.0, 20.0, 25.0], False, cfg) is None   # 4 families: none
    t = score_month.thresholds_for("TE-02", [10.0, 30.0, 20.0, 25.0, 15.0], False, cfg)
    assert t["basis"] == "Calibrated" and t["green"] == 20.0                               # 5 families: median
    assert "5 are needed" in score_month.no_threshold_reason(4, cfg)
    assert score_month.thresholds_for("TE-02", [10.0, 30.0], False, dict(cfg, min_families_for_threshold=2))["green"] == 20.0
    assert score_month.thresholds_for("TE-02", [], False, cfg) is None                    # nothing to calculate from
    assert score_month.thresholds_for("RE-02", [], True, cfg)["basis"] == "Policy"         # policy metrics unchanged


def test_subteams_come_from_the_hr_column_in_settings(tmp_store):
    """Owner, 3 Nov 2026: sub-teams on family pages use Department by default; configurable."""
    from trust import storage
    load("2026-09")
    items = storage.load_month("scored", "2026-09")["items"]["payments"]["TE-01"]
    assert {i["team"] for i in items} == {"Tech"}                                  # the Department column
    (tmp_store / "s.json").write_text('{"hr_root_sam_account": "dcto", "subteam_hr_column": "Supervisory Organization"}')
    mapping.map_month("2026-09")
    score_month.run("2026-09")
    items = storage.load_month("scored", "2026-09")["items"]["payments"]["TE-01"]
    assert all("(" in i["team"] for i in items)                                    # e.g. "Platform (Alex Moreno)"


def test_coverage_setting_can_go_back_to_the_original_rules(tmp_store, monkeypatch):
    """coverage = 0.5 / 3 (the original rules): one block is not enough for a TRUST score."""
    import json
    cfg = json.loads((pathlib.Path(__file__).resolve().parents[1] / "config" / "thresholds.json").read_text())
    cfg["coverage"] = {"block_min_share": 0.5, "trust_min_blocks": 3}
    cfg["automatic_red_rules"] = True                                       # so Releases has a score to test with
    (tmp_store / "t.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("TRUST_THRESHOLDS", str(tmp_store / "t.json"))
    p = load("2026-09")["period"]
    assert p["families"]["payments"]["trust"] is None and p["families"]["payments"]["status"] == "Insufficient data"
    assert p["families"]["payments"]["blocks"]["REL"]["score"] == 0        # the block itself still scores


def test_automatic_red_rules_can_be_switched_back_on(tmp_store, monkeypatch):
    """Setting automatic_red_rules (owner, 9 Nov 2026: off for now). On: client impact makes TE-02 Red, caps
    Releases at 49 (here 0, its only metric) and holds for the firm."""
    import json
    cfg = json.loads((pathlib.Path(__file__).resolve().parents[1] / "config" / "thresholds.json").read_text())
    cfg["automatic_red_rules"] = True
    (tmp_store / "t.json").write_text(json.dumps(cfg))
    monkeypatch.setenv("TRUST_THRESHOLDS", str(tmp_store / "t.json"))
    p = load("2026-09")["period"]
    pay = p["families"]["payments"]["metrics"]["TE-02"]
    assert pay["status"] == "Red" and pay["override"] and "client impact" in pay["reason"]
    assert p["families"]["payments"]["blocks"]["REL"]["score"] == 0
    assert p["firm"]["TE-02"]["status"] == "Red" and p["firm"]["TE-02"]["override"]


def test_un01_no_incidents_is_shown_not_scored(tmp_store):
    """Owner, 9 Nov 2026: a family with confirmed apps but no Critical or SWE incident shows 0, not scored."""
    raw = (FIX / "postmortems_export.csv").read_bytes().replace(b",Critical/SWE,3,critical,", b",Critical/SWE,0,critical,")
    for feed, name in ALL:
        store.upload(feed, "2026-09", raw if feed == "postmortems" else (FIX / name).read_bytes(), name, "Tester")
    mapping.map_month("2026-09")
    pay = score_month.run("2026-09")["period"]["families"]["payments"]["metrics"]["UN-01"]
    assert (pay["value"], pay["status"], pay["points"]) == (0.0, "Low confidence", None)
    assert "No Critical or SWE incidents" in pay["reason"]
