CREATE TABLE IF NOT EXISTS stock_items (
    product_id BIGINT PRIMARY KEY,
    quantity BIGINT NOT NULL DEFAULT 0
);
