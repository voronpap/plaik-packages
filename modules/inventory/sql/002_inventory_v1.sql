-- Inventory v1 schema. 001_init remains historical stub (product_id TEXT PK, no store_id).
DROP TABLE IF EXISTS stock_items;

CREATE TABLE stock_items (
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity BIGINT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, product_id)
);
