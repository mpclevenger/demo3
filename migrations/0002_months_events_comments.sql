-- The rest of the v1 data model (doc 11, owner 3 Nov 2026): each month's status and lock seal,
-- one log of every action, families' comments, and every mapping and scoring run kept as history.

CREATE TABLE month (
    month      text PRIMARY KEY CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    status     text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'locked')),
    locked_by  text,
    locked_at  timestamptz,
    seal       jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status = 'open' OR (locked_by IS NOT NULL AND locked_at IS NOT NULL AND seal IS NOT NULL))
);
COMMENT ON TABLE month IS 'One row per month that has been locked at least once. A month with no row is open.';
COMMENT ON COLUMN month.month IS 'YYYY-MM.';
COMMENT ON COLUMN month.status IS 'open (can be changed) or locked (upload, map and score refuse it).';
COMMENT ON COLUMN month.locked_by IS 'The name typed by the person who locked it.';
COMMENT ON COLUMN month.locked_at IS 'When it was locked.';
COMMENT ON COLUMN month.seal IS 'At the lock: hashes of the scored result, the files used, the settings and the comments, and the git commit.';
COMMENT ON COLUMN month.updated_at IS 'When it was last locked or reopened.';

CREATE TABLE event_log (
    id     bigserial PRIMARY KEY,
    at     timestamptz NOT NULL DEFAULT now(),
    month  text CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    action text NOT NULL CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment')),
    by     text NOT NULL,
    note   text NOT NULL DEFAULT '',
    detail jsonb
);
CREATE INDEX event_log_month ON event_log (month, id);
COMMENT ON TABLE event_log IS 'One line per action, never edited: who did what, when, to which month.';
COMMENT ON COLUMN event_log.at IS 'When it happened.';
COMMENT ON COLUMN event_log.month IS 'The month it was about (empty for publish, which covers every month).';
COMMENT ON COLUMN event_log.action IS 'upload, map, score, publish, lock, reopen or comment.';
COMMENT ON COLUMN event_log.by IS 'The name typed by the person, or "command line".';
COMMENT ON COLUMN event_log.note IS 'A short plain note, e.g. the reason for a reopen.';
COMMENT ON COLUMN event_log.detail IS 'Extra facts, e.g. the feed and file hash for an upload, the seal for a lock.';

CREATE TABLE comment (
    id         bigserial PRIMARY KEY,
    month      text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    family     text NOT NULL,
    metric     text,
    block      text,
    kind       text NOT NULL CHECK (kind IN ('explanation', 'query', 'action')),
    text       text NOT NULL CHECK (length(text) BETWEEN 1 AND 4000),
    by         text NOT NULL,
    at         timestamptz NOT NULL DEFAULT now(),
    reply_to   bigint REFERENCES comment (id),
    status     text CHECK (status IN ('open', 'answered', 'closed')),
    after_lock boolean NOT NULL DEFAULT false
);
CREATE INDEX comment_month ON comment (month, family, id);
COMMENT ON TABLE comment IS 'Families'' explanations, data queries and actions, never edited. A reply is a new row; a thread''s status is its latest row''s.';
COMMENT ON COLUMN comment.month IS 'YYYY-MM.';
COMMENT ON COLUMN comment.family IS 'The product family id the comment is on.';
COMMENT ON COLUMN comment.metric IS 'The metric code it is about, if any.';
COMMENT ON COLUMN comment.block IS 'The building block it is about, if any (its code from the page''s data block, e.g. SEC). Empty metric and block = the whole family.';
COMMENT ON COLUMN comment.kind IS 'explanation, query (a data query) or action.';
COMMENT ON COLUMN comment.text IS 'What they wrote.';
COMMENT ON COLUMN comment.by IS 'The name they typed.';
COMMENT ON COLUMN comment.at IS 'When.';
COMMENT ON COLUMN comment.reply_to IS 'The comment this answers, or empty for a new one.';
COMMENT ON COLUMN comment.status IS 'For queries and actions: open, answered or closed.';
COMMENT ON COLUMN comment.after_lock IS 'True when made while the month was locked: received after lock, never changes the figures (D-22).';

-- Every mapping and scoring run is kept; the newest of each kind is the current one.
ALTER TABLE month_result DROP CONSTRAINT month_result_pkey;
ALTER TABLE month_result ADD COLUMN id bigserial PRIMARY KEY;
ALTER TABLE month_result RENAME COLUMN updated_at TO run_at;
ALTER TABLE month_result ADD COLUMN by text NOT NULL DEFAULT 'command line';
ALTER TABLE month_result ADD COLUMN git_sha text;
ALTER TABLE month_result ADD COLUMN settings_sha256 text;
CREATE INDEX month_result_latest ON month_result (kind, month, id DESC);
COMMENT ON TABLE month_result IS 'Every mapping and scoring run of a month, never edited. The newest of each kind is the current one.';
COMMENT ON COLUMN month_result.run_at IS 'When it was worked out.';
COMMENT ON COLUMN month_result.by IS 'Who ran it (typed name, or "command line").';
COMMENT ON COLUMN month_result.git_sha IS 'The git commit of the code that ran it.';
COMMENT ON COLUMN month_result.settings_sha256 IS 'Hash of the settings, thresholds and column maps it used.';
