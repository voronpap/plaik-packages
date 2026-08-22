-- PSP outbound v1 recorded-charge journal. Pointers only. No card columns.
CREATE TABLE outbound_charges (
    store_id TEXT NOT NULL,
    payment_id TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL,
    connection_id TEXT NOT NULL DEFAULT '',
    provider_ref TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, payment_id)
);
