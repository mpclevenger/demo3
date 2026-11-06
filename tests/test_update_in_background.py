"""Update the scorecard runs in the background (owner, 4 Nov 2026): the request answers at once, the page asks
how it is going, one update per month at a time, and a failure or a stopped update is said plainly."""
import datetime
import threading
import time

from test_web import H, client, up  # noqa: F401  (client is a fixture)

from trust import jobs, mapping, storage


def poll(client, month, job, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        s = client.get(f"/api/update/{month}/{job}").json
        if s["state"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("update never finished")


def test_update_answers_at_once_and_finishes_in_the_background(client, monkeypatch):
    monkeypatch.setattr(jobs, "WAIT", False)
    up(client, "tcc", "tcc_export.csv")
    gate, real = threading.Event(), mapping.map_month
    monkeypatch.setattr(mapping, "map_month", lambda *a, **k: (gate.wait(10), real(*a, **k))[1])
    r = client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H).json
    assert r["ok"] and r["state"] == "running" and r["job"]
    # A second press, and a lock, while it runs are refused in plain words.
    again = client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H)
    assert again.status_code == 400 and "already being updated" in again.json["error"]
    lock = client.post("/api/lock", json={"month": "2026-09", "by": "Tester"}, headers=H)
    assert lock.status_code == 400 and "being updated right now" in lock.json["error"]
    gate.set()
    s = poll(client, "2026-09", r["job"])
    assert s["state"] == "finished" and "tcc" in s["received"] and s["note"].startswith("in ")
    assert "2026-09" in client.get("/data.json").json["periods"]
    acts = [e["action"] for e in storage.events("2026-09")]
    assert "update started" in acts and "update finished" in acts


def test_a_failure_is_reported_with_the_step(client, monkeypatch):
    monkeypatch.setattr(jobs, "WAIT", False)
    up(client, "tcc", "tcc_export.csv")

    def broken(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(jobs.score_month, "run", broken)
    r = client.post("/api/update", json={"month": "2026-09", "by": "Tester"}, headers=H).json
    s = poll(client, "2026-09", r["job"])
    assert s["state"] == "failed" and "while scoring" in s["message"] and "disk full" in s["message"]
    # Failed means not running: Update can be pressed again.
    assert jobs.running("2026-09") is None


def test_an_update_that_never_finished_counts_as_stopped(client):
    up(client, "tcc", "tcc_export.csv")
    storage.log("update started", "Tester", "2026-09", "", {"job": "old1"})
    real = jobs._now
    jobs._now = lambda: real() + datetime.timedelta(minutes=jobs.STALE_MINUTES + 1)
    try:
        assert jobs.status("2026-09", "old1")["state"] == "stopped"
        assert jobs.running("2026-09") is None
    finally:
        jobs._now = real
    assert client.get("/api/update/2026-09/nope").json["state"] == "unknown"
