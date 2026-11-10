"""Owner-editable settings (config/settings.json, or the file named by TRUST_SETTINGS), and the metric
definitions (config/metrics.json, or the file named by TRUST_METRICS).

Keys starting with _ are notes for people and are ignored. Used by upload (the HR file is cut down
to the CTO's line as it arrives) and by mapping.
"""
import os
import pathlib

from .intake.common import loads_tolerant


def settings():
    path = pathlib.Path(os.environ.get("TRUST_SETTINGS")
                        or pathlib.Path(__file__).resolve().parents[2] / "config" / "settings.json")
    try:
        doc = loads_tolerant(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        doc = {}
    out = {k: v for k, v in doc.items() if not k.startswith("_")}
    # A config var can stand in for the CTO's SAM_ACCOUNT (owner, 4 Nov 2026): the TEST environment sets
    # TRUST_HR_ROOT_SAM_ACCOUNT to the seed data's made-up CTO without editing the file.
    if os.environ.get("TRUST_HR_ROOT_SAM_ACCOUNT", "").strip():
        out["hr_root_sam_account"] = os.environ["TRUST_HR_ROOT_SAM_ACCOUNT"].strip()
    return out


def metrics_path():
    return pathlib.Path(os.environ.get("TRUST_METRICS")
                        or pathlib.Path(__file__).resolve().parents[2] / "config" / "metrics.json")


def metrics():
    """Every metric's definition (config/metrics.json, owner 8 Nov 2026): name, wording, dictionary card, known
    limits and how it is counted, in display order. Keys starting with _ are notes and are ignored."""
    doc = loads_tolerant(metrics_path().read_text(encoding="utf-8")) or {}
    return {k: v for k, v in (doc.get("metrics") or {}).items() if not k.startswith("_")}


def counting(mid):
    """The 'counting' part of one metric's definition ({} for a metric that isn't measured yet)."""
    return metrics().get(mid, {}).get("counting") or {}


def risks_dir():
    return pathlib.Path(os.environ.get("TRUST_RISKS")
                        or pathlib.Path(__file__).resolve().parents[2] / "config" / "risks")


RISK_FIELDS = ("domain", "category", "name", "description")


def _is_risk(d):
    return isinstance(d, dict) and any(k in d for k in RISK_FIELDS)


def _risks_in(stem, doc):
    """(risk id, risk) pairs in one file. A domain file (e.g. air.cyber.yaml) holds several risks (owner, 9 Nov
    2026), keyed by ID (air.cyber.01: {...}, or 01: {...} -> air.cyber.01), as a list (each with an id, else
    numbered air.cyber.01, .02 in order), or under a "risks" key; a file holding one risk is keyed by its own id,
    else by the file name."""
    if isinstance(doc, dict) and "risks" in doc and not _is_risk(doc):
        doc = doc["risks"]
    if _is_risk(doc):
        yield str(doc.get("id") or stem), doc
    elif isinstance(doc, dict):
        for k, v in doc.items():
            if _is_risk(v):
                k = str(v.get("id") or k)
                yield (k if k.startswith(stem + ".") or "." in k else f"{stem}.{k}"), v
    elif isinstance(doc, list):
        for i, v in enumerate(doc, start=1):
            if _is_risk(v):
                yield str(v.get("id") or f"{stem}.{i:02d}"), v


def risks():
    """The risk assessment engine's risks (owner, 9 Nov 2026): copies of its risk files in config/risks/ (one file
    per domain, e.g. air.cyber.yaml, with several risks inside), keyed by risk ID (air.cyber.01). Metrics link to
    them by ID in card.risks (config/metrics.json)."""
    import yaml                                          # pyyaml; only needed here
    out = {}
    folder = risks_dir()
    files = sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml")) if folder.exists() else []
    for f in files:
        for doc in yaml.safe_load_all(f.read_text(encoding="utf-8")):
            for rid, r in _risks_in(f.stem, doc):
                out[rid] = r
    return out


def data_sources():
    """Facts about each data source TRUST receives (config/data_sources.json, owner 9 Nov 2026): who owns it.
    Keyed by feed id; keys starting with _ are notes."""
    path = pathlib.Path(os.environ.get("TRUST_DATA_SOURCES")
                        or pathlib.Path(__file__).resolve().parents[2] / "config" / "data_sources.json")
    doc = loads_tolerant(path.read_text(encoding="utf-8")) or {} if path.exists() else {}
    return {k: {f: v for f, v in (x or {}).items() if not f.startswith("_")}
            for k, x in (doc.get("sources") or {}).items() if not k.startswith("_")}
