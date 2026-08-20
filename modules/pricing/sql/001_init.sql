-- product_id is catalog ResourceRef.id (TEXT). This package owns list prices only.
CREATE TABLE IF NOT EXISTS list_prices (
    product_id TEXT PRIMARY KEY,
    amount_minor BIGINT NOT NULL,
    currency TEXT NOT NULL
);
