-- Catalog v1 schema. 001_init remains historical stub (BIGINT products).
DROP TABLE IF EXISTS product_attributes;
DROP TABLE IF EXISTS products;

CREATE TABLE brands (
    id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, id),
    UNIQUE (store_id, slug)
);

CREATE TABLE categories (
    id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, id),
    UNIQUE (store_id, slug),
    FOREIGN KEY (store_id, parent_id) REFERENCES categories (store_id, id)
);

CREATE TABLE attribute_definitions (
    id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('text', 'integer', 'boolean', 'select')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, id),
    UNIQUE (store_id, code)
);

CREATE TABLE attribute_options (
    id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, id),
    UNIQUE (store_id, attribute_id, code),
    FOREIGN KEY (store_id, attribute_id) REFERENCES attribute_definitions (store_id, id)
);

CREATE TABLE products (
    id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
    kind TEXT NOT NULL CHECK (kind IN ('standalone', 'parent', 'variant')),
    parent_id TEXT,
    brand_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, id),
    UNIQUE (store_id, sku),
    UNIQUE (store_id, slug),
    FOREIGN KEY (store_id, parent_id) REFERENCES products (store_id, id),
    FOREIGN KEY (store_id, brand_id) REFERENCES brands (store_id, id)
);

CREATE TABLE product_variant_axes (
    store_id TEXT NOT NULL,
    parent_product_id TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (store_id, parent_product_id, attribute_id),
    FOREIGN KEY (store_id, parent_product_id) REFERENCES products (store_id, id),
    FOREIGN KEY (store_id, attribute_id) REFERENCES attribute_definitions (store_id, id)
);

CREATE TABLE product_categories (
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    PRIMARY KEY (store_id, product_id, category_id),
    FOREIGN KEY (store_id, product_id) REFERENCES products (store_id, id),
    FOREIGN KEY (store_id, category_id) REFERENCES categories (store_id, id)
);

CREATE TABLE product_attribute_values (
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    attribute_id TEXT NOT NULL,
    value_text TEXT,
    value_integer BIGINT,
    value_boolean BOOLEAN,
    option_id TEXT,
    PRIMARY KEY (store_id, product_id, attribute_id),
    FOREIGN KEY (store_id, product_id) REFERENCES products (store_id, id),
    FOREIGN KEY (store_id, attribute_id) REFERENCES attribute_definitions (store_id, id),
    FOREIGN KEY (store_id, option_id) REFERENCES attribute_options (store_id, id)
);

CREATE TABLE product_media (
    id TEXT NOT NULL,
    store_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    storage_id TEXT NOT NULL,
    alt TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, id),
    FOREIGN KEY (store_id, product_id) REFERENCES products (store_id, id)
);
