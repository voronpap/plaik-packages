ALTER TABLE checkout_placements ADD COLUMN IF NOT EXISTS subject TEXT NOT NULL DEFAULT '';
ALTER TABLE checkout_placements ADD COLUMN IF NOT EXISTS fingerprint TEXT NOT NULL DEFAULT '';
ALTER TABLE checkout_placements ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'in_flight';
UPDATE checkout_placements
SET state = CASE
    WHEN order_id <> '' OR payment_id <> '' THEN 'completed'
    ELSE 'needs_reconciliation'
END;
ALTER TABLE checkout_placements ADD CONSTRAINT checkout_placements_state_check
    CHECK (state IN ('in_flight', 'completed', 'failed_safe', 'needs_reconciliation'));
CREATE UNIQUE INDEX IF NOT EXISTS checkout_placements_unresolved_cart_uq
    ON checkout_placements (store_id, cart_id, subject)
    WHERE state IN ('in_flight', 'needs_reconciliation') AND subject <> '';
