CREATE TABLE IF NOT EXISTS facet_values (
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    product_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (name, value)
);
