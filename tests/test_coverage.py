"""How much has to be measured before a building block or TRUST shows (setting "coverage"; owner, 4 Nov 2026)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import scoring  # noqa: E402

ANY = {"block_min_share": 0, "trust_min_blocks": 1}
OLD = {"block_min_share": 0.5, "trust_min_blocks": 3}
M = [dict(id=f"{c}-0{i}", block=c) for c in scoring.BLOCKS for i in (1, 2, 3)]


def r(status):
    return {"status": status}


def test_a_block_scores_from_any_one_scored_metric():
    ms = [("REL-01", r("Green")), ("REL-02", r("N/A")), ("REL-03", r("N/A"))]      # 1 of 3 arrived metrics scored
    assert scoring.block(ms, None, ANY)[0]["score"] == 100
    assert scoring.block(ms, None, OLD)[0]["status"] == "Insufficient data"
    none = [("REL-01", r("N/A")), ("REL-02", r("N/A"))]
    assert scoring.block(none, None, ANY)[0]["status"] == "Insufficient data"   # still needs one


def test_trust_from_any_scored_block():
    fr = {"metrics": {"REL-01": r("Green"), "SEC-01": r("Amber")}}
    blocks, trust, status, _ = scoring.family(fr, M, None, ANY)
    assert trust == 75 and status == "Amber"
    assert scoring.family(fr, M, None, OLD)[1] is None
    assert scoring.family({"metrics": {}}, M, None, ANY)[1] is None             # no block at all: no score


def test_bad_settings_fall_back_to_the_original_rules():
    assert scoring.coverage_from(None) == OLD
    assert scoring.coverage_from({"block_min_share": 2, "trust_min_blocks": 0}) == OLD
    assert scoring.coverage_from({"trust_min_blocks": True}) == OLD
