"""Why does a family score the way it does? Prints, for one month and one family, where its rows came from.

    python tools/why_family.py 2026-11 payments

Shows: the family's leads and people, whether a lead of several families is involved (a shared group), how
many rows of each file were placed with the family (and with its shared group), each metric's counts before
and after the shared group is added, the scored result for each metric with its reason, and the coverage
settings that decide whether a building block and TRUST get a score. Reads only; changes nothing.
Run it from the repo root after Update the scorecard (or map + score) for the month.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import measure, score_month, storage  # noqa: E402


def main(month, fid):
    mapped = storage.load_month("mapped", month)
    if not mapped:
        sys.exit(f"{month} hasn't been mapped yet: press Update the scorecard (or run python manage.py map {month}).")
    feeds = mapped["feeds"]
    hm = feeds.get("hr_mapping") or {}
    fam = next((f for f in hm.get("families") or [] if f.get("family_id") == fid), None)
    known = [f.get("family_id") for f in hm.get("families") or []]
    if not fam:
        sys.exit(f"No family '{fid}' in the owners file for {month}. Family ids: {', '.join(known)}")
    shared = hm.get("shared")
    groups = [g for g, fs in (shared or {}).items() if fid in fs]
    keys = [fid] + groups
    print(f"== {fam.get('family')} ({fid}), {month}")
    info = storage.run_info("mapped", month) or {}
    now_sha = storage.git_sha() or ""
    print(f"last mapped: {info.get('at', '?')} by {info.get('by', '?')} | code that mapped it: "
          f"{(info.get('git_sha') or '')[:10] or 'not recorded'} | code running now: {now_sha[:10] or 'not recorded'}"
          f" | database: {'yes' if storage.using_database() else 'NO (reading the local store folder)'}")
    from trust import config, linking
    st = config.settings()
    print(f"settings: team_grouping = {linking.grouping(st)} | hr_root_sam_account set: {bool(st.get('hr_root_sam_account'))}"
          f" | hr_mapping keys saved: {sorted(hm)}")
    ups = [e for e in storage.events(month, 400) if str(e.get("action", "")).startswith("update ")][:6]
    if ups:
        print("recent Update attempts (newest first):")
        for e in ups:
            print(f"   {e['at'][:19]}  {e['action']}  {str(e.get('note') or '')[:160]}")
        if ups[0]["action"] != "update finished":
            print("   -> the newest Update didn't finish, so the month still shows an earlier result. "
                  f"Run python manage.py map {month} in the shell to see the error.")
    print(f"leads: {', '.join(fam.get('owner_emails') or [])} | people placed: {fam.get('people')}")
    if shared is None:
        why = ("team_grouping is l3, so the owners file isn't used and there are no shared leads"
               if linking.grouping(st) == "l3" else
               "the saved result has no 'shared' list. Code from 6 Nov onwards always writes one, so this result was "
               "made by older code: compare the two code versions above")
        print(f"shared groups: not recorded ({why})")
    else:
        print(f"shared groups for this family: {groups or 'none'}" + (f" -> {[shared[g] for g in groups]}" if groups else ""))
    ppl = feeds.get("hr", {}).get("people") or []
    if ppl and not any("family_id" in p for p in ppl):
        print("HR people: no family recorded on them: this month was mapped before families were placed, or with older "
              f"code. Run python manage.py map {month}.")
    print(f"HR people with this family's key: {sum(1 for p in ppl if p.get('family_id') == fid)}"
          + "".join(f" | in group {g}: {sum(1 for p in ppl if p.get('family_id') == g)}" for g in groups))
    print("\n-- rows placed per file (this family / its shared group(s) / not yet mapped / whole file)")
    for name, f in sorted(feeds.items()):
        rows = f.get("rows")
        if not isinstance(rows, list) or not rows or not any(isinstance(r, dict) and "family_id" in r for r in rows[:500]):
            continue
        c = lambda k: sum(1 for r in rows if r.get("family_id") == k)
        print(f"{name:20} {c(fid):6} / {sum(c(g) for g in groups):6} / {c('UNATTRIBUTED'):6} / {len(rows):6}")
    meas = measure.measure(mapped)
    fc = score_month.expand_shared(meas["counts"], shared or {})
    print("\n-- counts per metric: numerator / denominator (own key + group -> after the group is added)")
    for mid in sorted(meas["counts"]):
        raw = meas["counts"][mid]
        own, grp, after = raw.get(fid) or {}, [raw.get(g) or {} for g in groups], fc[mid].get(fid) or {}
        nd = lambda c: f"{c.get('numerator', 0)}/{c.get('denominator', '-')}"
        print(f"{mid:6} own {nd(own):>10}  group {' + '.join(nd(x) for x in grp) or '-':>10}  -> {nd(after):>10}"
              f"   {'received' if mid in meas['received'] else 'file not received'}")
    sc = storage.load_month("scored", month)
    fr = ((sc or {}).get("period") or {}).get("families", {}).get(fid)
    if not fr:
        print(f"\nNot scored yet: run python manage.py score {month}")
        return
    print(f"\n-- scored: TRUST {fr.get('trust')} ({fr.get('status')}); blocks: "
          + ", ".join(f"{b} {x.get('score')}" for b, x in fr["blocks"].items()))
    for mid, r in sorted(fr["metrics"].items()):
        print(f"{mid:6} {str(r.get('status')):14} value {r.get('value')}  | {r.get('reason') or ''}"[:220])
    cfg = score_month.thresholds_config()
    cov = (sc["period"].get("coverage") or cfg.get("coverage") or {})
    print(f"\ncoverage used: {cov or 'code defaults (a block needs half its metrics, TRUST needs 3 blocks)'}"
          f" | switched on: {cfg.get('switched_on')}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
