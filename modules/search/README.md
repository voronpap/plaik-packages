# Search

Official PLAIK search/facets module 1.0.1. Provides `search.facets`. Facet identity is `(store_id, name, value)` counted from catalog attribute maps exposed by `catalog.query`.

Durable tables live in the package PostgreSQL schema: `sql/001_init.sql` is the historical stub; `sql/002_search_v1.sql` is the v1 schema. When Core binds `runtime.sql`, that schema is the system of record. Isolated `plaik-sdk` package tests and hosts without a SQL connector keep an in-process engine so `register()` does not open a database session.

This package owns facet counts only. It does not read catalog tables. Catalog traffic is `catalog.products` / `catalog.query` / `catalog.changed`. It does not run a full-text search backend.

Admin management is JSON commands under `search.manage` (`search.facets.list|reindex`). Storefront binding uses the frozen Theme slot `storefront.search.filters`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
