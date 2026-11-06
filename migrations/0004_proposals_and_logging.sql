-- Proposals to change the metric dictionary, and the decisions on them (owner, 3 Nov 2026).
-- Never edited: a decision is a new row. Approving records the decision only.

CREATE TABLE proposal (
    id     bigserial PRIMARY KEY,
    at     timestamptz NOT NULL DEFAULT now(),
    kind   text NOT NULL CHECK (kind IN ('change', 'new_metric', 'retire')),
    metric text,
    title  text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    detail jsonb NOT NULL,
    by     text NOT NULL
);
COMMENT ON TABLE proposal IS 'A suggestion to change a metric''s wording, add a new metric or retire one. Never edited; the answer is a row in proposal_decision.';
COMMENT ON COLUMN proposal.at IS 'When it was proposed.';
COMMENT ON COLUMN proposal.kind IS 'change (new wording for a metric), new_metric (a metric that does not exist yet) or retire (stop using a metric).';
COMMENT ON COLUMN proposal.metric IS 'The metric it is about, e.g. TE-01. Empty for a new metric.';
COMMENT ON COLUMN proposal.title IS 'A short heading, 1 to 200 characters.';
COMMENT ON COLUMN proposal.detail IS 'The details as the person filled them in (change: field, wording, reason; retire: reason, effective month; new metric: name, why).';
COMMENT ON COLUMN proposal.by IS 'The name typed by the person who proposed it.';

CREATE TABLE proposal_decision (
    id          bigserial PRIMARY KEY,
    proposal_id bigint NOT NULL REFERENCES proposal (id),
    decision    text NOT NULL CHECK (decision IN ('approved', 'returned', 'declined', 'withdrawn')),
    reason      text NOT NULL DEFAULT '',
    by          text NOT NULL,
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX proposal_decision_proposal ON proposal_decision (proposal_id);
COMMENT ON TABLE proposal_decision IS 'The answer to a proposal. A proposal with no row here is still open. Never edited. Approving records the decision only; the dictionary and scoring are changed separately.';
COMMENT ON COLUMN proposal_decision.proposal_id IS 'The proposal this answers.';
COMMENT ON COLUMN proposal_decision.decision IS 'approved, returned (needs more), declined, or withdrawn (by the person who proposed it).';
COMMENT ON COLUMN proposal_decision.reason IS 'Why. Required for returned and declined.';
COMMENT ON COLUMN proposal_decision.by IS 'The name typed by the person who decided.';
COMMENT ON COLUMN proposal_decision.at IS 'When.';

ALTER TABLE event_log DROP CONSTRAINT event_log_action_check;
ALTER TABLE event_log ADD CONSTRAINT event_log_action_check
    CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment', 'acknowledge',
                      'proposal', 'decision', 'download'));
COMMENT ON COLUMN event_log.action IS 'upload, map, score, publish, lock, reopen, comment, acknowledge, proposal, decision or download.';
