-- What a DR tests row is, and when it was performed (owner, 3 Nov 2026):
--   Open = a DR test in production (live); Closed = a DR test that doesn't touch production (UAT, test);
--   TTX = a tabletop exercise, which is not a DR test.
--   A blank Status means it hasn't been performed.
--   A DR test was last performed on the date in its comment; a tabletop exercise on the date in When.

ALTER TABLE dr_test ADD COLUMN kind text CHECK (kind IN ('DR test', 'Tabletop exercise'));
ALTER TABLE dr_test ADD COLUMN environment text CHECK (environment IN ('Production (live)', 'Non-production (UAT, test)'));
ALTER TABLE dr_test ADD COLUMN performed_on date;
COMMENT ON COLUMN dr_test.test_type IS 'Open (DR test in production, live), Closed (DR test outside production: UAT, test) or TTX (tabletop exercise, not a DR test); anything else as written; null when blank.';
COMMENT ON COLUMN dr_test.kind IS 'DR test (Open or Closed) or Tabletop exercise (TTX); null for any other type.';
COMMENT ON COLUMN dr_test.environment IS 'For a DR test: Production (live) or Non-production (UAT, test).';
COMMENT ON COLUMN dr_test.test_date IS 'When (MM/DD/YYYY in the file). The date of a tabletop exercise; null when blank or not a date.';
COMMENT ON COLUMN dr_test.status IS 'Successful, Not performed (blank in the file), or anything else as written (not counted as performed).';
COMMENT ON COLUMN dr_test.performed_on IS 'When it was last performed, only when Status is Successful: a DR test from its comment, a tabletop exercise from When.';
