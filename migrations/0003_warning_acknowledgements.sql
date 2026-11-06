-- Warnings must be read before the lock (owner, 3 Nov 2026): one row per acknowledgement, never edited.

CREATE TABLE warning_ack (
    id       bigserial PRIMARY KEY,
    month    text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    feed     text NOT NULL,
    note_key text NOT NULL,
    note     text NOT NULL,
    by       text NOT NULL,
    at       timestamptz NOT NULL DEFAULT now(),
    reason   text NOT NULL DEFAULT ''
);
CREATE INDEX warning_ack_month ON warning_ack (month, note_key);
COMMENT ON TABLE warning_ack IS 'Who acknowledged each warning from the checks, and when. The lock refuses while any of the month''s warnings has none.';
COMMENT ON COLUMN warning_ack.month IS 'YYYY-MM.';
COMMENT ON COLUMN warning_ack.feed IS 'The feed the warning is about, or "general" for one about the month as a whole.';
COMMENT ON COLUMN warning_ack.note_key IS 'Fingerprint of the feed and the warning''s wording: a warning that changes needs acknowledging again.';
COMMENT ON COLUMN warning_ack.note IS 'The warning, as it read when acknowledged.';
COMMENT ON COLUMN warning_ack.by IS 'The name typed by the person who acknowledged it.';
COMMENT ON COLUMN warning_ack.at IS 'When.';
COMMENT ON COLUMN warning_ack.reason IS 'Optional: why it is acceptable.';

ALTER TABLE event_log DROP CONSTRAINT event_log_action_check;
ALTER TABLE event_log ADD CONSTRAINT event_log_action_check
    CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment', 'acknowledge'));
