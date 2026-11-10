"""Risk assessments, phase 1 (owner, 9 Nov 2026): read the CSV, the proposed Elevated rule, a family takes the
highest rating among its groups, groups placed by department, a month with no file carries the newest one forward.
Nothing here changes a score."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust.intake import risk_assessments as ra  # noqa: E402

CSV = (b"Group,Departments,Assessment date,Risk ID,Applicable,Likelihood,Impact,Drivers\n"
       b"Ops A,Payments Ops,03/02/2026,air.cyber.01,,high,Med,RD01 own accounts | RD63 incidents\n"
       b"Ops A,Payments Ops,03/02/2026,air.data.01,No,,,\n"
       b"Ops A,Payments Ops,03/02/2026,air.ops.01,,LOW,CRITICAL,\n"
       b"Ops B,Payments Eng;Payments Ops,,air.cyber.01,yes,LOW,LOW,\n"
       b",x,,air.x,,LOW,LOW,\n"
       b"Ops B,y,,air.ops.01,,banana,LOW,\n")


def test_the_proposed_elevated_rule():
    e = ra.elevated
    assert e("HIGH", "HIGH") and e("CRITICAL", "HIGH") and e("HIGH", "CRITICAL") and e("CRITICAL", "CRITICAL")
    assert not e("HIGH", "MEDIUM") and not e("MEDIUM", "CRITICAL") and not e("LOW", "CRITICAL") and not e(None, "HIGH")


def test_the_csv_is_read_with_rows_set_aside_and_not_applicable_left_out():
    r = ra.read(CSV)
    got = {(x["group"], x["risk_id"]): (x["likelihood"], x["impact"], x["elevated"]) for x in r["rows"]}
    assert got == {("Ops A", "air.cyber.01"): ("HIGH", "MEDIUM", False), ("Ops A", "air.ops.01"): ("LOW", "CRITICAL", False),
                   ("Ops B", "air.cyber.01"): ("LOW", "LOW", False)}
    assert r["summary"]["not_applicable"] == 1 and len(r["set_aside"]) == 2
    a = next(x for x in r["rows"] if x["risk_id"] == "air.cyber.01" and x["group"] == "Ops A")
    assert a["drivers"] == ["RD01 own accounts", "RD63 incidents"] and a["assessed_on"] == "2026-03-02"
    assert next(x for x in r["rows"] if x["group"] == "Ops B")["departments"] == ["Payments Eng", "Payments Ops"]


def test_a_family_takes_the_highest_rating_among_its_groups():
    rows = ra.read(CSV)["rows"]
    got = ra.by_family(rows, {"Ops A": ["payments"], "Ops B": ["payments", "cards"]})
    assert got["payments"]["air.cyber.01"]["group"] == "Ops A"                 # the higher rating wins
    assert got["cards"]["air.cyber.01"]["group"] == "Ops B" and not got["cards"]["air.cyber.01"]["elevated"]


def test_months_without_a_file_carry_the_newest_one_forward(tmp_path, monkeypatch):
    import testdata
    from trust import storage
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "cto.demo"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    testdata.seed_store(["2026-09", "2026-10"], families=4)
    sep = storage.load_month("scored", "2026-09")["period"]["inherent_risk"]
    octo = storage.load_month("scored", "2026-10")["period"]["inherent_risk"]
    assert sep["carried_from"] is None and octo["carried_from"] == "2026-09"
    assert octo["families"] and octo["families"] == sep["families"]
    assert any(not g["families"] for g in octo["groups"])          # the made-up group no department matches


def test_the_made_up_risk_files_for_test_are_complete(monkeypatch):
    """tools/test_risks (TEST only, owner 9 Nov 2026): made-up risk files in the engine's shape. Every risk ID the
    made-up assessments use is there, and every driver a risk names is in the made-up driver_mapping.yaml."""
    import yaml
    import make_test_data
    from trust import config
    folder = pathlib.Path(__file__).resolve().parents[1] / "tools" / "test_risks"
    monkeypatch.setenv("TRUST_RISKS", str(folder))
    risks = config.risks()
    assert len(risks) == 8 and set(make_test_data.RA_RISKS) <= set(risks)
    assert all(r.get("name") and r.get("description") and r.get("domain") for r in risks.values())
    drivers = yaml.safe_load((folder / "driver_mapping.yaml").read_text())["risk_drivers"]
    named = {d for r in risks.values() for d in r["likelihood_drivers"] + r["impact_drivers"]}
    assert named <= set(drivers), sorted(named - set(drivers))
    assert all(v.get("rationale") and "trigger" in v for v in drivers.values())
