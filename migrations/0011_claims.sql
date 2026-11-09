-- Lost and Found (owner, 9 Nov 2026): items no source file could place with a family (a change by someone not in
-- HR, a repo with no owner, an application with no matching product area...) are listed on the Lost and found page.
-- A family lead (or Tech Risk) claims an item for a family; Tech Risk approves or returns the claim. An approved
-- claim places the item from the next Update of any open month, and carries over to every later month the item
-- appears in. It never overrides a source file: an item a file places goes where the file says. Tech Risk can
-- release an approved claim (the undo). The request itself is never edited; only the decision columns change.

CREATE TABLE claim (
    id          bigserial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    feed        text NOT NULL,
    item        text NOT NULL,
    label       text NOT NULL DEFAULT '',
    family_id   text NOT NULL,
    month       text NOT NULL,
    why         text NOT NULL,
    by          text NOT NULL,
    status      text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'returned', 'withdrawn', 'released')),
    decided_by  text,
    decided_at  timestamptz,
    reason      text NOT NULL DEFAULT ''
);
CREATE INDEX claim_item ON claim (feed, item);
COMMENT ON TABLE claim IS 'A claim on a Lost and Found item (owner, 9 Nov 2026): this item belongs to this family. Tech Risk approves it; approved claims place the item at every later Update.';
COMMENT ON COLUMN claim.feed IS 'The file the item comes from, e.g. tcc, actions, repos.';
COMMENT ON COLUMN claim.item IS 'The item''s own reference in that file: RPD, action, repo, Checkmarx project, ITDR Ref or incident.';
COMMENT ON COLUMN claim.label IS 'How the item read on the page when it was claimed.';
COMMENT ON COLUMN claim.month IS 'The month it was claimed from (YYYY-MM).';
COMMENT ON COLUMN claim.why IS 'Why it belongs to the family, in the claimer''s words.';
COMMENT ON COLUMN claim.status IS 'draft (waiting for Tech Risk), approved, returned, withdrawn (by the person who asked) or released (approved, then undone by Tech Risk).';
COMMENT ON COLUMN claim.reason IS 'Why it was returned or released.';

ALTER TABLE event_log DROP CONSTRAINT event_log_action_check;
ALTER TABLE event_log ADD CONSTRAINT event_log_action_check
    CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment', 'acknowledge',
                      'proposal', 'decision', 'download', 'view', 'contract', 'retention',
                      'update started', 'update finished', 'update failed', 'claim'));
