-- Cart v1 schema. Admin-managed (store_id, cart_id). No owner columns.
CREATE TABLE carts (
    store_id TEXT NOT NULL,
    cart_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, cart_id)
);

CREATE TABLE cart_lines (
    store_id TEXT NOT NULL,
    cart_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, cart_id, product_id)
);
