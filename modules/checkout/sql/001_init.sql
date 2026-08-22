-- Checkout v1 schema. Idempotency for place only. Business facts live in sibling modules.
CREATE TABLE checkout_placements (
    store_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    cart_id TEXT NOT NULL,
    order_id TEXT NOT NULL DEFAULT '',
    payment_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, idempotency_key)
);
