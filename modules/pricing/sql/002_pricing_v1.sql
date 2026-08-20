-- Pricing v1 schema. 001_init remains historical stub (product_id TEXT PK, no store_id).
DROP TABLE IF EXISTS list_prices;

CREATE TABLE list_prices (
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, product_id)
);
