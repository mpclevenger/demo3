"""tools/make_test_data.py (owner, 5 Nov 2026): a standalone script writes made-up provider files that go through
the normal steps and score every family; the app itself has no seeding. Same seed, same files."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import make_test_data  # noqa: E402
from testdata import seed_store  # noqa: E402
from trust import storage  # noqa: E402


@pytest.fixture
def test_store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRUST_DATABASE_URL", raising=False)
    monkeypatch.setenv("TRUST_STORE_DIR", str(tmp_path / "store"))
    (tmp_path / "s.json").write_text('{"hr_root_sam_account": "cto.demo"}')
    monkeypatch.setenv("TRUST_SETTINGS", str(tmp_path / "s.json"))
    return tmp_path


def test_files_score_every_family(test_store):
    months = ["2026-09", "2026-10"]
    seed_store(months, families=6)
    data = json.loads((test_store / "store" / "published" / "data.json").read_text())
    for month in months:
        fams = data["periods"][month]["families"]
        assert len(fams) == 6
        assert all(isinstance(f["trust"], (int, float)) for f in fams.values()), month
        assert isinstance(data["periods"][month]["firm_trust"], (int, float))
    assert storage.months("scored") == months


def test_write_files_and_manifest(tmp_path):
    m = make_test_data.write_files(tmp_path / "demo", ["2026-10"], families=4)
    assert m["cto_sam"] == "cto.demo" and set(m["months"]) == {"2026-10"}
    files = m["months"]["2026-10"]
    assert {"hr", "hr_mapping", "tcc", "itdr", "dr_tests", "cx_sast", "cx_sca", "repos"} <= set(files)
    for name in files.values():
        assert (tmp_path / "demo" / "2026-10" / name).stat().st_size > 0
    assert (tmp_path / "demo" / "manifest.json").exists() and "cto.demo" in (tmp_path / "demo" / "README.txt").read_text()


def test_same_seed_same_files(tmp_path):
    a = make_test_data.make_month(make_test_data.make_world(families=5, seed=3), "2026-10")
    b = make_test_data.make_month(make_test_data.make_world(families=5, seed=3), "2026-10")
    assert {k: v[1] for k, v in a.items()} == {k: v[1] for k, v in b.items()}


def test_the_app_has_no_seed_command():
    import subprocess
    r = subprocess.run([sys.executable, "manage.py", "seed"], capture_output=True, text=True,
                       cwd=pathlib.Path(__file__).resolve().parents[1])
    assert r.returncode != 0 and "invalid choice" in r.stderr
