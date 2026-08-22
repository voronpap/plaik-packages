ALTER TABLE carts ADD COLUMN IF NOT EXISTS owner_subject TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS carts_store_owner_subject
    ON carts (store_id, owner_subject) WHERE owner_subject IS NOT NULL;
