"""Command line for the TRUST steps. Run from the repo folder:

    python -m trust upload FEED FILE --month 2026-10 --by "Your Name" [--link URL]   # step 1: keep the file
    python -m trust map 2026-10                                                     # step 2: read and place (re-run any time)
    python -m trust score 2026-10                                                   # step 3: count, judge, score
    python -m trust publish                                                         # step 4: data.json + page for the front end
    python -m trust calibrate 2026-07 2026-08 ... [--write --by "Name"]            # set tolerance thresholds from pooled months
    python -m trust migrate                                                         # set up the database tables (each deploy)
    python -m trust retention [--write]                                             # remove months older than 24 months and old runs

(From the top of the repo: python manage.py ..., which needs no PYTHONPATH; or PYTHONPATH=backend python -m trust ...)
"""
import argparse
import json
import pathlib
import sys

from . import calibrate, lock as locking, mapping, migrate, publish, score_month, storage, store


def main(argv=None):
    p = argparse.ArgumentParser(prog="trust", description="TRUST: upload, then map, then score.")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("upload", help="Step 1: keep a provider file for a month (nothing is read yet).")
    u.add_argument("feed", choices=store.FEEDS)
    u.add_argument("file")
    u.add_argument("--month", required=True)
    u.add_argument("--by", required=True, help="who is uploading")
    u.add_argument("--link", help="SharePoint link to the original")
    m = sub.add_parser("map", help="Step 2: read every kept file for a month and place rows with families.")
    m.add_argument("month")
    m.add_argument("--by", default="command line", help="who is running it (recorded)")
    s = sub.add_parser("score", help="Step 3: count each metric per family, judge it, score building blocks and TRUST.")
    s.add_argument("month")
    s.add_argument("--by", default="command line", help="who is running it (recorded)")
    pb = sub.add_parser("publish", help="Step 4: put every scored month into data.json and the front-end page.")
    pb.add_argument("--by", default="command line", help="who is running it (recorded)")
    lk = sub.add_parser("lock", help="Lock a month: seal it and refuse further changes.")
    lk.add_argument("month")
    lk.add_argument("--by", required=True, help="who is locking it")
    ro = sub.add_parser("reopen", help="Reopen a locked month, with a reason.")
    ro.add_argument("month")
    ro.add_argument("--by", required=True, help="who is reopening it")
    ro.add_argument("--reason", required=True, help="why (kept in the record)")
    cb = sub.add_parser("calibrate", help="Work out tolerance thresholds from several scored months pooled together.")
    cb.add_argument("months", nargs="+", help="scored months, e.g. 2026-07 2026-08 2026-09 2026-10")
    cb.add_argument("--write", action="store_true", help="freeze the result into config/thresholds.json")
    cb.add_argument("--by", help="who approves the thresholds (needed with --write)")
    sub.add_parser("migrate", help="Set up or update the database tables (needs DATABASE_URL).")
    rt = sub.add_parser("retention", help="Remove months older than 24 months and old result runs (dry run unless --write).")
    rt.add_argument("--write", action="store_true", help="really remove it (a dry run only lists what would go)")
    rt.add_argument("--months", type=int, default=24, help="how many months to keep, counting the current one (24)")
    rt.add_argument("--grace-days", type=int, default=30, help="old runs younger than this stay (30)")
    rt.add_argument("--by", default="Scheduler", help="who ran it, for the activity log")
    a = p.parse_args(argv)

    try:
        if a.cmd == "upload":
            path = pathlib.Path(a.file)
            e = store.upload(a.feed, a.month, path.read_bytes(), path.name, a.by, a.link)
            print(f"{a.feed} {a.month}: {e['note']} ({e['size_bytes']} bytes, sha256 {e['sha256'][:12]}…)")
            for w in (e.get("checks") or {}).get("warnings", []):
                print(f"  to look at: {w}")
            print(f"Next: python -m trust map {a.month}")
        elif a.cmd == "score":
            r = score_month.run(a.month, a.by)["period"]
            print(f"{r['meta']['label']}: firm TRUST {r['firm_trust'] if r['firm_trust'] is not None else 'not scored'}")
            for fid, fr in r["families"].items():
                print(f"  {fid}: TRUST {fr['trust'] if fr['trust'] is not None else 'not scored'} ({fr['status']})")
            if r["dnr"]:
                print(f"No data from: {', '.join(r['dnr'])}")
            print(f"Next: python -m trust publish")
        elif a.cmd == "publish":
            out = publish.run(a.by)
            if out == "database":
                print("Published to the database: the website shows it now.")
            else:
                print(f"Written: {out / 'data.json'} and {out / 'index.html'}")
                print(f"To view: cd {out} && python -m http.server 8000, then open http://localhost:8000")
        elif a.cmd == "lock":
            st = locking.lock(a.month, a.by)
            print(f"{a.month} locked by {st['locked_by']} at {st['locked_at']}; the scorecard was published again.")
        elif a.cmd == "reopen":
            locking.reopen(a.month, a.by, a.reason)
            print(f"{a.month} reopened; the reason is in the record.")
        elif a.cmd == "calibrate":
            rows = calibrate.calibrate(a.months)
            print(f"{'Metric':8}{'Family results':>15}{'Green tolerance':>17}{'Red limit':>11}{'Amber band':>12}")
            for r in rows:
                if r["ok"]:
                    print(f"{r['metric']:8}{r['values_used']:>15}{r['green']:>17g}{r['red']:>11g}{r['band']:>12g}")
                else:
                    print(f"{r['metric']:8}{r['values_used']:>15}  not set: {r['why']}")
            if not a.write:
                print("\nNothing was changed. To freeze these as fixed tolerance thresholds, run the same command with "
                      "--write --by \"Your Name\".")
            else:
                if not a.by:
                    raise ValueError("--write needs --by \"Your Name\" (who approves the thresholds)")
                path = calibrate.write(rows, a.months, a.by)
                done = [r["metric"] for r in rows if r["ok"]]
                print(f"\nSet in {path}: {', '.join(done) if done else 'nothing (no metric had enough results)'}.")
                print("Next: deploy, then update the scorecard for each open month. Locked months keep their sealed figures.")
        elif a.cmd == "retention":
            from . import retention
            retention.run(write=a.write, by=a.by, keep_months=a.months, grace_days=a.grace_days)
        elif a.cmd == "migrate":
            done = migrate.run()
            print(f"Database tables up to date ({'ran ' + ', '.join(done) if done else 'nothing new to run'}).")
        else:
            r = mapping.map_month(a.month, a.by)
            for feed, v in r["feeds"].items():
                if v["status"] == "not received":
                    continue
                print(f"\n{feed}: {v['status']}  {json.dumps(v.get('summary', {}))}")
                for n in v.get("notes", []):
                    print(f"  - {n}")
            for n in r["notes"]:
                print(f"\nNote: {n}")
            print(f"\nSaved: {'the database' if storage.using_database() else store.store_dir() / 'mapped' / (a.month + '.json')}")
            print(f"Next: python -m trust score {a.month}")
    except ValueError as err:
        print(f"Not done: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
