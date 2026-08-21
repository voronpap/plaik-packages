-- Search v1 schema. 001_init remains historical stub (name+value PK, no store_id).
DROP TABLE IF EXISTS facet_values;

CREATE TABLE facet_values (
    store_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    product_count BIGINT NOT NULL DEFAULT 0 CHECK (product_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, name, value)
);
