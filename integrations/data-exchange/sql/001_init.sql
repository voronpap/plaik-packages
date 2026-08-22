-- Data Exchange v1 import journal. Pointers only. No catalog tables.
CREATE TABLE import_runs (
    store_id TEXT NOT NULL,
    import_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('json', 'csv')),
    product_count BIGINT NOT NULL CHECK (product_count >= 0),
    product_ids TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, import_id)
);
