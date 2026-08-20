# Modules

Official PLAIK business-domain packages live here.

0.4 proof stack:

- `catalog` — products and attributes (`catalog.products`)
- `inventory` — stock (`inventory.stock`)
- `pricing` — list prices (`pricing.list`)
- `search` — facets (`search.facets`)
- `seo` — storefront SEO (`seo.storefront`)

Modules own their data and rules. They may expose versioned services/events/hooks through `plaik-sdk`, but must not import private PLAIK Core implementation details or access another package's private storage directly.
