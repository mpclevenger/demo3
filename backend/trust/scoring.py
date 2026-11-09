"""Building-block and TRUST scores from metric statuses. The list of blocks comes from the page's data block
(`blocks`; each metric names its `block`), so adding a block is a data edit, not a code change.

Rules (docs/wiki/scoring-rules.md):
  - Points: Green 100, Amber 50, Red 0.
  - A block is the plain average of its scored metrics (owner, 9 Nov 2026: no weights),
    rounded to a whole number, half up (Decimal, ROUND_HALF_UP, D-04).
  - 'Info only' and 'Not Tier 0/1' are not applicable. 'DNR' (data not received) is left out
    and counted as missing (D-76). Other non-scored statuses ('N/A', 'Low confidence', ...)
    count as applicable but not scored.
  - A block needs at least `block_min_share` of the metrics that arrived to be scored (and always at least one),
    else 'Insufficient data'. Setting `coverage` in config/thresholds.json; 0 = any one scored metric (owner, 4 Nov 2026).
  - Caps (D-28, O-15): an automatic Red rule (metric override=True and Red) caps the block at 49;
    any Red metric caps the block at 79; any Red block caps the family TRUST at 79.
  - Family TRUST = average of the blocks' (capped) means, half up; needs at least `trust_min_blocks` scored blocks
    (setting `coverage`; 1 = any scored block, owner 4 Nov 2026).
  - Firm TRUST = the firm-wide metric results scored the same way (owner, 4 Nov 2026), see score_month.
  - Bands: 80+ Green, 50-79 Amber, below 50 Red.
"""
from decimal import Decimal as D, ROUND_HALF_UP

# The blocks as the page's data block lists them (code, name, question, provider, risk_category). Kept here as the
# default so the scorer works without a template; score_month passes the template's list.
BLOCKS = ['SEC', 'RES', 'STA', 'REL', 'ACC', 'MOD']
PTS = {'Green': 100, 'Amber': 50, 'Red': 0}
SC = set(PTS)                               # statuses that carry points
NOT_APPLICABLE = ('Info only', 'Not Tier 0/1', 'Coming soon')   # 'Coming soon': no source yet (owner, 2 Nov 2026)
# The caps are settings (owner, 3 Nov 2026): config/thresholds.json "caps" overrides these defaults.
CAPS = {'automatic_red_block': 49, 'red_metric_block': 79, 'red_block_trust': 79}


# How much has to be measured before a block or TRUST is scored. Defaults = the original rules (half the
# arrived metrics; 3 blocks). config/thresholds.json "coverage" overrides them (owner, 4 Nov 2026: any metric, any block).
COVERAGE = {'block_min_share': 0.5, 'trust_min_blocks': 3}
def coverage_from(cfg=None, blocks=None):
    """The coverage rules to use: the defaults, with any valid values given in cfg (a dict) in their place."""
    out = dict(COVERAGE)
    cfg = cfg or {}
    v = cfg.get('block_min_share')
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1:
        out['block_min_share'] = v
    v = cfg.get('trust_min_blocks')
    if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= len(blocks or BLOCKS):
        out['trust_min_blocks'] = v
    return out


def caps_from(cfg=None):
    """The caps to use: the defaults, with any whole numbers given in cfg (a dict) in their place."""
    out = dict(CAPS)
    for k, v in (cfg or {}).items():
        if k in out and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100:
            out[k] = v
    return out


def block_codes(metrics):
    """The block codes in use, in the order the metric list first names them (the template's order)."""
    seen = []
    for m in metrics:
        b = m.get('block')
        if b and b not in seen:
            seen.append(b)
    return seen or list(BLOCKS)


def q(x):
    """Round to a whole number, half up (D-04)."""
    return int(D(x).quantize(D(1), rounding=ROUND_HALF_UP))


def band(s):
    """Score band: 80+ Green, 50-79 Amber, below 50 Red."""
    return 'Green' if s >= 80 else 'Amber' if s >= 50 else 'Red'


def block(ms, caps=None, coverage=None):
    """Score one block. ms: list of (metric_id, metric_result). Returns (block_dict, mean or None)."""
    app = [(k, m) for k, m in ms if m['status'] not in NOT_APPLICABLE]
    miss = sum(1 for k, m in app if m['status'] == 'DNR')      # D-76: not received -> left out, flagged "x of y metrics"
    rec = [(k, m) for k, m in app if m['status'] != 'DNR']
    sc = [(k, m) for k, m in rec if m['status'] in SC]
    red = sum(1 for k, m in ms if m['status'] == 'Red')
    prov = any(m.get('provisional') for k, m in ms)
    base = dict(scored=len(sc), applicable=len(app), missing=miss, red_count=red, provisional=prov, capped=False)

    if not app:                              # nothing applicable at all
        st = 'Not Tier 0/1' if any(m['status'] == 'Not Tier 0/1' for k, m in ms) else 'N/A'
        return dict(base, score=None, status=st, scored=0, applicable=0), None
    if not rec:                              # everything applicable is missing
        return dict(base, score=None, status='DNR', scored=0), None
    share = D(str(coverage_from(coverage)['block_min_share']))
    if not sc or D(len(sc)) / D(len(rec)) < share:  # coverage counted on what arrived (D-76)
        return dict(base, score=None, status='Insufficient data'), None

    mean = D(sum(PTS[m['status']] for k, m in sc)) / D(len(sc))
    s = q(mean)
    cap, c = False, caps_from(caps)
    a, r = c['automatic_red_block'], c['red_metric_block']
    if any(m.get('override') and m['status'] == 'Red' for k, m in sc) and s > a:    # automatic Red rule
        s, mean, cap = a, D(a), True
    if any(m['status'] == 'Red' for k, m in sc) and s > r:                          # any Red metric (O-15)
        s, mean, cap = r, D(r), True
    return dict(base, score=s, status=band(s), capped=cap), mean


def family(fr, metrics, caps=None, coverage=None):
    """Score one family-month (or the firm, from its pooled results). fr: {'metrics': {id: result}}; metrics: the
    template's metric list, each with its 'block'.

    Returns (blocks dict, trust or None, status, capped).
    """
    out = {}
    means = []
    codes = block_codes(metrics)
    for B in codes:
        ms = [(m['id'], fr['metrics'][m['id']]) for m in metrics
              if m.get('block') == B and m['id'] in fr['metrics']]
        r, mn = block(ms, caps, coverage)
        out[B] = r
        if mn is not None:
            means.append(mn)
    if len(means) < coverage_from(coverage, codes)['trust_min_blocks']:
        return out, None, 'Insufficient data', False
    t = q(sum(means, D(0)) / len(means))
    cap = False
    tc = caps_from(caps)['red_block_trust']
    if any(r['status'] == 'Red' for r in out.values()) and t > tc:
        t, cap = tc, True
    return out, t, band(t), cap


def average_trust(trusts):
    """Average of the TRUST scores that exist, half up (the old firm rule; kept for the page's comparison line)."""
    ts = [t for t in trusts if t is not None]
    return q(D(sum(ts)) / len(ts)) if ts else None
