-- product_id is catalog ResourceRef.id (TEXT). This package owns stock only.
CREATE TABLE IF NOT EXISTS stock_items (
    product_id TEXT PRIMARY KEY,
    quantity BIGINT NOT NULL DEFAULT 0
);
