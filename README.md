# PLAIK Packages

Official installable packages for **PLAIK**.

This repository contains business modules, external integrations, installable themes and packs assembled against the public `plaik-sdk` contracts.

## 0.4 proof stack

```text
modules/catalog
modules/inventory
modules/pricing
modules/search
modules/seo
packs/auto-parts-pack
```

These packages depend only on released `plaik-sdk`. They do not import `plaik_core`. Each 1.0.x module declares Core `>=0.4.0,<0.6.0`.

## 0.5 commerce

```text
modules/cart
modules/orders
modules/shipping
modules/payments
modules/promotions
modules/checkout
packs/auto-parts-pack
```

Cart v1 is Admin-managed `(store_id, cart_id)`. Orders v1 stores a snapshot envelope after place. Shipping v1 is flat/manual methods + quote. Payments v1 is offline/manual capture with optional 1.0.x outbound dispatch. Promotions v1 is cart-level coupons against a quote. Checkout v1 orchestrates place without a Core saga.

## 0.6 integrations

```text
integrations/data-exchange
integrations/psp-outbound
packs/auto-parts-pack
```

Data Exchange v1 imports Admin JSON/CSV through `catalog.query.upsert`. PSP Outbound v1 is recorded HTTP capture behind `payments.capture`. Neither package imports `plaik_core` or stores secret values.

## Rules

- depend only on released public `plaik-sdk` interfaces;
- never import private PLAIK Core implementation details;
- never read another package's private storage directly;
- cross-package behavior uses declared services, events, hooks, slots or public APIs;
- package permissions, settings, events, services, capabilities, migrations and storage remain package-owned and namespaced.

Internal acceptance, regression and security tests, agent instructions and release-control infrastructure live in the private `plaik-internal` repository.

## License

Apache License 2.0.
