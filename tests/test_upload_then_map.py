"""Upload (step 1) and mapping (step 2) are separate: upload keeps the file; mapping can be re-run any time."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import mapping, store  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    s = tmp_path / "settings.json"
    s.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(s))
    return tmp_path


def up(feed, name):
    return store.upload(feed, "2026-10", (FIX / name).read_bytes(), name, "Tester")


def test_sca_alone_uploads_and_maps():
    up("cx_sca", "final_checkmarx_sca_report 1.json")
    r = mapping.map_month("2026-10")
    assert r["received"] == ["cx_sca"]
    assert r["feeds"]["cx_sca"]["summary"]["repos"] == 3
    assert r["feeds"]["cx_sca"]["as_of_source"] == "upload date"


def test_junk_is_refused_at_upload_and_not_stored():
    """Owner, 3 Nov 2026: check files at upload so we aren't getting junk."""
    with pytest.raises(ValueError, match="Not uploaded. None of the columns TRUST uses"):
        store.upload("tcc", "2026-10", b"this is not a TCC export at all", "junk.csv", "Tester")
    with pytest.raises(ValueError, match="doesn't look like a TCC changes file"):
        store.upload("tcc", "2026-10", b"Ticket ID,Colour\n", "wrong.csv", "Tester")
    with pytest.raises(ValueError, match="rows could be used"):
        lines = (FIX / "tcc_export.csv").read_bytes().split(b"\n")
        no_keys = b"\n".join([lines[0]] + [b"," + l.split(b",", 1)[1] for l in lines[1:] if b"," in l])  # Ticket ID blank
        store.upload("tcc", "2026-10", no_keys, "keys-blank.csv", "Tester")
    with pytest.raises(ValueError, match="no list of repos"):
        store.upload("cx_sast", "2026-10", b'{"nope": 1}', "x.json", "Tester")
    assert mapping.map_month("2026-10")["received"] == []                     # nothing was stored
    from trust import storage
    ups = [e for e in storage.events("2026-10") if e["action"] == "upload"]
    assert [e["note"] for e in ups][:2] == ["cx_sast: x.json refused", "tcc: keys-blank.csv refused"]
    assert all(e["detail"]["refused"] for e in ups)                              # each refusal is in the record


def test_a_real_file_with_no_rows_is_kept_with_a_warning():
    header = (FIX / "tcc_export.csv").read_bytes().split(b"\n")[0] + b"\n"
    e = store.upload("tcc", "2026-10", header, "empty-month.csv", "Tester")
    assert e["file"] and e["checks"]["rows"] == 0 and "no rows" in e["checks"]["warnings"][0]


def test_warnings_from_the_checks_are_kept_with_the_upload():
    e = up("tcc", "tcc_export.csv")
    assert e["checks"]["rows"] > 0 and any("isn't a date" in w for w in e["checks"]["warnings"])


def test_same_file_twice_is_a_no_op_and_a_new_one_replaces():
    up("cx_sast", "final_checkmarx_sast_report.json")
    assert "already received" in up("cx_sast", "final_checkmarx_sast_report.json")["note"]
    e = store.upload("cx_sast", "2026-10", b'{"data": []}', "new.json", "Tester")
    assert e["replaces"] and "replaces" in e["note"]
    assert mapping.map_month("2026-10")["feeds"]["cx_sast"]["summary"]["repos"] == 0   # newest is used


def test_only_the_columns_trust_uses_are_kept(tmp_store):
    """Owner, 2 Nov 2026: unused columns (e.g. the free-text Title) are dropped at upload."""
    e = up("tcc", "tcc_export.csv")
    stored = (tmp_store / "store" / "uploads" / "2026-10" / "tcc" / e["file"]).read_text()
    assert "Title" in e["kept"]["columns_dropped"] and "Title" not in stored.splitlines()[0]
    assert e["original_sha256"] != e["sha256"]
    assert mapping.map_month("2026-10")["feeds"]["tcc"]["summary"]["tickets"] > 0


def test_fixing_a_column_name_then_uploading_again(tmp_store, monkeypatch):
    raw = (FIX / "tcc_export.csv").read_bytes().replace(b"Ticket ID", b"Change Number", 1)
    with pytest.raises(ValueError, match="rows could be used"):                # no key column: every row unusable
        store.upload("tcc", "2026-10", raw, "tcc.csv", "Tester")
    maps = tmp_store / "maps.json"
    maps.write_text('{"tcc": {"Ticket ID": ["Change Number"]}}')
    monkeypatch.setenv("TRUST_COLUMN_MAPS", str(maps))
    e = store.upload("tcc", "2026-10", raw, "tcc.csv", "Tester")             # same file, new column map: accepted
    assert "already received" not in e["note"]
    assert mapping.map_month("2026-10")["feeds"]["tcc"]["summary"]["tickets"] > 0


def test_hr_keeps_only_the_ctos_line_and_the_columns_trust_uses(tmp_store):
    """Owner, 2 Nov 2026: the firm-wide HR file is cut down at upload; the rest of the firm is never stored.
    Owner, 3 Nov 2026: Country is kept for now (technology only) for the EU regulatory impact assessment."""
    lines = (FIX / "hr_firmwide.csv").read_text().splitlines()
    raw = "\n".join([lines[0] + ",Time Type"] + [l + ",Full time" for l in lines[1:]]) + "\n"   # a column TRUST doesn't use
    e = store.upload("hr", "2026-10", raw.encode(), "hr.csv", "Tester")
    assert e["kept"]["people_kept"] == 4 and e["kept"]["rows_in_file"] > 4
    stored = (tmp_store / "store" / "uploads" / "2026-10" / "hr" / e["file"]).read_text()
    assert len(stored.splitlines()) == 1 + 4                                   # header + the CTO's line only
    assert "chris.exec@example.com" not in stored                              # the CEO, above the CTO: his row is never stored
    header = stored.splitlines()[0]
    assert "Time Type" not in header                                           # unused column dropped
    assert "Location Address - Country" in header and "Department" in header   # kept (owner, 3 Nov 2026)
    assert e["original_sha256"] != e["sha256"]                                 # the file as received isn't kept
    people = mapping.map_month("2026-10")["feeds"]["hr"]["people"]
    assert len(people) == 4 and all(p.get("country") for p in people)


def test_hr_before_the_cto_setting_keeps_nothing(tmp_store):
    (tmp_store / "settings.json").write_text('{"hr_root_sam_account": ""}')
    with pytest.raises(ValueError, match="isn't set in config/settings.json"):
        up("hr", "hr_firmwide.csv")
    (tmp_store / "settings.json").write_text('{"hr_root_sam_account": "nobody"}')
    with pytest.raises(ValueError, match="'nobody': check it is right"):
        up("hr", "hr_firmwide.csv")
    (tmp_store / "settings.json").write_text('{"hr_root_sam_account": "DCTO"}')
    e = up("hr", "hr_firmwide.csv")                                            # upload again after setting it
    assert e["kept"]["people_kept"] == 4
    assert mapping.map_month("2026-10")["feeds"]["hr"]["summary"]["kept"] == 4


def test_actions_and_postmortems_link_when_both_are_there():
    up("actions", "actions_export.csv")
    up("postmortems", "postmortems_export.csv")
    a = mapping.map_month("2026-10")["feeds"]["actions"]
    assert a["incidents"]["INC-A"]["in_postmortem_file"]
    assert {x["item_ref"]: x["scope_reason"] for x in a["rows"]}["RPD:123"] == "incident is DEFCON 0"


def test_empty_file_is_refused():
    with pytest.raises(ValueError, match="empty"):
        store.upload("tcc", "2026-10", b"", "x.csv", "Tester")


def test_mapped_result_is_saved_for_scoring(tmp_store):
    up("cx_sca", "final_checkmarx_sca_report 1.json")
    mapping.map_month("2026-10")
    saved = json.loads((tmp_store / "store" / "mapped" / "2026-10.json").read_text())
    assert saved["feeds"]["cx_sca"]["status"] == "mapped"


def test_hr_plus_owners_places_actions_and_incidents():
    up("actions", "actions_export.csv")                  # any order
    up("postmortems", "postmortems_export.csv")
    r = mapping.map_month("2026-10")
    assert {a["family_id"] for a in r["feeds"]["actions"]["rows"]} == {"UNATTRIBUTED"}   # no HR yet
    up("hr", "hr_firmwide.csv")
    up("hr_mapping", "family_owners.csv")
    r = mapping.map_month("2026-10")                     # map again; nothing re-uploaded
    fam = {a["item_ref"]: a["family_id"] for a in r["feeds"]["actions"]["rows"]}
    assert fam["JIRA:A-1"] == "payments" and fam["GITHUB:org/r/issues/5"] == "cards"
    assert r["feeds"]["actions"]["incidents"]["INC-A"]["families"] == ["cards", "payments"]
    people = {p["sam_account"]: p["family_id"] for p in r["feeds"]["hr"]["people"]}
    assert people["dcto"] == "cloud-platform"


@pytest.mark.parametrize("feed,name", [("hr", "hr_firmwide.csv"), ("hr_mapping", "family_owners.csv"),
                                       ("tcc", "tcc_export.csv"), ("ntcc", "ntcc_export.csv"),
                                       ("actions", "actions_export.csv"), ("postmortems", "postmortems_export.csv"),
                                       ("cx_sast", "final_checkmarx_sast_report.json"),
                                       ("cx_sca", "final_checkmarx_sca_report 1.json")])
def test_each_source_is_checked_on_its_own(feed, name):
    """Owner, 3 Nov 2026: the checks run independently for each data source, with no other file loaded."""
    e = up(feed, name)
    assert e["checks"]["rows"] > 0
    assert mapping.map_month("2026-10")["received"] == [feed]                  # nothing else was there


def test_checkmarx_that_is_not_json_is_refused():
    with pytest.raises(ValueError, match="isn't valid JSON"):
        store.upload("cx_sca", "2026-10", b"repo,passed\nx,1\n", "sca.csv", "Tester")
