-- Orders v1 schema. Immutable lines/amounts after place. payment_state may move unpaid → paid.
CREATE TABLE orders (
    store_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    contact_name TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '',
    contact_phone TEXT NOT NULL DEFAULT '',
    address_line TEXT NOT NULL DEFAULT '',
    address_city TEXT NOT NULL DEFAULT '',
    address_postal TEXT NOT NULL DEFAULT '',
    address_country TEXT NOT NULL DEFAULT '',
    shipping_method_id TEXT NOT NULL DEFAULT '',
    shipping_amount_minor BIGINT NOT NULL DEFAULT 0 CHECK (shipping_amount_minor >= 0),
    discount_amount_minor BIGINT NOT NULL DEFAULT 0 CHECK (discount_amount_minor >= 0),
    goods_amount_minor BIGINT NOT NULL CHECK (goods_amount_minor >= 0),
    payable_amount_minor BIGINT NOT NULL CHECK (payable_amount_minor >= 0),
    currency TEXT NOT NULL,
    payment_state TEXT NOT NULL CHECK (payment_state IN ('unpaid', 'paid')),
    placed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, order_id)
);

CREATE TABLE order_lines (
    store_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    title TEXT NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity >= 1),
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, order_id, product_id)
);
