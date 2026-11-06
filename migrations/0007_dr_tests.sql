-- The completed DR tests file, kept as a table (owner, 3 Nov 2026). One row per test per upload,
-- never edited: a new upload for the month adds its own rows, and the newest upload is the current list.

CREATE TABLE dr_test (
    id               bigserial PRIMARY KEY,
    submission_id    bigint NOT NULL REFERENCES submission (id),
    month            text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    application_name text NOT NULL,
    recovery_tier    smallint CHECK (recovery_tier BETWEEN 0 AND 5),
    tier_label       text NOT NULL CHECK (tier_label IN ('Tier 0', 'Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5', 'TBC', 'Not given')),
    business_area    text,
    itdr_lead        text,
    test_type        text,
    test_date        date,
    status           text NOT NULL,
    comments         text,
    comment_date     date,
    ttx_in_comment   boolean NOT NULL DEFAULT false
);
CREATE INDEX dr_test_month ON dr_test (month, submission_id);
COMMENT ON TABLE dr_test IS 'Completed DR tests from the DR tests file, one row per test per upload. The newest upload for a month is the current list. Linked to itdr_application by name at mapping, not here.';
COMMENT ON COLUMN dr_test.submission_id IS 'The upload these rows came from (submission.id).';
COMMENT ON COLUMN dr_test.month IS 'YYYY-MM the file was uploaded for.';
COMMENT ON COLUMN dr_test.application_name IS 'Name, tidied the same way as the ITDR application file.';
COMMENT ON COLUMN dr_test.recovery_tier IS '0 (most critical) to 5 (least); null for TBC or not given.';
COMMENT ON COLUMN dr_test.tier_label IS 'Tier 0 to Tier 5, TBC, or Not given.';
COMMENT ON COLUMN dr_test.business_area IS 'Business Area; null when blank.';
COMMENT ON COLUMN dr_test.itdr_lead IS 'ITDR Lead, as written.';
COMMENT ON COLUMN dr_test.test_type IS 'Open, Closed or TTX (tabletop exercise); anything else as written; null when blank.';
COMMENT ON COLUMN dr_test.test_date IS 'When (MM/DD/YYYY in the file); null when blank or not a date.';
COMMENT ON COLUMN dr_test.status IS 'Successful, Not recorded (blank in the file), or anything else as written.';
COMMENT ON COLUMN dr_test.comments IS 'Comments, tidied.';
COMMENT ON COLUMN dr_test.comment_date IS 'The date read from a comment like "DR Test completed on 14th March 2026"; null if none.';
COMMENT ON COLUMN dr_test.ttx_in_comment IS 'True when the comment mentions TTX or a tabletop exercise.';
