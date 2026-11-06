-- Data contracts (owner, 4 Nov 2026): one row per request to onboard a data source, or per new version of a source
-- already onboarded. Anyone can request from the Data dictionary page; Tech Risk approves or returns it.
-- Formal = approved. Once a contract is approved, TRUST may not read the file for a metric the contract doesn't
-- list, and a file whose columns differ from the contract is flagged at upload (acknowledged before the lock).
-- The request itself is never edited; only the decision columns are filled in, once.

CREATE TABLE data_contract (
    id         bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT now(),
    feed       text NOT NULL,
    version    integer NOT NULL CHECK (version >= 1),
    provider   text NOT NULL,
    contact    text NOT NULL DEFAULT '',
    what       text NOT NULL,
    cadence    text NOT NULL DEFAULT '',
    columns    jsonb NOT NULL,
    metrics    jsonb NOT NULL,
    note       text NOT NULL DEFAULT '',
    by         text NOT NULL,
    status     text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'returned', 'withdrawn')),
    decided_by text,
    decided_at timestamptz,
    reason     text NOT NULL DEFAULT ''
);
CREATE INDEX data_contract_feed ON data_contract (feed, version);
COMMENT ON TABLE data_contract IS 'A request to onboard a data source (or a new version of one), and Tech Risk''s decision on it. Formal = approved (owner, 4 Nov 2026).';
COMMENT ON COLUMN data_contract.feed IS 'The feed id, e.g. tcc.';
COMMENT ON COLUMN data_contract.version IS '1 for the first request for a feed; one more for each later request.';
COMMENT ON COLUMN data_contract.provider IS 'The team that sends the file.';
COMMENT ON COLUMN data_contract.contact IS 'Who to ask about the file.';
COMMENT ON COLUMN data_contract.what IS 'What the file is, in plain words.';
COMMENT ON COLUMN data_contract.cadence IS 'How often it is sent (monthly, on request, ...).';
COMMENT ON COLUMN data_contract.columns IS 'The column names TRUST may read, as a JSON list.';
COMMENT ON COLUMN data_contract.metrics IS 'The metric ids TRUST may use the file for, as a JSON list.';
COMMENT ON COLUMN data_contract.by IS 'The name of the person who asked.';
COMMENT ON COLUMN data_contract.status IS 'draft (waiting for Tech Risk), approved (formal), returned (needs more), withdrawn.';
COMMENT ON COLUMN data_contract.decided_by IS 'Who decided, once.';
COMMENT ON COLUMN data_contract.reason IS 'Why it was returned or withdrawn.';

ALTER TABLE event_log DROP CONSTRAINT event_log_action_check;
ALTER TABLE event_log ADD CONSTRAINT event_log_action_check
    CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment', 'acknowledge',
                      'proposal', 'decision', 'download', 'view', 'contract'));
