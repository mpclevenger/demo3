"""The website: shows the published scorecard, and lets people upload files and update it.

Who can get in is the company's access add-on container in front of TRUST (owner, 2 Nov 2026), so
there is no sign-in here. The add-on passes each person's SAM_ACCOUNT and AD groups; access.py turns
them into roles, and every page, file and change below is checked against the role (owner, 3 Nov 2026).
Until the add-on's header is named in config/access.json, TRUST runs open: anyone past the add-on can
do everything and types their name. Started by gunicorn from the Procfile.

Changes come in as POST requests to /api/... and must carry the header X-TRUST: 1. A browser won't
add that header to a request from another site without asking this one first, so another site can't
make someone's browser change TRUST behind their back.
"""
import json
import os
import re

from flask import Flask, Response, g, jsonify, request

from . import access, evidence, jobs, lock as locking, mapping, publish, score_month, storage, store
from .intake.common import upload_time

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("TRUST_MAX_UPLOAD_MB", "55")) * 1024 * 1024

TYPES = {"index.html": "text/html; charset=utf-8", "data.json": "application/json",
         "evidence.json": "application/json"}

@app.after_request
def headers(resp):
    resp.headers["Cache-Control"] = "no-store"             # scorecard data isn't kept in browser or proxy caches
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _file(name):
    """The published page and data, cut down to what this person may see, with who they are added."""
    pr = g.person
    if name == "evidence.json":
        body = storage.published(name)
        if body is None:
            return Response("{}", content_type=TYPES[name])
        ev = access.filter_evidence(json.loads(body), pr)
        if not pr["open"]:
            storage.log("view", _by(pr), None, "item detail", {"families": sorted({f for x in ev.values() for f in x})})
        return Response(json.dumps(ev, ensure_ascii=False), content_type=TYPES[name])
    # The published data, plus months with uploads not scored yet; the real site, empty, before any publish
    # (owner, 4 Nov 2026).
    stored = storage.published("data.json")
    data = publish.site_data(json.loads(stored) if stored else None, upload_time().strftime("%Y-%m"))
    data = access.filter_data(data, pr)
    data["access"] = {"enforced": not pr["open"], "me": None if pr["open"] else access.me(pr)}
    if name == "data.json":
        return Response(json.dumps(data, ensure_ascii=False), content_type=TYPES[name])
    # Always the page as deployed now, with the published data in it (4 Nov 2026): a page saved by an
    # earlier publish would keep serving that version's screens until the next update.
    return Response(publish.page_html(data), content_type=TYPES[name])


@app.get("/")
def index():
    return _file("index.html")


@app.get("/<any('index.html','data.json','evidence.json'):name>")
def published(name):
    return _file(name)


@app.get("/healthz")
def healthz():
    """For the platform's health check: is the app up, and can it reach the database?"""
    if storage.using_database():
        try:
            with storage.connect() as c:
                c.execute("SELECT 1")
        except Exception:                                   # say no without echoing connection details
            return Response("database not reachable", status=503, mimetype="text/plain")
    return Response("ok", mimetype="text/plain")


# ---- changes (upload, update) ----

class Refused(ValueError):
    """A change TRUST won't make, with a plain reason for the person."""


def _by(pr):
    return f"{pr['name']} ({pr['sam']})" if pr["name"] and pr["name"] != pr["sam"] else pr["sam"]


def _who(body):
    """Who is making the change: the signed-in person, or (while TRUST runs open) the name they typed."""
    if not g.person["open"]:
        return _by(g.person)
    by = " ".join(str(body.get("by") or "").split())
    if not by:
        raise Refused("Type your name first, so the record shows who did this.")
    if len(by) > 100:
        raise Refused("That name is too long (100 characters at most).")
    return by


class NotAllowed(Exception):
    """The person's role doesn't allow this."""


NO_ACCESS = ("You don't have access to TRUST. Ask Tech Risk to add you to the right group, or check that you "
             "are in a product family's line in HR.")


@app.before_request
def who_is_asking():
    if request.path == "/healthz":
        return None
    g.person = access.person(request.headers)
    if not access.has_access(g.person):
        if request.path.startswith("/api/"):
            return jsonify(ok=False, error=NO_ACCESS), 403
        return Response(f"<!doctype html><title>TRUST</title><p style=\"font-family:system-ui;margin:3em\">{NO_ACCESS}</p>",
                        status=403, mimetype="text/html")
    if request.method == "POST" and request.path.startswith("/api/") and request.headers.get("X-TRUST") != "1":
        return jsonify(ok=False, error="This change didn't come from the TRUST page, so it wasn't made."), 403
    return None


def require(action, family=None):
    if not access.can(g.person, action, family):
        raise NotAllowed()


@app.errorhandler(NotAllowed)
def not_allowed(_err):
    return jsonify(ok=False, error="Your role doesn't allow this. Ask Tech Risk if you think it should."), 403


@app.errorhandler(Refused)
@app.errorhandler(ValueError)
def refused(err):
    app.logger.warning("refused %s %s: %s", request.method, request.path, err)   # visible in the platform's logs
    return jsonify(ok=False, error=str(err)), 400


@app.errorhandler(413)
def too_big(_err):
    mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify(ok=False, error=f"That file is bigger than {mb} MB, so it wasn't uploaded."), 413


@app.get("/api/month/<month>")
def month_state(month):
    """What has been received for a month: the newest upload per feed."""
    require("console_read")
    store._check(store.FEEDS[0], month)
    feeds = {}
    for feed in store.FEEDS:
        reg = storage.register(month, feed)
        if reg:
            e = reg[-1]
            feeds[feed] = {k: e.get(k) for k in ("original_name", "uploaded_by", "uploaded_at", "original_sha256",
                                                  "size_bytes", "sharepoint_link", "kept")}
            feeds[feed]["uploads"] = len(reg)
    return jsonify(ok=True, month=month, feeds=feeds, status=storage.month_status(month),
                   events=storage.events(month, 30), warnings=locking.warnings(month, include_info=True),
                   runs={k: storage.run_info(k, month) for k in ("mapped", "scored")})


@app.post("/api/upload")
def upload():
    require("run_month")
    f = request.files.get("file")
    if f is None:
        raise Refused("Choose a file to upload.")
    by = _who(request.form)
    e = store.upload(request.form.get("feed", ""), request.form.get("month", ""), f.read(), f.filename, by,
                     (request.form.get("link") or "").strip() or None)
    return jsonify(ok=True, note=e["note"], feed=e["feed"], month=e["month"],
                   original_sha256=e.get("original_sha256"), kept=e.get("kept"), checks=e.get("checks"))


@app.post("/api/update")
def update():
    """Start mapping, scoring and publishing a month, in the background (jobs.py), and answer at once, so a long
    update never runs into the platform's time limit (a 503). The page then asks /api/update/<month>/<job>."""
    require("run_month")
    body = request.get_json(silent=True) or {}
    by, month = _who(body), str(body.get("month") or "")
    store._check(store.FEEDS[0], month)
    storage.ensure_open(month)
    if not any(storage.register(month, feed) for feed in store.FEEDS):
        raise Refused(f"Nothing has been uploaded for {month} yet, so there is nothing to update.")
    job = jobs.start_update(month, by)
    return jsonify({**jobs.status(month, job), "ok": True})


@app.get("/api/update/<month>/<job>")
def update_status(month, job):
    """How a background update is going: running, finished, failed or stopped."""
    require("run_month")
    store._check(store.FEEDS[0], month)
    return jsonify(ok=True, **jobs.status(month, job))


# ---- lock and reopen (by hand, from the Tech Risk console) ----

@app.post("/api/lock")
def lock_month():
    require("run_month")
    body = request.get_json(silent=True) or {}
    by, month = _who(body), str(body.get("month") or "")
    return jsonify(ok=True, status=locking.lock(month, by))


@app.post("/api/reopen")
def reopen_month():
    require("run_month")
    body = request.get_json(silent=True) or {}
    by, month = _who(body), str(body.get("month") or "")
    return jsonify(ok=True, status=locking.reopen(month, by, body.get("reason")))


@app.post("/api/acknowledge")
def acknowledge():
    require("run_month")
    body = request.get_json(silent=True) or {}
    by, month, keys = _who(body), str(body.get("month") or ""), body.get("keys") or []
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        raise Refused("Choose which warnings to acknowledge.")
    n = locking.acknowledge(month, keys, by, str(body.get("reason") or "")[:500])
    return jsonify(ok=True, acknowledged=n)


# ---- comments (explanations, data queries, actions); they never change a score ----

KINDS = {"explanation", "query", "action"}


def _published_ids():
    """The family and metric ids on the published scorecard, to check a comment points at something real."""
    import json
    d = json.loads(storage.published("data.json") or "{}")
    return {f["id"] for f in d.get("families", [])}, {m["id"] for m in d.get("metrics", [])}


@app.get("/api/comments/<month>")
def list_comments(month):
    store._check(store.FEEDS[0], month)
    cs = storage.comments(month)
    if not access.sees_all(g.person):
        mine = g.person["lead_of"] | g.person["member_of"]
        cs = [c for c in cs if c["family"] in mine]
    return jsonify(ok=True, comments=cs)


@app.post("/api/comments")
def add_comment():
    body = request.get_json(silent=True) or {}
    by, month = _who(body), str(body.get("month") or "")
    store._check(store.FEEDS[0], month)
    families, metrics = _published_ids()
    blocks = {b["code"] for b in score_month.template().get("blocks", [])}
    family, metric, block = body.get("family"), body.get("metric") or None, body.get("block") or None
    kind, text = body.get("kind"), str(body.get("text") or "").strip()
    reply_to, parent = body.get("reply_to"), None
    if reply_to is not None:        # a reply is on the same thing as the comment it answers
        try:
            parent = storage.comment(int(reply_to))
        except (TypeError, ValueError):
            parent = None
        if not parent or parent["month"] != month or parent["family"] != family:
            raise Refused("The comment you're replying to isn't on this page.")
        kind, metric, block, reply_to = parent["kind"], parent["metric"], parent["block"], parent["id"]
    if family not in families:
        raise Refused("That family isn't on the scorecard.")
    require("reply" if parent is not None else "comment", family)
    if metric is not None and metric not in metrics:
        raise Refused("That metric isn't on the scorecard.")
    if block is not None and block not in blocks:
        raise Refused("That building block isn't on the scorecard.")
    if kind not in KINDS:
        raise Refused("Choose explanation, data query or action.")
    if not text:
        raise Refused("Write something first.")
    if len(text) > 4000:
        raise Refused("That's longer than 4,000 characters; please shorten it.")
    status = None
    if parent is not None:
        if kind in ("query", "action"):
            status = body.get("status") or "answered"
            if status not in ("open", "answered", "closed"):
                raise Refused("Status must be open, answered or closed.")
            if status == "closed":
                require("close")                    # family leads reply; Tech Risk closes
    elif kind in ("query", "action"):
        status = "open"
    after = storage.month_status(month)["status"] == "locked"
    c = storage.add_comment({"month": month, "family": family, "metric": metric, "block": block, "kind": kind,
                             "text": text, "by": by, "reply_to": reply_to, "status": status, "after_lock": after})
    storage.log("comment", by, month, f"{kind} on {family}" + (" (received after lock)" if after else ""),
                {"comment_id": c["id"], "family": family, "metric": metric})
    return jsonify(ok=True, comment=c)


# ---- proposals to change the metric dictionary, and decisions on them ----
# Approving a proposal records the decision only. Changing the dictionary or the scoring is done
# separately, with the owner's agreement.

import re

PROPOSAL_KINDS = {"change": "change", "new_metric": "new metric", "retire": "retirement"}
DECISIONS = {"approved", "returned", "declined", "withdrawn"}
REQUIRED_DETAIL = {"change": ("field", "wording", "reason"), "retire": ("reason", "effective"),
                   "new_metric": ("name", "why")}


@app.get("/api/proposals")
def list_proposals():
    require("console_read")
    return jsonify(ok=True, proposals=storage.proposals())


@app.post("/api/proposals")
def add_proposal():
    require("propose")
    body = request.get_json(silent=True) or {}
    by, kind = _who(body), body.get("kind")
    if kind not in PROPOSAL_KINDS:
        raise Refused("Choose change, new metric or retire.")
    metric = str(body.get("metric") or "").strip() or None
    if kind == "new_metric":
        if metric:
            raise Refused("A new metric has no metric id yet; leave the metric empty.")
    elif metric not in _published_ids()[1]:
        raise Refused("That metric isn't on the scorecard.")
    title = str(body.get("title") or "").strip()
    if not title:
        raise Refused("Give the proposal a title.")
    if len(title) > 200:
        raise Refused("The title is longer than 200 characters; please shorten it.")
    detail = body.get("detail")
    if not isinstance(detail, dict):
        raise Refused("The proposal's details are missing.")
    if len(json.dumps(detail)) > 20000:
        raise Refused("The details are longer than 20,000 characters; please shorten them.")
    for key in REQUIRED_DETAIL[kind]:
        if not isinstance(detail.get(key), str) or not detail[key].strip():
            raise Refused(f"Fill in '{key}' first.")
    if kind == "retire" and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", detail["effective"].strip()):
        raise Refused("The effective month must look like 2026-10.")
    p = storage.add_proposal({"kind": kind, "metric": metric, "title": title, "detail": detail, "by": by})
    storage.log("proposal", by, None, f"{PROPOSAL_KINDS[kind]} proposed: {title}",
                {"proposal_id": p["id"], "kind": kind, "metric": metric})
    return jsonify(ok=True, proposal=storage.proposal(p["id"]))


@app.post("/api/proposals/<int:pid>/decide")
def decide_proposal(pid):
    body = request.get_json(silent=True) or {}
    by, decision = _who(body), body.get("decision")
    reason = str(body.get("reason") or "").strip()
    if decision not in DECISIONS:
        raise Refused("Choose approved, returned, declined or withdrawn.")
    if decision in ("returned", "declined") and not reason:
        raise Refused("Say why, so the person who proposed it can see.")
    if len(reason) > 2000:
        raise Refused("The reason is longer than 2,000 characters; please shorten it.")
    p = storage.proposal(pid)
    if p is None:
        raise Refused("There is no such proposal.")
    # The Head of Tech Risk decides; Tech Risk may withdraw a proposal
    require("propose" if decision == "withdrawn" else "decide")
    if p["status"] != "open":
        raise Refused(f"This proposal was already {p['status']}.")
    d = storage.add_decision({"proposal_id": pid, "decision": decision, "reason": reason, "by": by})
    storage.log("decision", by, None, f"{p['title']}: {decision}",
                {"proposal_id": pid, "decision": decision, "decision_id": d["id"]})
    return jsonify(ok=True, proposal=storage.proposal(pid))


# ---- data contracts (owner, 4 Nov 2026): requested from the Data dictionary page, decided by Tech Risk ----

@app.get("/api/contracts")
def list_contracts():
    """Everyone sees the data dictionary, so everyone sees the contracts."""
    return jsonify(ok=True, contracts=storage.contracts())


@app.post("/api/contracts")
def add_contract():
    """Onboard a data source, or ask for a new version of one: anyone past the add-on can ask."""
    body = request.get_json(silent=True) or {}
    by = _who(body)
    feed = str(body.get("feed") or "").strip()
    if feed not in store.FEEDS:
        raise Refused("Choose which file this is from the list.")
    text = lambda k, n: str(body.get(k) or "").strip()[:n]
    provider, what = text("provider", 100), text("what", 2000)
    if not provider:
        raise Refused("Say which team sends the file.")
    if not what:
        raise Refused("Say what the file is, in a sentence or two.")
    cols = body.get("columns")
    if isinstance(cols, str):
        cols = [c.strip() for c in re.split(r"[,\n]", cols) if c.strip()]
    if not isinstance(cols, list) or not cols or not all(isinstance(c, str) for c in cols):
        raise Refused("List the columns TRUST may read, one per line or comma-separated.")
    cols = [c.strip()[:200] for c in cols if c.strip()][:200]
    metrics = body.get("metrics")
    if isinstance(metrics, str):
        metrics = [m.strip() for m in re.split(r"[,\s]+", metrics) if m.strip()]
    if not isinstance(metrics, list) or not metrics:
        raise Refused("Say which metrics the file is for (at least one).")
    known = {m["id"] for m in score_month.template()["metrics"]}
    bad = [m for m in metrics if m not in known]
    if bad:
        raise Refused(f"Not a metric on the scorecard: {', '.join(bad[:5])}.")
    if any(c["feed"] == feed and c["status"] == "draft" for c in storage.contracts()):
        raise Refused("A request for this file is already waiting for Tech Risk. Ask them to decide it first.")
    version = max([c["version"] for c in storage.contracts() if c["feed"] == feed], default=0) + 1
    c = storage.add_contract({"feed": feed, "version": version, "provider": provider, "contact": text("contact", 200),
                              "what": what, "cadence": text("cadence", 100), "columns": cols,
                              "metrics": sorted(set(metrics)), "note": text("note", 2000), "by": by})
    storage.log("contract", by, None, f"data contract requested: {feed} version {version}",
                {"contract_id": c["id"], "feed": feed, "version": version})
    return jsonify(ok=True, contract=c)


@app.post("/api/contracts/<int:cid>/decide")
def decide_contract(cid):
    body = request.get_json(silent=True) or {}
    by, decision = _who(body), body.get("decision")
    reason = str(body.get("reason") or "").strip()[:2000]
    if decision not in ("approved", "returned", "withdrawn"):
        raise Refused("Choose approved, returned or withdrawn.")
    if decision == "returned" and not reason:
        raise Refused("Say why, so the person who asked can see.")
    c = storage.contract(cid)
    if c is None:
        raise Refused("There is no such request.")
    # Tech Risk decides (formal = approved; owner, 4 Nov 2026). The person who asked may withdraw their own request.
    if not (decision == "withdrawn" and c["by"] == by):
        require("run_month")
    if c["status"] != "draft":
        raise Refused(f"This request was already {c['status']}.")
    out = storage.decide_contract(cid, decision, by, reason)
    storage.log("contract", by, None, f"data contract {c['feed']} version {c['version']}: {decision}",
                {"contract_id": cid, "feed": c["feed"], "version": c["version"], "decision": decision})
    return jsonify(ok=True, contract=out)


# ---- a family's items as a CSV file (owner, 3 Nov 2026) ----

@app.get("/api/items/<month>/<family>.csv")
def family_items_csv(month, family):
    require("download", family)
    store._check(store.FEEDS[0], month)
    scored = storage.load_month("scored", month)
    families = {f["id"]: f["name"] for f in (scored or {}).get("families", [])}
    if scored is None or family not in families:
        return Response("Nothing to download: that month or family isn't on the scorecard.", status=404,
                        mimetype="text/plain")
    rows = evidence.family_items(scored, family)
    body = evidence.to_csv(rows, month, families[family])
    by = _by(g.person) if not g.person["open"] else (" ".join((request.args.get("by") or "").split())[:100] or "name not given")
    storage.log("download", by, month, f"items for {family}", {"family": family, "rows": len(rows)})
    return Response(body, mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="trust-items-{family}-{month}.csv"'})
