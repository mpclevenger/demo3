"""Metric cards link to the code behind them (owner, 5 Nov 2026), with real line numbers, only when code_repo_url is set."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import codelinks  # noqa: E402


def _settings(tmp_path, monkeypatch, **extra):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"hr_root_sam_account": "x", **extra}))
    monkeypatch.setenv("TRUST_SETTINGS", str(p))


def test_no_repo_address_means_no_links(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch)
    assert codelinks.links() == {}


def test_every_mapped_function_resolves_to_real_lines(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, code_repo_url="https://github.example.com/tech-risk/trust/")
    monkeypatch.setenv("TRUST_GIT_SHA", "abc1234")
    out = codelinks.links()
    assert out["ref"] == "abc1234" and out["repo"].endswith("/trust")
    for mid, places in codelinks.METRIC_CODE.items():
        rows = out["metrics"][mid]
        assert len(rows) == len(places) + len(codelinks.SHARED), mid
        for r in rows:
            assert 0 < r["from"] <= r["to"]
            assert r["url"] == f"https://github.example.com/tech-risk/trust/blob/abc1234/{r['file']}#L{r['from']}-L{r['to']}"
    rule = next(r for r in out["metrics"]["TE-02"] if "client impact" in r["what"])
    src = (pathlib.Path(__file__).resolve().parents[1] / "backend/trust/score_month.py").read_text().splitlines()
    assert any('client_impact' in src[n - 1] for n in range(rule["from"], rule["to"] + 1))
    assert rule["to"] - rule["from"] <= 4                      # the rule, not the whole function


def test_ref_falls_back_to_code_ref(tmp_path, monkeypatch):
    _settings(tmp_path, monkeypatch, code_repo_url="https://x.example/r", code_ref="release")
    monkeypatch.delenv("TRUST_GIT_SHA", raising=False)
    monkeypatch.setattr(codelinks.storage, "git_sha", lambda: None)
    assert codelinks.links()["ref"] == "release"
