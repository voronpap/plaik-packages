# Modules

Official PLAIK business-domain packages live here.

0.4 proof stack:

- `catalog` — products and attributes (`catalog.products`)
- `inventory` — stock (`inventory.stock` 1.0.0; identity `(store_id, product_id)`)
- `pricing` — list prices (`pricing.list` 1.0.0; identity `(store_id, product_id)`)
- `search` — facets (`search.facets` 1.0.0; identity `(store_id, name, value)`)
- `seo` — storefront SEO (`seo.storefront` 1.0.0; identity `(store_id, product_id)`)

0.5 commerce:

- `cart` — Admin-managed carts (`cart.lines` 1.0.0; identity `(store_id, cart_id)`)
- `orders` — placed orders (`orders.records` 1.0.0; identity `(store_id, order_id)`)

Modules own their data and rules. They may expose versioned services/events/hooks through `plaik-sdk`, but must not import private PLAIK Core implementation details or access another package's private storage directly.

A catalog product reference is the catalog `ResourceRef.id` string. Sibling SQL must store it as `TEXT`, not `BIGINT`. Inventory owns stock; it depends on `catalog.products` / `catalog.query` / `catalog.changed`, not catalog tables. Module slot templates live under `web/`.
