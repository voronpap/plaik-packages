-- Payments v1 schema. Manual capture only. No card columns.
CREATE TABLE payments (
    store_id TEXT NOT NULL,
    payment_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method = 'manual'),
    state TEXT NOT NULL CHECK (state IN ('open', 'captured')),
    connection_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    captured_at TIMESTAMPTZ,
    PRIMARY KEY (store_id, payment_id)
);
