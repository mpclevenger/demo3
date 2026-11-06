-- What TRUST keeps before the full data model (doc 11) is built: the cut-down uploads,
-- the upload register, each month's mapped and scored results, and the published page.

CREATE TABLE kept_file (
    sha256     text PRIMARY KEY,
    content    bytea NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE kept_file IS 'An uploaded file after it was cut down to what TRUST uses, keyed by the hash of what was kept. Never changed.';
COMMENT ON COLUMN kept_file.sha256 IS 'SHA-256 of the kept (cut-down) bytes.';
COMMENT ON COLUMN kept_file.content IS 'The kept bytes: only the columns or JSON fields TRUST uses (HR: only the CTO''s line).';
COMMENT ON COLUMN kept_file.created_at IS 'When it was first kept.';

CREATE TABLE submission (
    id          bigserial PRIMARY KEY,
    month       text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    feed        text NOT NULL,
    entry       jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX submission_month_feed ON submission (month, feed, id);
COMMENT ON TABLE submission IS 'Every upload, newest last per feed and month. The newest is the one mapping uses; earlier ones are kept (D-92).';
COMMENT ON COLUMN submission.month IS 'The month the file is for, YYYY-MM.';
COMMENT ON COLUMN submission.feed IS 'Which provider file (feed code, e.g. tcc, cx_sca).';
COMMENT ON COLUMN submission.entry IS 'The upload record: who, when, file name, hash of the file as received, hash of what was kept, columns kept and not found, SharePoint link.';
COMMENT ON COLUMN submission.received_at IS 'When the database recorded the upload.';

CREATE TABLE month_result (
    kind       text NOT NULL CHECK (kind IN ('mapped', 'scored')),
    month      text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, month)
);
COMMENT ON TABLE month_result IS 'The latest mapping or scoring of a month. Re-running map or score replaces it.';
COMMENT ON COLUMN month_result.kind IS 'mapped (step 2) or scored (step 3).';
COMMENT ON COLUMN month_result.month IS 'YYYY-MM.';
COMMENT ON COLUMN month_result.doc IS 'The full result as JSON.';
COMMENT ON COLUMN month_result.updated_at IS 'When it was last worked out.';

CREATE TABLE published_file (
    name       text PRIMARY KEY CHECK (name IN ('index.html', 'data.json', 'evidence.json')),
    body       text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE published_file IS 'What the website shows, written by python -m trust publish.';
COMMENT ON COLUMN published_file.name IS 'index.html (the screens with the data built in), data.json or evidence.json.';
COMMENT ON COLUMN published_file.body IS 'The file''s text.';
COMMENT ON COLUMN published_file.updated_at IS 'When it was last published.';
