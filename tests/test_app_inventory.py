"""App inventory and AD owner groups (owner, 6 Nov 2026): read, placed with families, linked to ITDR, GitHub
repos and owners, and shown in the drill-down. Nothing here is scored."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import evidence, lock, mapping, store  # noqa: E402
from trust.intake import app_inventory, app_links, owner_groups  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"

HEADER = ("app_id,app_name,app_status,app_department,app_sbu,app_org_hierarchy,app_owner_raw,app_owner_type,"
          "app_owner_email,bcp_tier,bcp_tier_source,itdr_match,service_id,service_name,service_owner_email,"
          "service_repo,unmapped_reasons\n")


def inventory(*rows):
    return (HEADER + "".join(r + "\n" for r in rows)).encode()


INV = inventory(
    "A1,Payments Gateway,Confirmed,Pay,SBU1,Tech > Payments Eng > Gateway,x,DL,pay-dl@example.com,1,src,9,S1,api,,org/pay-api,none",
    "A1,Payments Gateway,Confirmed,Pay,SBU1,Tech > Payments Eng > Gateway,x,DL,pay-dl@example.com,1,src,9,S2,ui,,org/pay-ui,none",
    "A2,Card Ledger,confirmed,Cards,SBU1,Tech > Unknown Org > X,x,Person,pat.kim@example.com,2,src,,S3,ledger,,cards-ledgr,",
    "A3,Old Thing,Retired,Pay,SBU1,Tech > Payments Eng > Gateway,x,Person,pat.kim@example.com,,,,S4,old,,,",
    ",No Id,Confirmed,,,,,,,,,,,,,,")

PEOPLE = [
    dict(sam_account="amoreno", email="alex.moreno@example.com", worker="Alex Moreno", sup_org="Payments Eng (Alex Moreno)", family_id="payments"),
    dict(sam_account="pkim", email="pat.kim@example.com", worker="Pat Kim", sup_org="Payments Eng (Sam Lee)", family_id="payments"),
    dict(sam_account="jray", email="jo.ray@example.com", worker="Jo Ray", sup_org="Card Platform (Jo Ray)", family_id="cards"),
]
AD = [dict(owner_email="pay-dl@example.com", owner_kind="group", group_sam="PAY-DL", member_sam="jray",
           member_email="jo.ray@example.com", member_name="Jo Ray", included=True, reason=None),
      dict(owner_email="pay-dl@example.com", owner_kind="group", group_sam="PAY-DL", member_sam="svc_x",
           member_email=None, member_name="svc", included=False, reason="service account")]


def test_reader_groups_service_rows_and_counts_only_confirmed_apps():
    r = app_inventory.read(INV)
    apps = {a["app_id"]: a for a in r["rows"]}
    assert set(apps) == {"A1", "A2", "A3"}
    assert [s["service_repo"] for s in apps["A1"]["services"]] == ["org/pay-api", "org/pay-ui"]
    assert apps["A1"]["org_group"] == "Payments Eng" and apps["A1"]["owner_emails"] == ["pay-dl@example.com"]
    assert apps["A2"]["active"] and not apps["A3"]["active"]          # "confirmed" in any case; Retired isn't active
    assert r["set_aside"][0]["reason"] == "no app_id"
    assert any(n.startswith("For information: only apps with app_status 'confirmed'") and "1 Retired" in n for n in r["notes"])


def test_org_group_is_the_second_part():
    assert app_inventory.org_group("This > That > Other") == "That"
    assert app_inventory.org_group("Only one") is None
    assert app_links.sup_org_name("Payments Eng (Alex Moreno)") == "Payments Eng"


def test_owners_family_itdr_and_repos_are_linked():
    apps = app_inventory.read(INV)["rows"]
    itdr = [{"ref": 10, "application_name": "Payments Gateway", "tier_label": "Tier 1"},
            {"ref": 11, "application_name": "Card Ledgers", "tier_label": "Tier 2"}]
    gh = [{"repo": "org/pay-api"}, {"repo": "org/pay-ui"}, {"repo": "org/cards-ledger"}]
    cx = [{"key": "org/pay-api", "gh_repo": "org/pay-api"}]
    out = app_links.link(apps, PEOPLE, AD, itdr, gh, [cx], {})
    a = {x["app_id"]: x for x in apps}
    # A1: org "Payments Eng" = HR sup org without "(Manager Name)", whose people are in payments (golden source),
    # though its owner group's only member (Jo Ray) is in cards.
    assert (a["A1"]["family_id"], a["A1"]["family_how"]) == ("payments", "org")
    assert [o["sam"] for o in a["A1"]["owners"]] == ["jray"] and a["A1"]["owners"][0]["via"] == "AD group PAY-DL"
    # A2: org not found, so its owner's HR family is used.
    assert (a["A2"]["family_id"], a["A2"]["family_how"]) == ("payments", "owners (HR)")
    assert a["A1"]["itdr"]["ref"] == 10 and a["A2"]["itdr"]["ref"] == 11 and a["A2"]["itdr"]["score"] < 1
    assert a["A1"]["repos"] == ["org/pay-api", "org/pay-ui"] and a["A2"]["repos"] == ["org/cards-ledger"]
    assert gh[0]["apps"] == ["Payments Gateway (A1)"] and gh[0]["app_owners"] == ["Jo Ray"]
    assert cx[0]["apps"] == ["Payments Gateway (A1)"] and itdr[0]["apps"] == ["Payments Gateway (A1)"]
    assert a["A3"]["family_id"] is None and "itdr" not in a["A3"]                 # retired: not placed or linked
    assert out["summary"]["by_org"] == 1 and out["summary"]["by_owners"] == 1
    assert any("isn't close enough to an HR Supervisory Organization" in n or "aren't close enough" in n for n in out["notes"])


def test_owner_not_in_hr_or_ad_is_not_mapped():
    apps = app_inventory.read(inventory("B1,Thing,Confirmed,,,A > Nowhere > C,,,ghost@example.com,,,,,,,,"))["rows"]
    out = app_links.link(apps, PEOPLE, [], None, None, (), {})
    assert apps[0]["owners"] == [] and apps[0]["owners_not_mapped"] == ["ghost@example.com"]
    assert apps[0]["family_id"] is None
    assert any("not in HR or the AD owner groups file" in n for n in out["notes"])
    out = app_links.link(apps, PEOPLE, None, None, None, (), {})
    assert any("AD owner groups file not loaded" in n for n in out["notes"])


def test_owner_groups_reader():
    raw = (b"owner_email,owner_kind,group_sam,member_sam,member_email,member_name,member_enabled,included,reason\n"
           b"DL@x.com,group,DL,AB1,a@x.com,A B,True,Yes,\n"
           b"DL@x.com,group,DL,old,o@x.com,Old,False,No,disabled account\n"
           b"gone@x.com,not found,,,,,,No,not found in AD\n")
    r = owner_groups.read(raw)
    assert r["members"] == {"dl@x.com": [("ab1", "a@x.com", "DL")]}          # the disabled member is left out
    assert r["kinds"] == {"dl@x.com": "group", "gone@x.com": "not found"}
    assert r["summary"]["by_kind"] == {"group": 1, "not found": 1} and r["summary"]["left_out"] == 1
    kept, info = owner_groups.keep(raw)
    text = kept.decode()
    assert "member_name" not in text and "Old" not in text and "gone@x.com" in text and info["members_left_out"] == 1
    assert owner_groups.read(kept)["members"] == r["members"]


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    s = tmp_path / "settings.json"
    s.write_text('{"hr_root_sam_account": "dcto"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(s))
    return tmp_path


def test_upload_drops_the_retired_columns_and_mapping_places_apps(tmp_store):
    e = store.upload("app_inventory", "2026-10", INV, "app_inventory.csv", "Tester")
    for col in ("bcp_tier", "bcp_tier_source", "itdr_match", "unmapped_reasons"):
        assert col not in e["kept"]["columns_kept"]
    assert e["checks"]["rows"] == 3
    store.upload("hr", "2026-10", (FIX / "hr_firmwide.csv").read_bytes(), "hr.csv", "Tester")
    store.upload("hr_mapping", "2026-10", (FIX / "family_owners.csv").read_bytes(), "owners.csv", "Tester")
    m = mapping.map_month("2026-10")
    inv = m["feeds"]["app_inventory"]
    assert inv["placed"]["summary"]["active_apps"] == 2
    # Pat Kim (owner of A2) leads Cards in the owners file: A2's org isn't in HR, so it takes its owner's family.
    # A1's org "Payments Eng" is HR's "Payments Eng (Sam Lee)", whose one person (Pat Kim) is in Cards.
    a = {x["app_id"]: x for x in inv["rows"]}
    assert (a["A2"]["family_id"], a["A2"]["family_how"]) == ("cards", "owners (HR)")
    assert (a["A1"]["family_id"], a["A1"]["family_how"]) == ("cards", "org")
    assert a["A1"]["owners_not_mapped"] == ["pay-dl@example.com"]          # no AD owner groups file uploaded
    assert lock.is_informational("app_inventory", "For information: anything")
    assert not lock.is_informational("app_inventory", "1 of 2 active apps linked to an ITDR application by name")


def test_drill_down_shows_apps_and_owners():
    items = [{"id": "org/pay-api", "passed": False, "apps": ["Payments Gateway (A1)"], "app_owners": ["Jo Ray"]},
             {"id": "org/other", "passed": True}]
    ev = evidence.page_evidence({"items": {"payments": {"SE-01": items}}}, "2026-10")["payments"]["SE-01"]
    assert ev["by_app"] == [{"app_id": "Payments Gateway (A1)", "num": 0, "den": 1, "override": False},
                            {"app_id": "NO-APP", "num": 1, "den": 1, "override": False}]
    assert ev["items"][0]["app_id"] == "Payments Gateway (A1)" and ev["items"][0]["attributes"] == {"app_owners": "Jo Ray"}
    rows = evidence.family_items({"items": {"payments": {"SE-01": items}}}, "payments")
    assert rows[0]["app"] == "Payments Gateway (A1)" and rows[0]["app_owners"] == "Jo Ray"
    assert evidence.page_evidence({"items": {"p": {"SE-01": items[1:]}}}, "2026-10")["p"]["SE-01"]["by_app"] == []


def test_name_shortlist_finds_every_close_name():
    """Speed only (6 Nov 2026): the shortlist must never drop a name the full comparison would match."""
    import random
    import string
    from trust.intake.itdr import name_similarity
    rng = random.Random(5)
    words = ["".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, 9))) for _ in range(120)]
    cands = [" ".join(rng.choices(words, k=rng.randint(1, 4))) for _ in range(300)]
    idx = app_links._index({c: c for c in cands})
    for _ in range(150):
        w = rng.choice(cands).split()
        rng.shuffle(w)
        i = rng.randrange(len(w))
        w[i] = w[i][:-1] or w[i]                               # reordered and a letter dropped
        q = " ".join(w)
        full = {c for c in cands if name_similarity(q, c) >= 0.85}
        assert full <= set(idx["__grams__"].shortlist(q)), q


def test_linked_itdr_apps_take_the_inventory_family():
    """Owner, 6 Nov 2026: the inventory is the golden source for ITDR placement; unlinked apps keep their area's."""
    apps = app_inventory.read(INV)["rows"]
    itdr = [{"ref": 10, "application_name": "Payments Gateway", "tier_label": "Tier 1", "family_id": "cards"},
            {"ref": 12, "application_name": "Something Else", "tier_label": "Tier 1", "family_id": "cards"}]
    out = app_links.link(apps, PEOPLE, AD, itdr, None, (), {})
    assert itdr[0]["family_id"] == "payments" and itdr[0]["family_match"]["how"] == "app inventory"
    assert itdr[1]["family_id"] == "cards"                                  # not linked: Business Product Area
    assert any("changed family" in n and "cards → payments" in n for n in out["itdr_notes"])
    itdr[0]["family_id"] = "cards"
    app_links.link(apps, PEOPLE, AD, itdr, None, (), {"itdr_family_from_inventory": False})
    assert itdr[0]["family_id"] == "cards"                                  # switched off


def test_tr01_counts_repos_linked_to_an_app():
    from trust import measure
    rows = [{"repo": "org/a", "active": True, "family_id": "payments", "apps": ["A (1)"]},
            {"repo": "org/b", "active": True, "family_id": "payments", "apps": []},
            {"repo": "org/c", "active": True, "family_id": "payments", "apps": ["A (1)", "B (2)"]},
            {"repo": "org/d", "active": False, "family_id": "payments", "apps": ["A (1)"]}]
    r = measure.tr01({"repos": {"rows": rows}})["payments"]
    assert (r["numerator"], r["denominator"]) == (2, 3)          # owner, 6 Nov 2026: a shared repo counts as mapped
    assert [evidence.describe("TR-01", it)["result"] for it in r["items"]] == [
        "Mapped to one app", "Not mapped to an app in the app inventory", "Mapped to 2 apps"]
    assert [evidence.describe("TR-01", it)["concern"] for it in r["items"]] == [False, True, False]
    assert measure.NEEDS_ALSO["TR-01"] == "app_inventory" and "TR-01" in measure.SWITCHABLE


def test_blank_area_is_only_a_warning_when_the_inventory_doesnt_place_the_app(tmp_store):
    """Owner, 6 Nov 2026: ITDR applications the app inventory places don't need a Business Product Area."""
    itdr_csv = (b"Ref,Application Name,Business Product Area,Recovery Tier\n"
                b"10,Payments Gateway,,Tier 1\n"          # blank area, but the inventory places it
                b"11,Lonely App,,Tier 2\n")              # blank area, not in the inventory: still a warning
    for feed, data, name in (("hr", (FIX / "hr_firmwide.csv").read_bytes(), "hr.csv"),
                             ("hr_mapping", (FIX / "family_owners.csv").read_bytes(), "owners.csv"),
                             ("itdr", itdr_csv, "itdr.csv"), ("app_inventory", INV, "app_inventory.csv")):
        store.upload(feed, "2026-10", data, name, "Tester")
    m = mapping.map_month("2026-10")
    notes = m["feeds"]["itdr"]["notes"]
    rows = {r["ref"]: r for r in m["feeds"]["itdr"]["rows"]}
    assert rows[10]["family_id"] == "cards" and rows[10]["family_match"]["how"] == "app inventory"
    assert any(n.startswith("1 application has no Business Product Area") for n in notes), notes
    assert not any(n.startswith("2 applications have no Business Product Area") for n in notes)
    assert any(n.startswith("For information: 1 of 2 ITDR applications were placed by the app inventory") for n in notes)
    assert all(lock.is_informational("itdr", n) for n in notes if n.startswith("For information"))
