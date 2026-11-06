"""Fill a test store with the made-up months from tools/make_test_data.py, through the normal steps."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "backend"))
import make_test_data  # noqa: E402
from trust import mapping, publish, score_month, store  # noqa: E402


def seed_store(months, families=6, seed=7, cto_sam="cto.demo"):
    world = make_test_data.make_world(families=families, seed=seed, cto_sam=cto_sam)
    for month in months:
        for feed, (name, data) in make_test_data.make_month(world, month).items():
            store.upload(feed, month, data, name, "Test data")
        mapping.map_month(month, "Test data")
        score_month.run(month, "Test data")
    publish.run("Test data")
