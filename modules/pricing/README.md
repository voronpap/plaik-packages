# Pricing

Official PLAIK pricing module 1.0.1. Provides `pricing.list`. List-price identity is `(store_id, product_id)` where `product_id` is the catalog `ResourceRef.id` string.

Durable tables live in the package PostgreSQL schema: `sql/001_init.sql` is the historical stub; `sql/002_pricing_v1.sql` is the v1 schema. When Core binds `runtime.sql`, that schema is the system of record. Isolated `plaik-sdk` package tests and hosts without a SQL connector keep an in-process engine so `register()` does not open a database session.

This package owns list prices only. It does not read catalog or inventory tables. Catalog traffic is `catalog.products` / `catalog.query` / `catalog.changed`. New catalog products do not receive an invented amount.

Admin management is JSON commands under `pricing.manage` (`pricing.list.list|get|set`). Storefront binding uses the frozen Theme slot `storefront.product.after-price`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
