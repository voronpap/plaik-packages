# Cart

Official PLAIK cart module 1.0.1. Provides `cart.lines`. Cart identity is `(store_id, cart_id)` where `cart_id` is a `ResourceRef.id` string. Close-gate carts are Admin-managed; there is no guest session owner and no `owner_id` payload.

Durable tables live in the package PostgreSQL schema (`sql/001_init.sql`). When Core binds `runtime.sql`, that schema is the system of record. Isolated `plaik-sdk` package tests and hosts without a SQL connector keep an in-process engine so `register()` does not open a database session.

This package owns cart lines only. It does not read catalog, pricing, or inventory tables. Product existence is `catalog.query`; live quote is `pricing.query`. List price is not stored on the line.

Admin management is JSON commands under `cart.manage`. Storefront binding uses the frozen Default Theme slots `storefront.cart.items|summary|actions`, `storefront.header.cart`, and `storefront.product.add-to-cart`. Slot templates live under `web/`. Do not edit Default Theme.

Depends only on public `plaik-sdk`.
