# SEO

Official PLAIK SEO module 1.0.0. Provides `seo.storefront`. Record identity is `(store_id, product_id)` where `product_id` is the catalog `ResourceRef.id` string.

Durable tables live in the package PostgreSQL schema: `sql/001_init.sql` is the historical stub; `sql/002_seo_v1.sql` is the v1 schema. When Core binds `runtime.sql`, that schema is the system of record. Isolated `plaik-sdk` package tests and hosts without a SQL connector keep an in-process engine so `register()` does not open a database session.

This package owns storefront SEO records only. It does not read catalog tables. Catalog traffic is `catalog.products` / `catalog.query` / `catalog.changed`. New catalog products receive an ensured title and canonical; catalog events do not overwrite operator `set` values.

Admin management is JSON commands under `seo.manage` (`seo.records.list|get|set`). Storefront binding uses the frozen Theme slot `storefront.seo.structured-data`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
