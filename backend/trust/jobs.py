"""Update the scorecard in the background (owner, 4 Nov 2026).

The website's "Update the scorecard" used to map, score and publish inside one web request. With real files
that can take longer than the platform waits, and the platform then answers 503 although TRUST is still
working. Now the request only starts the work and answers at once; the page asks every few seconds how
it is going.

Progress is kept in the event log (actions "update started", "update finished", "update failed", each with
the job's id), so every web worker can answer, and the month's Recent activity shows it. Only one update per
month runs at a time. The command line (python manage.py map / score / publish) is unchanged.

With the database (5 Nov 2026, from review): the running update holds a database lock on its month
(pg_try_advisory_lock on its own connection) for as long as it works. The lock goes away with the process,
so a restart part-way frees the month at once instead of after STALE_MINUTES, and two web workers can't
start the same month: the second one finds the lock held. Without the database (laptop, tests) the old
rule stands: no finish after STALE_MINUTES counts as stopped.
"""
import datetime
import threading
import traceback
import uuid

from . import mapping, publish, score_month, storage

STALE_MINUTES = 20
WAIT = False      # tests only: start_update waits for the work to finish (the same code runs either way)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _when(iso):
    try:
        d = datetime.datetime.fromisoformat(str(iso))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def _jobs(month):
    """{job id: {started, by, finished?, failed?}} from the month's recent events, oldest first."""
    out = {}
    for e in reversed(storage.events(month, limit=500)):
        d = e.get("detail") or {}
        job = d.get("job") if isinstance(d, dict) else None
        if not job or e.get("month") != month:
            continue
        j = out.setdefault(job, {"job": job, "month": month})
        if e["action"] == "update started":
            j.update(started=e["at"], by=e["by"])
        elif e["action"] == "update finished":
            j.update(finished=e["at"], note=e.get("note"), seconds=d.get("seconds"), received=d.get("received"))
        elif e["action"] == "update failed":
            j.update(failed=e["at"], error=d.get("error") or e.get("note"), step=d.get("step"))
    return out


def _lock_key(month):
    return f"trust-update:{month}"


def _try_hold(month):
    """With the database: a connection holding the month's update lock, or None if someone else holds it.
    Without the database: a stand-in that is always granted."""
    if not storage.using_database():
        return True
    c = storage.connect()
    got = c.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (_lock_key(month),)).fetchone()[0]
    if got:
        return c
    c.close()
    return None


def _release(held):
    if held is not True and held is not None:
        try:
            held.close()            # closing the session releases its advisory locks
        except Exception:
            pass


def _held_elsewhere(month):
    """Is an update for the month really running right now (its lock held)? Database only."""
    h = _try_hold(month)
    if h is None:
        return True
    _release(h)
    return False


def status(month, job):
    """'running', 'finished', 'failed' or 'stopped' (lock no longer held, or no finish within
    STALE_MINUTES without the database), with plain words."""
    j = _jobs(month).get(job)
    if not j or "started" not in j:
        return {"job": job, "state": "unknown", "message": "TRUST has no record of that update. Reload the page."}
    if "finished" in j:
        return {**j, "state": "finished"}
    if "failed" in j:
        return {**j, "state": "failed",
                "message": f"The update stopped while {j.get('step') or 'working'}: {j.get('error')}"}
    started = _when(j["started"])
    stopped = (not _held_elsewhere(month)) if storage.using_database() else \
        (started and _now() - started > datetime.timedelta(minutes=STALE_MINUTES))
    if stopped:
        return {**j, "state": "stopped",
                "message": f"The update started at {j['started'][11:16]} UTC never finished (the server may have "
                           "restarted). Press Update the scorecard again."}
    return {**j, "state": "running"}


def running(month):
    """The update running now for the month, or None."""
    for job in reversed(list(_jobs(month))):
        s = status(month, job)
        if s["state"] == "running":
            return s
    return None


_start_lock = threading.Lock()


def start_update(month, by):
    """Start map + score + publish for the month in the background. Returns the job id.
    Raises ValueError when an update for the month is already running."""
    with _start_lock:              # two presses in the same worker; across workers the database lock decides
        r = running(month)
        if r:
            raise ValueError(f"The scorecard for {month} is already being updated (started {r['started'][11:16]} "
                             f"UTC by {r.get('by')}). Wait for it to finish.")
        held = _try_hold(month)
        if held is None:
            raise ValueError(f"The scorecard for {month} is already being updated. Wait for it to finish.")
        job = uuid.uuid4().hex[:12]
        storage.log("update started", by, month, "", {"job": job})
    t = threading.Thread(target=_run, args=(month, by, job, held), daemon=True, name=f"update-{month}")
    t.start()
    if WAIT:
        t.join()
    return job


def _run(month, by, job, held=True):
    t0, step = _now(), "reading the files"
    try:
        mapped = mapping.map_month(month, by)
        step = "scoring"
        score_month.run(month, by)
        step = "publishing"
        publish.run(by)
        secs = round((_now() - t0).total_seconds())
        storage.log("update finished", by, month, f"in {secs} seconds",
                    {"job": job, "seconds": secs, "received": mapped.get("received")})
    except Exception as err:                    # say what went wrong on the page, plainly; full detail in the logs
        print(f"update {job} for {month} failed while {step}", flush=True)
        traceback.print_exc()
        storage.log("update failed", by, month, f"while {step}", {"job": job, "step": step, "error": str(err)[:500]})
    finally:
        _release(held)
