-- The ITDR application file, kept as a table (owner, 3 Nov 2026). One row per application per upload,
-- never edited: a new upload for the month adds its own rows, and the newest upload is the current list.

CREATE TABLE itdr_application (
    id                    bigserial PRIMARY KEY,
    submission_id         bigint NOT NULL REFERENCES submission (id),
    month                 text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    ref                   integer NOT NULL,
    application_name      text NOT NULL,
    business_product_area text,
    recovery_tier         smallint CHECK (recovery_tier BETWEEN 0 AND 5),
    tier_label            text NOT NULL CHECK (tier_label IN ('Tier 0', 'Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5', 'TBC', 'Not given')),
    UNIQUE (submission_id, ref)
);
CREATE INDEX itdr_application_month ON itdr_application (month, submission_id);
COMMENT ON TABLE itdr_application IS 'Applications from the ITDR file, one row per application per upload. The newest upload for a month is the current list.';
COMMENT ON COLUMN itdr_application.submission_id IS 'The upload these rows came from (submission.id).';
COMMENT ON COLUMN itdr_application.month IS 'YYYY-MM the file was uploaded for.';
COMMENT ON COLUMN itdr_application.ref IS 'The register''s own number for the application (column Ref).';
COMMENT ON COLUMN itdr_application.application_name IS 'Application Name, with extra spaces and line breaks tidied.';
COMMENT ON COLUMN itdr_application.business_product_area IS 'Business Product Area; null when the file leaves it blank.';
COMMENT ON COLUMN itdr_application.recovery_tier IS '0 (most critical) to 5 (least); null for TBC or not given.';
COMMENT ON COLUMN itdr_application.tier_label IS 'Tier 0 to Tier 5, TBC, or Not given (blank or not a recognised tier).';
