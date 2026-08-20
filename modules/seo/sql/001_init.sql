-- product_id is catalog ResourceRef.id (TEXT). This package owns SEO records only.
CREATE TABLE IF NOT EXISTS seo_records (
    product_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL
);
