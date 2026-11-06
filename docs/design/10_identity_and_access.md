# TRUST Scorecard — 10 Identity and Access (draft for owner review)

> **Superseded in part, 2 Nov 2026 (owner): access is NOT Entra.** The company's add-on container in front of TRUST handles who can get in; TRUST has **no sign-in of its own** and none should be built. Everything below about Entra ID, OIDC, SSO, claims, the employee-ID claim add-on, the login flow and login outcomes (§1 point 1, §2, §6 "Login outcomes", the §9.1 column comment, §10 item 5) no longer applies. The rest (who should see which family, comments, access review) is kept as background only, for if per-person views are wanted later; then SAM_ACCOUNT is the key to match whatever identity the add-on passes on. Current state: [architecture, access](../wiki/architecture.md#access), [deployment, access](../wiki/deployment.md#access). The storage this document assumes (`evidence_item`, `hr_mapping`, a row-level-security view) was replaced by the 13-table model in doc 11 and `backend/trust/access.py`; where this document and the code differ, the code is right.

Audience: executives and auditors. Status: design draft, 31 Oct 2026. Reopens D3 (v1 = Tech Risk-only logins) as already driven by D-13, D-18, D-20, D-25, D-26 and D-27. Replaces the access sketch in ARCH_REVIEW §4.5 and §5.2 and supersedes `app_user.role` as the only authorisation field in `05_schema.sql`.

## 1. Principles

1. **Identity comes from Entra ID, never from typing.** Nobody types a name, a role or an approver. This closes finding A1 and A2 (ARCH_REVIEW §3.4).
2. **Authorisation is derived from the frozen monthly HR snapshot wherever possible.** Who leads or belongs to a family is a fact in HR data, not a list someone maintains. Only exceptions (Tech Risk staff, auditors, delegates) are granted by hand.
3. **Least privilege.** Each person sees their own family; only Tech Risk sees across families; item-level evidence is the narrowest grant.
4. **Every read of Restricted data is logged**, with who, what, how many rows, and for downloads the file hash.
5. **A page never shows more than the database would return.** Row-level security (RLS) in Postgres enforces family scope, so a UI bug or a hand-crafted query cannot widen it.

## 2. Identity flow

| Step | What happens | Control |
|---|---|---|
| 1 | User opens the app; OIDC login to Entra ID (SSO, MFA per corporate policy). | No local passwords except break-glass. |
| 2 | App receives claims: `sub` (subject), `email`, and `employee_id` (via the organisation's claim add-on). | Missing employee ID: deny, tell the user to contact Tech Risk. |
| 3 | App finds `app_user` by `sso_subject`. If none: **create on first login only if the employee ID exists in the current (latest frozen) HR snapshot**; otherwise deny and log the attempt. | Stops ex-employees, contractors and unknown accounts. |
| 4 | Revoked or expired user: deny. | `revoked_at` honoured on every request. |
| 5 | For each database transaction the single data-access module runs `SET LOCAL app.user_id = <app_user_id>`, `SET LOCAL app.employee_id = '<id>'` and `SET LOCAL app.user = '<sso_subject>'`. | `SET LOCAL` expires at commit, so pooled connections cannot leak identity. The existing `fn_audit()` reads `app.user` (05 §0); keep it, add the other two. |
| 6 | Audit and access logs record the named person automatically. | `audit_log.app_user` should become NOT NULL (ARCH_REVIEW §4.5). |

**Break-glass.** One account (`is_break_glass`, no employee ID) outside SSO, credentials in the vault, held by the Head of Tech Risk and the platform DBA jointly. Each use needs a written reason and an expiry, raises an alert, and is reviewed by a person who did not use it, in the next quarterly review. It has DBA-style access, not business-approver rights: it cannot approve, lock or accept.

**Revocation.**
- **Automatic:** at each monthly snapshot freeze, anyone whose employee ID is no longer present is revoked (`revoked_at`, reason `left_hr_snapshot`) and their derived roles disappear. Delegations approved by a manager who left end the same day.
- **Immediate:** on request from HR, the manager or Tech Risk, a `tr_admin` sets `revoked_at` now. The request and approver are recorded. Sessions are checked on every request, so effect is immediate.
- Gap to accept or close: between a leaver's last day and the next snapshot, access persists unless requested. Mitigation: Entra disables the account on exit, which blocks login anyway; the snapshot rule is the backstop.

## 3. Role model

**Explicit roles** (granted by Tech Risk; each grant records approver and expiry; held in `app_user_role`, §9):

| Role | Who | Notes |
|---|---|---|
| `tr_admin` | Tech Risk admin | Only role that changes data (03 §2.1). |
| `tr_reviewer` | Second reviewer | Must differ from admin for the month (03 §3.1). |
| `tr_head` | Head of Tech Risk | Approves/locks (O-6 recommendation: head signs, reviewer prepares). |
| `auditor_readonly` | Named auditors | Per engagement, with end date. Auditor page and evidence reader. |
| `platform_dba` | Platform DBA | Database only, no application rights; every use logged (03 §3.1). |

**Derived roles** (recomputed from the frozen HR snapshot each month; nobody grants them):

| Role | Rule |
|---|---|
| `family_lead` | Employee ID is a `team_key` in `hr_mapping` mapped to the family, **or** a registered delegate approved by that manager. |
| `family_member` | Employee's manager chain reaches a `team_key` mapped to the family. |
| `provider_contact` | Named in a signed data contract. Only relevant if provider logins are approved (O-3). |

Implementation point: 05 loads only team-level `hr_mapping`; the manager chain lives in the file in immutable storage. To compute `family_member` the freeze step must also load a minimal `hr_membership (hr_snapshot_id, employee_id, team_key)` table (Restricted, append-only, no names). See §9.

**Permission matrix.** Y = yes, N = no, own = own family only.

| Action | tr_admin | tr_reviewer | tr_head | auditor_readonly | platform_dba | family_lead | family_member | provider_contact |
|---|---|---|---|---|---|---|---|---|
| View CTO view | Y | Y | Y | Y (locked) | N | N | N | N |
| View family page | Y | Y | Y | Y (locked) | N | own | own | N |
| View other families | Y | Y | Y | Y (locked) | N | N (firm typical value only) | N | N |
| View Level 1 drivers | Y | Y | Y | Y | N | own | own | N |
| View Level 2 items | Y | Y | Y | Y | N | own* | N | N |
| Download family data | Y | Y | Y | N (uses reperformance pack) | N | own* | N | N |
| Add comment | late_response only | N | late_response only | N | N | own | own | N |
| Accept comment | N | N | N | N | N | own | N | N |
| Raise data query | Y (logs) | N | Y | N | N | own | N | N |
| Upload submission | Y | N | N | N | N | N | N | own contract (v1.2) |
| Request feed onboarding | Y | N | N | N | N | N | N | own contract (v1.2) |
| Approve threshold | N | N | Y (proposer differs) | N | N | N | N | N |
| Approve metric version | N | N | Y (proposer differs) | N | N | N | N | N |
| Lock period | N (prepares: reviewer) | prepare | Y | N | N | N | N | N |
| Restate | prepare | review | approve (not the preparer) | N | N | N | N | N |
| View auditor page | Y | Y | Y | Y | N | N | N | N |
| View evidence of any family | Y | Y | Y | Y | N | N | N | N |

\* Level 2 and download depend on the Restricted classification sign-off (O-5; agreed in principle by the owner). Lead and members see the family's own items only, pseudonymised (D-26).

## 4. Commentary workflow with acceptance

**Is it too complicated?** No, with one caveat. Compared with the lock-and-submit design in ARCH_REVIEW §5.2 it adds one state (`proposed` to `accepted`) and one queue (the lead's "pending your acceptance"). The caveat is workload: a lead with many contributors must clear the queue by BD12, hence reminders and a visible count. Recommended, because it answers the question an executive or auditor will ask of any comment: **who said this, and who stands behind it?** Without acceptance, anyone in the family could put words in front of the CTO. With it, each published comment carries two named people.

**States**

| State | Meaning | Who moves it |
|---|---|---|
| draft | Private to author. | Author. |
| proposed | Submitted for the lead's decision. | Any family_member or family_lead. |
| accepted | Lead stands behind it. Counts. | A family_lead for that family; **never the author** (a lead's own comment needs the other lead or a delegate; if none exists, see §8). |
| returned | Lead sends back with a short note (up to 200 characters). Author may revise (new version) and re-propose. | Lead. |
| withdrawn | Author retracts; text kept. | Author. |

Rules:
- **Pending queue** on the family page for leads; count badge; reminders at BD10 and BD12 morning (D-22).
- **At lock (BD12)** only `accepted` comments enter the hashed snapshot. Proposed-but-unaccepted comments are not included and stay visible to the family as "not accepted before lock". Tech Risk may add a `late_response` after lock, flagged "received after lock", never altering the snapshot (D-22).
- **Attribution always shown:** "Proposed by A. Nguyen (Order routing), accepted by Lead K". D-18's "Family says:" marker shows accepted comments only.
- 600 characters, plain text, Confidential, "no client names, hostnames, secrets". Append-only versions (`supersedes_comment_id`); editing creates a new version and resets state to `proposed`.
- A comment is not a data query, action or risk-acceptance request (routes as in review §5.2).

## 5. Row-level security sketch

Principle: the database decides, the UI filters nothing by itself.

```sql
-- Families the current session user may see, for a given HR snapshot
CREATE FUNCTION trust.fn_user_families(p_snapshot int) RETURNS SETOF smallint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = trust, pg_temp AS $$
  SELECT m.product_family_id FROM trust.hr_membership h
    JOIN trust.hr_mapping m USING (hr_snapshot_id, team_key)
   WHERE h.hr_snapshot_id = p_snapshot
     AND h.employee_id = current_setting('app.employee_id', true)
  UNION
  SELECT d.product_family_id FROM trust.family_delegate d
   WHERE d.delegate_employee_id = current_setting('app.employee_id', true)
     AND current_date BETWEEN d.effective_from AND coalesce(d.effective_to, 'infinity') $$;

CREATE FUNCTION trust.fn_is_tech_risk() RETURNS boolean ... -- app_user_role holds tr_* / auditor_readonly, not expired

ALTER TABLE trust.family_comment ENABLE ROW LEVEL SECURITY;
CREATE POLICY p_family_scope ON trust.family_comment FOR SELECT USING (
  trust.fn_is_tech_risk()
  OR product_family_id IN (SELECT trust.fn_user_families(hr_snapshot_id)) );
```

- Family-scoped tables and views (comments, notes, actions, data queries, results by family, evidence) all use the same function. The snapshot parameter is the period's own snapshot, so a locked month is judged by who belonged then, not now (see §8).
- Evidence views: `CREATE VIEW ... WITH (security_invoker = true)` over `trust_evidence.evidence_item`, joined to `hr_mapping` on `(hr_snapshot_id, team_key)`. The base table is granted only to `trust_evidence_reader`; family users query the views as `trust_web`.
- Tech Risk bypass is by role membership (`fn_is_tech_risk()`), not by a superuser connection. The web role is never `BYPASSRLS`.
- Writes: RLS `WITH CHECK` ensures a user can only insert comments for their own family and as themselves; a trigger blocks self-acceptance and any insert after lock except `late_response`.
- **Tests (run in CI against a seeded database):** for each family pair, as a member of A, `SELECT` from every family-scoped table and view with no filter and with `WHERE family = B`, and with a crafted `UNION`/subquery: zero rows of B. Also: user with no snapshot membership gets zero rows; revoked user is denied; delegate sees only the delegated family; `app.employee_id` unset returns nothing (policies fail closed).

## 6. Logging

| Event | Recorded (in `access_log`, append-only) |
|---|---|
| Page view | user, page, family, period, time. |
| Drill-down (Level 1) | user, metric, grouping, family, period. |
| Item list (Level 2) | user, metric, filter (team/app), family, period, **row_count**. |
| Download | user, family, period, **row_count, file_sha256**, watermark id. |
| Comment events | create, propose, return, withdraw, edit (new version), accept, `late_response`: actor, comment id, from/to state. Also in `audit_log` through the trigger. |
| Login outcomes | success, denied (not in HR snapshot, revoked), break-glass use with reason. |

Retention 7 years, matching the evidence schedule. Direct database reads of `trust_evidence` are covered by `pgaudit`. **Review:** the quarterly access review (§7) examines the log for unusual volumes (downloads, Level 2 reads), denied logins and break-glass use. Reviewer is a Tech Risk person who is not the one being reviewed; the Head of Tech Risk signs.

## 7. Access review (quarterly)

| Population | Review | Evidence kept |
|---|---|---|
| Derived roles | Confirm the HR mapping itself was approved at each freeze (`approved_by <> frozen_by`, 05). No per-person review. | Snapshot hashes; snapshot **diff** for the quarter: leavers, movers, new managers. |
| Explicit roles | Each grant re-confirmed or revoked by the Head of Tech Risk; expiry enforced. | Signed list with decision per person. |
| Delegates | Approving manager re-confirms each delegate (or they lapse). | Confirmation record. |
| Auditors | Granted per engagement with end date; removed at end; extended only with a new approval. | Grant and removal timestamps. |
| Break-glass and DBA | Each use matched to a request. | Reason, expiry, reviewer. |

## 8. Edge cases

| Case | Handling |
|---|---|
| Manager owns teams in two families | Two `hr_mapping` rows, so lead of both; sees both pages; comment acceptance is per family and still not by the author. |
| Family with no manager in the snapshot | Nobody derives as lead, so comments cannot be accepted; the page shows "no lead identified"; Tech Risk raises it with HR and may register a delegate only with the line executive's approval. Flagged at freeze as a check. |
| Contractors without employee IDs | No access. They contribute through their lead, who proposes on their behalf (the lead may not self-accept, so need a second approver). Revisit if this is common. |
| Delegates | Registered in `family_delegate`, approved by the manager, effective dates, shown in the access review. A delegate may accept comments but not delegate onward. |
| Reorg mid-month | Takes effect at the next snapshot (05: "reorgs take effect next month"). Leavers: see §2. |
| User moves family, views a locked month | Derived roles are per snapshot: they see their *new* family now; the old family's locked months are no longer visible to them. Stated on the page. Their past comments stay attributed. |
| Only one lead and they authored the comment | Another lead or a delegate must accept; otherwise it stays unaccepted at lock. Recommend each family has two (1–2 leads per family, per the owner). |

## 9. Schema changes (draft DDL, 05 conventions)

```sql
-- 9.1 app_user: employee ID from the SSO claim
ALTER TABLE app_user
  ADD COLUMN employee_id text,
  ADD CONSTRAINT uq_app_user_employee UNIQUE (employee_id),
  ADD CONSTRAINT ck_app_user_emp CHECK (employee_id IS NOT NULL OR is_break_glass);
ALTER TABLE app_user DROP COLUMN role;     -- replaced by app_user_role below (migrate existing rows first)
COMMENT ON COLUMN app_user.employee_id IS
  'From the Entra ID employee-ID claim; must exist in the current HR snapshot at first login. NULL only for the break-glass account.';

-- 9.2 Explicit roles, with approver and expiry
CREATE TABLE app_user_role (
  app_user_role_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  app_user_id  integer NOT NULL REFERENCES app_user,
  role         text NOT NULL CHECK (role IN ('tr_admin','tr_reviewer','tr_head','auditor_readonly','platform_dba')),
  granted_by   integer NOT NULL REFERENCES app_user,
  approved_by  integer NOT NULL REFERENCES app_user,
  effective_from timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  revoked_at   timestamptz,
  engagement_ref text,                       -- auditors: engagement id
  CHECK (approved_by <> app_user_id AND granted_by <> app_user_id),
  CHECK (expires_at > effective_from),
  CHECK (role <> 'auditor_readonly' OR engagement_ref IS NOT NULL)
);

-- 9.3 Who is under which team in each frozen snapshot (needed for family_member; Restricted)
CREATE TABLE hr_membership (
  hr_snapshot_id integer NOT NULL,
  employee_id    text NOT NULL,
  team_key       text NOT NULL,              -- nearest mapped manager key in the chain
  PRIMARY KEY (hr_snapshot_id, employee_id),
  FOREIGN KEY (hr_snapshot_id, team_key) REFERENCES hr_mapping (hr_snapshot_id, team_key)
);   -- add to the append-only trigger list in 05 §10

-- 9.4 Delegates
CREATE TABLE family_delegate (
  family_delegate_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  product_family_id  smallint NOT NULL REFERENCES product_family,
  delegate_employee_id text NOT NULL,
  approved_by_employee_id text NOT NULL,     -- must be a team_key of that family in the snapshot in force (checked by trigger)
  effective_from date NOT NULL,
  effective_to   date,
  recorded_by    integer NOT NULL REFERENCES app_user,
  CHECK (delegate_employee_id <> approved_by_employee_id),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

-- 9.5 Commentary state machine (replaces the draft in 09)
CREATE TABLE family_comment (
  family_comment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  period_id          integer NOT NULL REFERENCES period,
  product_family_id  smallint NOT NULL REFERENCES product_family,
  metric_code        text REFERENCES metric,
  block_code         text REFERENCES block,
  CHECK (metric_code IS NULL OR block_code IS NULL),
  body               text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 600),
  state              text NOT NULL CHECK (state IN ('draft','proposed','accepted','returned','withdrawn')),
  supersedes_comment_id bigint REFERENCES family_comment,
  author_app_user_id integer NOT NULL REFERENCES app_user,
  author_employee_id text    NOT NULL,
  proposed_at        timestamptz,
  accepted_by_employee_id text,
  accepted_at        timestamptz,
  returned_note      text CHECK (char_length(returned_note) <= 200),
  is_late_response   boolean NOT NULL DEFAULT false,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (state <> 'accepted' OR (accepted_by_employee_id IS NOT NULL AND accepted_at IS NOT NULL)),
  CHECK (accepted_by_employee_id IS NULL OR accepted_by_employee_id <> author_employee_id),
  CHECK (state <> 'returned' OR returned_note IS NOT NULL)
);
-- Triggers: body/author/period/family immutable once proposed; lock guard (D-22);
-- acceptor must be in fn_user_families as lead; RLS per §5; audit trigger per 05 §10.

-- 9.6 access_log: from page views to a usable read record
CREATE TYPE access_action AS ENUM ('view_page','view_drilldown','view_items','download',
  'comment_create','comment_propose','comment_accept','comment_return','comment_withdraw',
  'login_denied','break_glass_use');
ALTER TABLE access_log
  ADD COLUMN action access_action NOT NULL DEFAULT 'view_page',
  ADD COLUMN product_family_id smallint REFERENCES product_family,
  ADD COLUMN metric_code text,
  ADD COLUMN row_count integer,
  ADD COLUMN file_sha256 char(64) CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
  ADD COLUMN reason text,
  ADD CONSTRAINT ck_access_download CHECK (action <> 'download' OR (row_count IS NOT NULL AND file_sha256 IS NOT NULL));
ALTER TABLE access_log ALTER COLUMN app_user_id DROP NOT NULL;   -- denied logins have no user yet; record sso_subject in reason

-- 9.7 Drill-down link to the provider's own tool (D-27)
ALTER TABLE connector ADD COLUMN source_url_template text
  CHECK (source_url_template IS NULL OR source_url_template ~ '^https://[^ ]+\{item_id\}');
```

**What changes in 09 (earlier commentary draft):** `family_user` is dropped (derivation replaces it, plus `family_delegate`); `family_contributor` as a stored role is dropped (members are derived); statuses become `draft/proposed/accepted/returned/withdrawn` instead of `draft/submitted/acknowledged/withdrawn/superseded` (superseding is by version link); the "Tech Risk acknowledged" step goes away because acceptance by the lead replaces it; `author_app_user_id` stays, plus employee IDs for stable attribution; the pre-read view includes `accepted` only.

## 10. Open decisions for the owner

1. **Delegates:** allowed at all, who approves them, and do they get acceptance rights?
2. **Contributors:** every employee under the family's managers (derived, zero upkeep, wide), or a named list kept by the lead (narrower, extra upkeep)? Recommendation: the derived group for viewing and commenting; Level 2 items for leads only.
3. **Can a lead edit a proposed comment,** or only accept or return it? Recommendation: accept or return only, so the author's words are what the lead endorsed.
4. **Do leaders (the CTO's direct reports) get logins now?** (O-4 recommended v2; they receive the pre-read PDF today.)
5. **Auditor accounts:** in Entra (guest or staff, with engagement end date) or separate local accounts? Recommendation: Entra guests, expiry enforced.
6. Related, from the review: a single-lead family cannot accept its own lead's comment; confirm every family has two leads or a delegate. Also confirm Level 2 and downloads for leads stay behind the Restricted sign-off (O-5).
