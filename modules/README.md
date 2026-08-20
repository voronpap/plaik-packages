# Modules

Official PLAIK business-domain packages live here.

0.4 proof stack:

- `catalog` — products and attributes (`catalog.products`)
- `inventory` — stock (`inventory.stock`)
- `pricing` — list prices (`pricing.list`)
- `search` — facets (`search.facets`)
- `seo` — storefront SEO (`seo.storefront`)

Modules own their data and rules. They may expose versioned services/events/hooks through `plaik-sdk`, but must not import private PLAIK Core implementation details or access another package's private storage directly.

A catalog product reference is the catalog `ResourceRef.id` string. Sibling SQL must store it as `TEXT`, not `BIGINT`. Inventory owns stock; it depends on `catalog.products` / `catalog.query` / `catalog.changed`, not catalog tables. Module slot templates live under `web/`.
