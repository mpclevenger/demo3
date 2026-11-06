"""Owner-editable settings (config/settings.json, or the file named by TRUST_SETTINGS).

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
