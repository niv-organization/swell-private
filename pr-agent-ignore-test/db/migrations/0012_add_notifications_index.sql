-- Migration 0012: add notifications table + index (SHOULD be reviewed).
-- Hand-written DDL: migrations must stay reviewable (NOT ignored).

BEGIN;

CREATE TABLE IF NOT EXISTS notifications (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    channel     VARCHAR(32) NOT NULL,
    payload     TEXT NOT NULL,
    attempts    INT NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT now()
);

-- BUG: non-concurrent index build inside a transaction takes an exclusive
-- lock on the table and blocks writes for the whole build on a large table.
-- Should be CREATE INDEX CONCURRENTLY (outside a transaction block).
CREATE INDEX idx_notifications_user_id ON notifications (user_id);

-- BUG: destructive backfill with no WHERE guard — resets attempts for every
-- row in the table, not just newly migrated ones.
UPDATE notifications SET attempts = 0;

-- BUG: dropping a column that may still be read by the previous app version
-- during a rolling deploy (no backward-compatible two-step migration).
ALTER TABLE notifications DROP COLUMN IF EXISTS legacy_status;

COMMIT;
