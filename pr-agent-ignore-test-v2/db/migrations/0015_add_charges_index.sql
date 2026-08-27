-- Migration 0015: add charges table + index (SHOULD be reviewed).
-- Hand-written DDL: migrations must stay reviewable (NOT ignored).

BEGIN;

CREATE TABLE IF NOT EXISTS charges (
    id           BIGSERIAL PRIMARY KEY,
    account_id   BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    status       VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts     INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMP NOT NULL DEFAULT now()
);

-- BUG: non-concurrent index build inside a transaction takes an exclusive
-- lock and blocks writes for the whole build on a large table. Should be
-- CREATE INDEX CONCURRENTLY (outside a transaction block).
CREATE INDEX idx_charges_account_id ON charges (account_id);

-- BUG: destructive backfill with no WHERE guard — rewrites status for every
-- existing row, not just the newly migrated ones.
UPDATE charges SET status = 'pending';

-- BUG: dropping a column still read by the previous app version during a
-- rolling deploy (no backward-compatible two-step migration).
ALTER TABLE charges DROP COLUMN IF EXISTS legacy_state;

COMMIT;
