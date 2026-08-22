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

These packages depend only on released `plaik-sdk`. They do not import `plaik_core`. Each 1.0.x module declares Core `>=0.4.0,<0.5.0`.

## 0.5 commerce

```text
modules/cart
```

Cart v1 is Admin-managed `(store_id, cart_id)`. Guest sessions, checkout, orders, payments, shipping and promotions follow later in 0.5.

## Rules

- depend only on released public `plaik-sdk` interfaces;
- never import private PLAIK Core implementation details;
- never read another package's private storage directly;
- cross-package behavior uses declared services, events, hooks, slots or public APIs;
- package permissions, settings, events, services, capabilities, migrations and storage remain package-owned and namespaced.

Internal acceptance, regression and security tests, agent instructions and release-control infrastructure live in the private `plaik-internal` repository.

## License

Apache License 2.0.
