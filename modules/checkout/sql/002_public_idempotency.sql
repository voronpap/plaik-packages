ALTER TABLE checkout_placements ADD COLUMN IF NOT EXISTS subject TEXT NOT NULL DEFAULT '';
ALTER TABLE checkout_placements ADD COLUMN IF NOT EXISTS fingerprint TEXT NOT NULL DEFAULT '';
ALTER TABLE checkout_placements ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'in_flight';
ALTER TABLE checkout_placements ADD CONSTRAINT checkout_placements_state_check
    CHECK (state IN ('in_flight', 'completed', 'failed_safe', 'needs_reconciliation'));
