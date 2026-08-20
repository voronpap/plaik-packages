-- Catalog-owned product and attribute tables. search_path is the package schema.
CREATE TABLE IF NOT EXISTS products (
    id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS product_attributes (
    id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products (id),
    name TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS product_attributes_name_idx
    ON product_attributes (name, value);
