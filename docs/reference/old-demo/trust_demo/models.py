"""Shared data structures for the TRUST demo. Do not edit without updating CONTRACT.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

LETTER_ORDER = ["TR", "RE", "UN", "SE", "TE"]


@dataclass(frozen=True)
class Family:
    id: str
    name: str
    band: str                 # "product" | "platform"
    tier01: bool              # owns Tier 0/1 apps
    client_facing: bool
    leads: tuple[str, ...]


@dataclass(frozen=True)
class Team:
    manager_id: str           # e.g. "M1001"
    family_id: str
    name: str                 # e.g. "Mgr 1001 org"


@dataclass(frozen=True)
class Letter:
    code: str                 # TR RE UN SE TE
    name: str                 # Traceable ...
    question: str
    provider: str


@dataclass(frozen=True)
class Metric:
    id: str                   # e.g. "SE-01"
    letter: str               # letter code
    name: str
    provider: str             # Arch, ITDR, Ops, Cyber, Hosting platform, Change
    source_system: str
    unit: str                 # "%" | "per 10 apps" | "per 100 releases"
    scale: Decimal            # 100 | 10 | 100
    higher_is_better: Optional[bool]   # None for info-only
    scored: bool
    zero_rule: str            # "NA" | "BEST"
    min_pop: int
    numerator_label: str
    denominator_label: str
    definition: str
    rolling_months: int = 1
    override_rule: Optional[str] = None   # "critical_secret" | "t01_internet_eol"
    peer_flag_gap: Optional[Decimal] = None
    tier01_only: bool = False
    framework: str = ""       # e.g. "NIST CSF 2.0 ID.AM-02"


@dataclass(frozen=True)
class ToleranceThreshold:
    metric_id: str
    version: int
    green_tolerance: Decimal
    red_limit: Decimal
    effective_from: str       # period id "YYYY-MM"
    effective_to: Optional[str]
    approved_by: str
    approved_at: str          # ISO date
    approval_ref: str
    reason: str
    basis: str                # "Policy" | "Calibrated" | "Placeholder"


@dataclass(frozen=True)
class TeamObservation:
    period_id: str
    manager_id: str           # or "UNATTRIBUTED"
    metric_id: str
    numerator: Decimal
    denominator: Decimal
    submission_id: str
    coverage_confirmed: bool = True
    critical_overdue: int = 0
    t01_internet_eol: int = 0


@dataclass(frozen=True)
class ValidationResult:
    rule: str
    severity: str             # "FAIL" | "WARN"
    passed: bool
    detail: str


@dataclass(frozen=True)
class Connector:
    id: str
    source_system: str
    provider: str
    method: str               # "Upload" | "Feed" | "Pull"
    contract_version: str
    schedule: str
    metrics: tuple[str, ...]


@dataclass
class Submission:
    id: str
    period_id: str
    provider: str
    connector_id: str
    status: str               # "Accepted" | "Superseded" | "Rejected" | "DNR" | "Late"
    received_bd: Optional[int]
    as_of: Optional[str]
    row_count: int
    file_sha256: Optional[str]
    uploaded_by: Optional[str]
    contract_version: str
    firm_total_num: Optional[Decimal]
    source_total_num: Optional[Decimal]
    supersedes: Optional[str] = None
    validation: list[ValidationResult] = field(default_factory=list)


@dataclass
class Period:
    id: str                   # "YYYY-MM"
    label: str                # "January 2027"
    status: str               # "Locked" | "Preview" | "Open"
    current_bd: Optional[int]
    locked_by: Optional[str] = None
    locked_at: Optional[str] = None
    calc_run_id: Optional[str] = None
    code_sha: Optional[str] = None
    checklist_done: int = 0
    checklist_total: int = 9
    pre_read_sha256: Optional[str] = None


@dataclass
class Entry:
    """Note, action, data query or accepted risk."""
    id: str
    period_id: str
    family_id: str
    metric_id: Optional[str]
    kind: str                 # "Note" | "Action" | "Data query" | "Accepted risk"
    text: str
    owner: str
    status: str               # Open | In progress | Done | Upheld | Rejected | Disputed | Approved
    due: Optional[str] = None
    created_by: str = "Tech Risk"
    created: str = ""


@dataclass
class AuditEvent:
    at: str
    actor: str
    action: str
    detail: str


@dataclass
class Store:
    families: list[Family]
    teams: list[Team]
    letters: list[Letter]
    metrics: list[Metric]
    thresholds: list[ToleranceThreshold]
    periods: list[Period]                 # chronological
    observations: list[TeamObservation]
    submissions: list[Submission]
    connectors: list[Connector]
    entries: list[Entry]
    unattributed_pct: dict[tuple[str, str], Decimal]   # (period_id, provider) -> %
    dnr: set[tuple[str, str]]                          # (period_id, provider) not received
    audit: list[AuditEvent] = field(default_factory=list)

    def family(self, fid: str) -> Family:
        return next(f for f in self.families if f.id == fid)

    def metric(self, mid: str) -> Metric:
        return next(m for m in self.metrics if m.id == mid)

    def period(self, pid: str) -> Period:
        return next(p for p in self.periods if p.id == pid)


# ---------- engine outputs ----------

@dataclass
class MetricResult:
    period_id: str
    family_id: str
    metric_id: str
    value: Optional[Decimal]          # 1-dp display value
    numerator: Optional[Decimal]
    denominator: Optional[Decimal]
    status: str
    points: Optional[int]
    reason: str
    provisional: bool = False
    carried_from: Optional[str] = None
    override: bool = False
    behind_peers: bool = False
    typical: Optional[Decimal] = None
    threshold_version: Optional[int] = None


@dataclass
class LetterResult:
    family_id: str
    letter: str
    score: Optional[int]
    status: str
    scored: int
    applicable: int
    red_count: int
    provisional: bool
    capped: bool


@dataclass
class FamilyResult:
    family_id: str
    trust: Optional[int]
    status: str
    delta: Optional[int]
    capped: bool
    letters: dict[str, LetterResult]
    metrics: dict[str, MetricResult]
    letter_deltas: dict[str, Optional[int]] = field(default_factory=dict)


@dataclass
class WatchItem:
    priority: int
    kind: str          # "Override red" | "New red" | "Chronic red" | "Sharp drop" | "Overdue action" | "Behind peers" | "Data quality"
    family_id: Optional[str]
    metric_id: Optional[str]
    text: str


@dataclass
class PeriodScorecard:
    period_id: str
    families: dict[str, FamilyResult]
    firm_trust: Optional[int]
    firm_trust_delta: Optional[int]
    firm_totals: dict[str, Optional[Decimal]]
    watch_list: list[WatchItem]
    most_improved: Optional[tuple[str, int]]
    thresholds_used: dict[str, int]          # metric_id -> threshold version
    prior: Optional["PeriodScorecard"] = None
