"""Which product family owners file is TRUST using for a month? Reads only; changes nothing.

    python tools/why_owners.py 2026-11

Lists every upload of the owners file (feed hr_mapping) for the month, oldest first, shows the families and
lead emails in the newest one (the one TRUST uses), compares them with what the last Update of the month used,
and says which other months have an owners file. Every month stands alone: a file uploaded for October
isn't used for November.
"""
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from trust import storage  # noqa: E402
from trust.intake import families  # noqa: E402


def main(month):
    reg = storage.register(month, "hr_mapping")
    others = [m for m in storage.upload_months() if m != month and storage.register(m, "hr_mapping")]
    print(f"== Product family owners file for {month}")
    if not reg:
        print("No owners file uploaded for this month." + (f" Months that have one: {', '.join(others)}" if others else ""))
        print("Upload it on Data sources with this month selected, then press Update the scorecard.")
        return
    for i, e in enumerate(reg, 1):
        print(f"{i}. {e.get('uploaded_at')}  {e.get('original_name')}  by {e.get('uploaded_by')}  "
              f"sha {str(e.get('original_sha256') or e.get('sha256'))[:12]}" + ("   <- newest: this one is used" if i == len(reg) else ""))
    newest = reg[-1]
    raw = storage.kept_file(month, "hr_mapping", newest)
    if raw is None:
        sys.exit("The newest upload's kept file can't be found.")
    got = families.read(raw)
    file_owners = {r["family"]: sorted(r["owner_emails"]) for r in got["rows"]}
    print(f"\n-- in the newest file: {len(file_owners)} families")
    for fam, em in sorted(file_owners.items()):
        print(f"   {fam}: {', '.join(em) or '(no lead email)'}")
    for n in got["notes"]:
        print(f"   note: {n}")
    mapped = storage.load_month("mapped", month)
    info = storage.run_info("mapped", month) or {}
    if not mapped:
        print("\nThe month hasn't been updated yet: press Update the scorecard.")
        return
    used = {f["family"]: sorted(f.get("owner_emails") or []) for f in (mapped["feeds"].get("hr_mapping") or {}).get("families") or []}
    when = info.get("at") or info.get("created_at") or "?"
    print(f"\n-- used by the last Update ({when}): {len(used)} families")
    diff = [f for f in sorted(set(file_owners) | set(used)) if file_owners.get(f) != used.get(f)]
    if not diff:
        print("   Same as the newest file.")
    for f in diff:
        print(f"   {f}: file {file_owners.get(f, '(not in file)')}  |  last Update {used.get(f, '(not used)')}")
    def t(x):
        try:
            return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
        except ValueError:
            return None
    up, ran = t(newest.get("uploaded_at")), t(when)
    if diff or (up and ran and up > ran):
        print("\nThe newest file is newer than the last Update: press Update the scorecard for this month.")
    if others:
        print(f"\nOther months with an owners file: {', '.join(others)} (each month uses only its own)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
