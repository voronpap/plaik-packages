-- Promotions v1 schema. Cart-level coupons only. No pricing.list writes.
CREATE TABLE promotion_coupons (
    store_id TEXT NOT NULL,
    coupon_id TEXT NOT NULL,
    code TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, coupon_id),
    UNIQUE (store_id, code)
);
