# Catalog

Official PLAIK catalog module 1.0.1. Provides `catalog.products`, `catalog.categories` and `catalog.attributes`. Product identity is a string `ResourceRef.id`.

Durable tables live in the package PostgreSQL schema: `sql/001_init.sql` is the historical stub; `sql/002_catalog_v1.sql` is the v1 schema. When Core binds `runtime.sql`, that schema is the system of record. Isolated `plaik-sdk` package tests and hosts without a SQL connector keep an in-process engine so `register()` does not open a database session.

Admin management is JSON commands under `catalog.manage` (`catalog.products.*`, `catalog.categories.*`, `catalog.attributes.*`). Storefront bindings use the frozen Theme slots `storefront.collection.products`, `storefront.product.gallery`, and `storefront.product.variants`. Slot templates live under `web/` so Core install staging can project them.

Depends only on public `plaik-sdk`.
