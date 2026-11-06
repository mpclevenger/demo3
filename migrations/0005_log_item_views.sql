-- Who looked at item detail (owner, 3 Nov 2026: roles set up on TRUST's side). One line per page load
-- that fetched item detail, with the families it covered.

ALTER TABLE event_log DROP CONSTRAINT event_log_action_check;
ALTER TABLE event_log ADD CONSTRAINT event_log_action_check
    CHECK (action IN ('upload', 'map', 'score', 'publish', 'lock', 'reopen', 'comment', 'acknowledge',
                      'proposal', 'decision', 'download', 'view'));
COMMENT ON COLUMN event_log.action IS 'upload, map, score, publish, lock, reopen, comment, acknowledge, proposal, decision, download or view (item detail).';
