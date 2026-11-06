-- Retention (D-86, built 5 Nov 2026): the event log records when expired months and old runs were removed.
-- The same change admits the background update's own lines ("update started", "update finished",
-- "update failed", written by backend/trust/jobs.py since 4 Nov), which the earlier list left out:
-- on the database the Update button failed on them (found in review, 5 Nov 2026).

ALTER TABLE event_log DROP CONSTRAINT event_log_action_check;
ALTER TABLE event_log ADD CONSTRAINT event_log_action_check
    CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment', 'acknowledge',
                      'proposal', 'decision', 'download', 'view', 'contract', 'retention',
                      'update started', 'update finished', 'update failed'));
