"""Read the ITDR application file on its own (feed "itdr"; layout from the owner, 3 Nov 2026).

The file is an Excel sheet (a CSV export of it works too) with a header that spans rows 1 and 2
(merged cells), then one row per application:

    Ref | Application Name | Business Product Area | Recovery Tier

    Ref: a number, the register's own id for the application. Rows without one, or with something
         that isn't a number, are set aside with the reason. A Ref on two rows: the first is kept.
    Application Name: free text, not always clean. Extra spaces, line breaks and non-breaking spaces
         are tidied; nothing else is changed.
    Business Product Area: not always filled in. Blank is kept as blank and counted.
    Recovery Tier: Tier 0 to Tier 5, or TBC. Tier 0 is the most critical, Tier 5 the least.
         Written loosely ("tier1", "T1", "1") it is still read; blank or anything else is kept as
         "Not given" and listed, never guessed.

The rows go into the itdr_application table at upload (storage.add_upload). Nothing here is
scored: RE-01 to RE-03 are still planned. Tier 0/1 = the critical applications for those metrics.
"""
import functools
import re

from .common import column_map, map_columns, read_table

FIELDS = {"Ref": ("Ref", "Ref No", "Reference", "ITDR Ref"),
          "Application Name": ("Application Name", "Application", "App Name"),
          "Business Product Area": ("Business Product Area", "Product Area", "Business Area"),
          "Recovery Tier": ("Recovery Tier", "Tier", "ITDR Tier")}
HEADER_ROWS = 2                       # the header is merged over rows 1 and 2
TIERS = range(0, 6)                   # Tier 0 (most critical) to Tier 5 (least)
TBC = "TBC"
NOT_GIVEN = "Not given"


def tidy(text):
    """Collapse runs of spaces, tabs, line breaks and non-breaking spaces into one space."""
    return re.sub(r"[\s ​]+", " ", str(text or "")).strip()


def tier_of(value):
    """'Tier 1', 'tier1', 'T1', '1' -> (1, 'Tier 1'); 'TBC'/'TBD'/'to be confirmed' -> (None, 'TBC');
    blank -> (None, 'Not given'); anything else -> (None, None) so the caller can say so."""
    v = tidy(value).lower()
    if not v:
        return None, NOT_GIVEN
    if v in ("tbc", "tbd", "to be confirmed", "to be determined", "tba"):
        return None, TBC
    m = re.fullmatch(r"(?:tier|t)?\s*[-_]?\s*(\d)(?:\.0)?", v)
    if m and int(m.group(1)) in TIERS:
        n = int(m.group(1))
        return n, f"Tier {n}"
    return None, None


def read(raw_bytes):
    """Returns dict(rows=[{ref, application_name, business_product_area, recovery_tier, tier_label}],
    set_aside, notes, summary)."""
    notes, set_aside, rows, seen = [], [], [], {}
    cmap = column_map("itdr", FIELDS)
    headers, table = read_table(raw_bytes, HEADER_ROWS, cmap)
    col = map_columns(headers, cmap, notes)
    g = lambda r, f: (r.get(col[f], "") if col[f] else "")
    first_row = 2                      # row numbers count in the kept file (one header row), like every feed

    tidied, odd_tiers, no_area, names = 0, {}, 0, {}
    for i, r in enumerate(table, start=first_row):
        ref_raw, name_raw = tidy(g(r, "Ref")), g(r, "Application Name")
        name = tidy(name_raw)
        if not ref_raw:
            set_aside.append(dict(row=i, reason="no Ref", application=name))
            continue
        if not re.fullmatch(r"\d+(\.0+)?", ref_raw):
            set_aside.append(dict(row=i, reason=f"Ref '{ref_raw}' is not a number", application=name))
            continue
        ref = int(float(ref_raw))
        if not name:
            set_aside.append(dict(row=i, reason="no Application Name", ref=ref))
            continue
        if ref in seen:
            notes.append(f"Ref {ref} is on more than one row ('{seen[ref]}' and '{name}'); the first is kept")
            set_aside.append(dict(row=i, reason=f"Ref {ref} repeated (first: '{seen[ref]}')", application=name))
            continue
        seen[ref] = name
        if name != str(name_raw).strip():
            tidied += 1
        tier, label = tier_of(g(r, "Recovery Tier"))
        if label is None:
            odd_tiers.setdefault(tidy(g(r, "Recovery Tier")), []).append(ref)
            label = NOT_GIVEN
        area = tidy(g(r, "Business Product Area"))
        if not area:
            no_area += 1
        names.setdefault(name.lower(), []).append(ref)
        rows.append({"ref": ref, "application_name": name, "business_product_area": area or None,
                     "recovery_tier": tier, "tier_label": label})

    if tidied:
        notes.append(f"{tidied} application {'name was' if tidied == 1 else 'names were'} tidied "
                     "(extra spaces or line breaks removed)")
    for raw, refs in odd_tiers.items():
        notes.append(f"Recovery Tier '{raw}' isn't Tier 0 to Tier 5 or TBC "
                     f"(Ref {', '.join(map(str, refs[:5]))}{'…' if len(refs) > 5 else ''}); kept as 'Not given'")
    blank = sum(1 for x in rows if x["tier_label"] == NOT_GIVEN) - sum(len(v) for v in odd_tiers.values())
    if blank:
        notes.append(f"{blank} {'application has' if blank == 1 else 'applications have'} no Recovery Tier; kept as 'Not given'")
    if no_area:
        notes.append(f"{no_area} {'application has' if no_area == 1 else 'applications have'} no Business Product Area")
    for refs in names.values():
        if len(refs) > 1:
            notes.append(f"The same application name is on Refs {', '.join(map(str, refs))}; each is kept as its own application")

    by_tier = {f"Tier {n}": 0 for n in TIERS}
    by_tier.update({TBC: 0, NOT_GIVEN: 0})
    for x in rows:
        by_tier[x["tier_label"]] += 1
    summary = dict(applications=len(rows), tier_0_1=by_tier["Tier 0"] + by_tier["Tier 1"], by_tier=by_tier,
                   no_business_product_area=no_area, set_aside=len(set_aside))
    return dict(rows=rows, set_aside=set_aside, notes=notes, summary=summary)


AREA_MATCH_MIN = 0.85          # default for the setting area_match_min
AREA_MATCH_CLOSE = 0.02        # two candidates this close, for different families, are too close to call


def name_similarity(a, b, floor=None):
    """How alike two names are, 0 to 1: the better of the whole-name score (common.similarity) and a
    word-by-word score. Word by word, each word is paired with its best match in the other name: the
    same word scores 1, a shortened word 0.9 ('Tech' for 'Technology', 3 letters or more), a near
    spelling its own similarity if 0.8 or more ('Bankng' for 'Banking'); the total is divided by the
    longer name's word count, so a missing or extra word lowers the score ('Payments' vs 'Payments
    Operations' = 0.5)."""
    from .common import similarity
    wa = re.findall(r"[a-z0-9]+", str(a or "").lower())
    wb = re.findall(r"[a-z0-9]+", str(b or "").lower())
    if not wa or not wb:
        return 0.0
    left, total = list(wb), 0.0
    for x in wa:
        if not left:
            break
        best, score = left[0], _word_score(x, left[0])      # first best wins a tie, as max() did
        for y in left[1:]:
            v = _word_score(x, y)
            if v > score:
                best, score = y, v
        total += score
        left.remove(best)
    words = total / max(len(wa), len(wb))
    if floor is not None and words < floor and _letters_bound(a, b) < floor:
        return words                     # can't reach floor either way: the caller drops it (speed only)
    return max(similarity(a, b), words)


def _letters_bound(a, b):
    """The most common.similarity(a, b) can be: 2 x letters shared / total length (same letters either way)."""
    from collections import Counter
    from .common import norm
    x, y = norm(a), norm(b)
    return 2 * sum((Counter(x) & Counter(y)).values()) / (len(x) + len(y)) if x or y else 1.0


@functools.lru_cache(maxsize=200_000)
def _word_score(x, y):
    """One word against another for name_similarity. Remembered: the same words come up again and again."""
    import difflib
    if x == y:
        return 1.0
    if min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)):
        return 0.9
    r = difflib.SequenceMatcher(None, x, y).ratio()
    return r if r >= 0.8 else 0.0


def area_match_min(settings):
    """The fuzzy-match confidence for Business Product Area (setting area_match_min, 0.5 to 1; default 0.85)."""
    v = (settings or {}).get("area_match_min", AREA_MATCH_MIN)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.5 <= v <= 1 else AREA_MATCH_MIN


def department_families(people):
    """{department name: (family_id or None, note)} from HR's Department column (owner, 3 Nov 2026).

    A department's family is the one most of its placed people are in. A tie gives no family, with a note.
    people: HR rows with department and family_id (set by mapping).
    """
    from collections import Counter
    from .common import norm
    counts, names = {}, {}
    for p in people:
        dept = tidy(p.get("department"))
        fam = p.get("family_id")
        if not dept or not fam or fam == "UNATTRIBUTED":
            continue
        names.setdefault(norm(dept), dept)
        counts.setdefault(norm(dept), Counter())[fam] += 1
    out = {}
    for key, c in counts.items():
        top = c.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            tied = sorted(f for f, n in top if n == top[0][1])
            out[names[key]] = (None, f"department '{names[key]}' has as many people in {', '.join(tied)}")
        else:
            out[names[key]] = (top[0][0], None)
    return out


def match_families(apps, family_rows, people=None, min_score=AREA_MATCH_MIN):
    """Place each application with a family by its Business Product Area (owner, 3 Nov 2026).

    Candidates: each family's name (owners file) and each HR Department (its family = the family most
    of its people are in). The area is compared ignoring case, spaces, punctuation and word order, and
    allowing shortened and misspelt words (name_similarity):
      1. an exact match wins (a family name before a department);
      2. otherwise the closest candidate scoring at least min_score (setting area_match_min) is used,
         and listed with its score so it can be checked;
      3. two candidates for different families within 0.02 of each other: too close to call, listed;
      4. a department whose people are split evenly between families: listed, no family.
    Sets app["family_id"] (None when not placed) and app["family_match"] = {how, matched, score}.
    """
    from .common import norm
    similarity = name_similarity
    cands = [(f["family"], f["family_id"], "family name", None) for f in family_rows]
    cands += [(d, fid, "department", why) for d, (fid, why) in department_families(people or []).items()]
    exact_of = {}                  # tidied name -> first candidate with it (a family name before a department)
    for c in cands:
        exact_of.setdefault(norm(c[0]), c)
    placed, blank, unknown, notes_by, fuzzy, seen = 0, 0, {}, {}, [], {}
    for a in apps:
        area = a.get("business_product_area")
        a["family_id"], a["family_match"] = None, None
        if not area:
            blank += 1
            continue
        exact = exact_of.get(norm(area))
        if exact:
            name, fid, kind, why = exact
            a["family_match"] = {"how": f"exact {kind}", "matched": name, "score": 1.0}
        else:
            if area not in seen:      # many applications share an area: score it once (speed only, owner 4 Nov 2026)
                f = min_score - 0.001        # below this, even rounded, it can't reach min_score
                ranked = sorted(((round(similarity(area, c[0], f), 3), c) for c in cands), key=lambda x: -x[0])
                seen[area] = [x for x in ranked if x[0] >= min_score]
            scored = seen[area]
            if not scored:
                unknown.setdefault(area, []).append(a["ref"])
                continue
            best, (name, fid, kind, why) = scored[0]
            rival = next((x for x in scored[1:] if x[1][1] != fid), None)
            if rival and best - rival[0] <= AREA_MATCH_CLOSE:
                notes_by.setdefault(f"'{area}' is about as close to {kind} '{name}' ({best:.2f}) as to "
                                    f"{rival[1][2]} '{rival[1][0]}' ({rival[0]:.2f}); no family chosen", []).append(a["ref"])
                continue
            a["family_match"] = {"how": f"fuzzy {kind}", "matched": name, "score": best}
            fuzzy.append(f"'{area}' → {kind} '{name}' ({best:.2f})")
        if fid:
            a["family_id"] = fid
            placed += 1
        else:
            notes_by.setdefault(f"'{area}' matches {why}; no family chosen", []).append(a["ref"])
    refs = lambda v: f"Ref {', '.join(map(str, v[:5]))}{'…' if len(v) > 5 else ''}"
    notes = []
    if blank:
        notes.append(f"{blank} {'application has' if blank == 1 else 'applications have'} no Business Product Area, "
                     "so no family yet")
    if fuzzy:
        uniq = list(dict.fromkeys(fuzzy))
        notes.append(f"{len(uniq)} Business Product {'Area was' if len(uniq) == 1 else 'Areas were'} matched by a close "
                     f"spelling (confidence at least {min_score:.2f}); please check: {'; '.join(uniq[:8])}"
                     f"{'…' if len(uniq) > 8 else ''}")
    for note, v in notes_by.items():
        notes.append(f"{note} ({refs(v)})")
    if unknown:
        shown = "; ".join(f"'{k}' ({refs(v)})" for k, v in list(unknown.items())[:8])
        n = sum(len(v) for v in unknown.values())
        notes.append(f"{n} {'application has' if n == 1 else 'applications have'} a Business Product Area that "
                     f"isn't close enough to a family name or an HR department: {shown}{'…' if len(unknown) > 8 else ''}")
    by = lambda how: sum(1 for x in apps if (x.get("family_match") or {}).get("how") == how and x["family_id"])
    return dict(placed=placed, not_placed=len(apps) - placed,
                exact=by("exact family name") + by("exact department"),
                fuzzy=by("fuzzy family name") + by("fuzzy department"),
                by_family_name=by("exact family name") + by("fuzzy family name"),
                by_department=by("exact department") + by("fuzzy department"), notes=notes)
