"""Lock and reopen a month, by hand from the Tech Risk console (owner, 3 Nov 2026).

Locking a month:
- checks the scorecard is up to date: the newest scoring used the newest mapping, and the mapping used
  the newest file of every feed. Otherwise it says "update the scorecard first", so the lock seals what
  people see on screen;
- stores the seal: fingerprints (SHA-256) of the scored result, the mapped result, each file used,
  the settings and the month's comments, plus the git commit;
- marks the month locked, so upload, map and score refuse it, and publishes so the page shows it.

Reopening needs a reason. The month is open again and can be changed and locked again. Both are in the
event log, and the old seal stays there. (A lock on a set date may come later.)
"""
import datetime
import hashlib

from . import publish, storage, store


def is_informational(feed, note):
    """A mapping note that reports nothing wrong (owner, 5 Nov 2026): shown "for information", never
    acknowledged, never blocks the lock. Everything else is a warning."""
    import re
    from . import config
    m = re.match(r"(\d+) of (\d+) (?:Checkmarx|app inventory) repos matched to a GitHub repo", note)
    if m and m.group(1) == m.group(2):
        return True                                          # every repo matched: nothing to look at
    root = (config.settings().get("hr_root_sam_account") or "").strip().lower()
    if root and "has no family owner above them" in note and note.rstrip(".").lower().endswith(root):
        return True                                          # the CTO has nobody above them by definition
    if note.startswith("For information: "):
        return True                                          # counts only (app inventory, owner 6 Nov 2026)
    m = re.match(r"(\d+) of (\d+) active apps? linked to an ITDR application", note)
    if m and m.group(1) == m.group(2):
        return True
    if note.startswith("Working rules until Change Management answers"):
        return True                                          # a standing note about the Non-TCC rules, not a finding
    return False


def warnings(month, include_info=False):
    """The month's warnings from its newest mapping, each with its acknowledgement (or None).
    Informational notes are left out unless include_info; with it, each carries info=True/False."""
    mapped = storage.load_month("mapped", month)
    if mapped is None:
        return []
    done, out = storage.acks(month), []
    pairs = [(feed, n) for feed, v in sorted(mapped["feeds"].items()) for n in v.get("notes") or []]
    pairs += [("general", n) for n in mapped.get("notes") or []]
    for feed, note in pairs:
        info = is_informational(feed, note)
        if info and not include_info:
            continue
        key = hashlib.sha256(f"{feed}|{note}".encode()).hexdigest()[:16]
        out.append({"feed": feed, "note": note, "key": key, "ack": done.get(key), "info": info})
    return out


def acknowledge(month, keys, by, reason=""):
    """Acknowledge some of the month's current warnings, by key. Returns how many were newly acknowledged."""
    store._check(store.FEEDS[0], month)
    storage.ensure_open(month)
    current = {w["key"]: w for w in warnings(month)}
    unknown = [k for k in keys if k not in current]
    if unknown:
        raise ValueError("Some of those warnings have changed since the page was loaded. Reload and try again.")
    n = 0
    for k in keys:
        w = current[k]
        if w["ack"] is None:
            storage.add_ack(month, w["feed"], k, w["note"], by, " ".join(str(reason or "").split()))
            n += 1
    if n:
        storage.log("acknowledge", by, month, f"{n} warning{'s' if n != 1 else ''}" + (f" ({reason})" if reason else ""),
                    {"keys": keys, "reason": reason})
    return n


def _label(month):
    y, m = map(int, month.split("-"))
    return datetime.date(y, m, 1).strftime("%B %Y")


def seal(month):
    """Work out the seal for a month as it stands now, or raise ValueError saying what to do first."""
    scored = storage.load_month("scored", month)
    if scored is None:
        raise ValueError(f"{_label(month)} hasn't been scored yet. Update the scorecard first.")
    mapped = storage.load_month("mapped", month)
    if mapped is None or scored.get("based_on_mapped_sha256") != storage.doc_sha256(mapped):
        raise ValueError(f"{_label(month)} was mapped again after it was scored. Update the scorecard first, "
                         "so the lock seals what people see.")
    files, stale = [], []
    for feed in store.FEEDS:
        reg = storage.register(month, feed)
        if not reg:
            continue
        e = reg[-1]
        files.append({"feed": feed, "file": e.get("original_name"), "original_sha256": e.get("original_sha256"),
                      "kept_sha256": e.get("sha256"), "uploaded_by": e.get("uploaded_by"),
                      "uploaded_at": e.get("uploaded_at")})
        used = mapped["feeds"].get(feed) or {}
        if (used.get("original_sha256"), used.get("sha256")) != (e.get("original_sha256"), e.get("sha256")):
            stale.append(feed)
    if stale:
        raise ValueError(f"A newer file arrived after the last update ({', '.join(stale)}). "
                         "Update the scorecard first, so the lock seals what people see.")
    ws = warnings(month)
    open_ = [w for w in ws if w["ack"] is None]
    if open_:
        raise ValueError(f"{len(open_)} warning{'s' if len(open_) != 1 else ''} from the checks "
                         f"{'haven' if len(open_) != 1 else 'hasn'}'t been acknowledged yet. Read and acknowledge "
                         "them on This month first.")
    return {"warnings_acknowledged": len(ws), "warnings_sha256": storage.doc_sha256(ws),
            "scored_sha256": storage.doc_sha256(scored), "mapped_sha256": storage.doc_sha256(mapped),
            "files": files, "settings_sha256": storage.settings_sha256(),
            "comments_sha256": storage.doc_sha256(storage.comments(month)),
            "comments": len(storage.comments(month)), "git_sha": storage.git_sha()}


def lock(month, by):
    store._check(store.FEEDS[0], month)
    if storage.month_status(month)["status"] == "locked":
        raise ValueError(f"{_label(month)} is already locked.")
    from . import jobs
    if jobs.running(month):
        raise ValueError(f"{_label(month)} is being updated right now. Lock it once the update has finished.")
    s = seal(month)
    # Freeze the month as people see it now (owner, 5 Nov 2026): the page copy, with its change arrows,
    # prior values, history and watch list, is kept in the lock record and shown unchanged from then on,
    # whatever happens to the months around it. Its fingerprint is in the seal; the copy itself isn't logged.
    shown = publish.shown_period(month)
    s["shown_sha256"] = storage.doc_sha256(shown)
    at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    storage.set_month_status(month, "locked", by, at, {**s, "shown": shown})
    storage.log("lock", by, month, f"locked with {len(s['files'])} files", s)
    publish.run(by)
    return storage.month_status(month)


def reopen(month, by, reason):
    store._check(store.FEEDS[0], month)
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise ValueError("Say why the month is being reopened. The reason is kept in the record.")
    st = storage.month_status(month)
    if st["status"] != "locked":
        raise ValueError(f"{_label(month)} isn't locked.")
    storage.set_month_status(month, "open")
    storage.log("reopen", by, month, reason, {"earlier_seal": st["seal"], "locked_by": st["locked_by"],
                                              "locked_at": st["locked_at"]})
    publish.run(by)
    return storage.month_status(month)
