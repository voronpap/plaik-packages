CREATE TABLE IF NOT EXISTS list_prices (
    product_id BIGINT PRIMARY KEY,
    amount_minor BIGINT NOT NULL,
    currency TEXT NOT NULL
);
