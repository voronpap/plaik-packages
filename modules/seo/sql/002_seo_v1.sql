-- SEO v1 schema. 001_init remains historical stub (product_id TEXT PK, no store_id).
DROP TABLE IF EXISTS seo_records;

CREATE TABLE seo_records (
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    canonical TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, product_id)
);
