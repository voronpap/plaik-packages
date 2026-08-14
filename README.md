# PLAIK Packages

Official installable packages for **PLAIK**.

This repository contains business modules, external integrations, installable themes and packs assembled against the public `plaik-sdk` contracts.

## Planned layout

```text
modules/
integrations/
themes/
packs/
```

Commerce is one package family, not the repository boundary. Catalog, inventory, cart, checkout, orders, payments, shipping and related capabilities belong here as installable packages rather than in PLAIK Core.

## Rules

- depend only on released public `plaik-sdk` interfaces;
- never import private PLAIK Core implementation details;
- never read another package's private storage directly;
- cross-package behavior uses declared services, events, hooks, slots or public APIs;
- package permissions, settings, events, services, capabilities, migrations and storage remain package-owned and namespaced.

Internal acceptance, regression and security tests, agent instructions and release-control infrastructure live in the private `plaik-internal` repository.

## License

Apache License 2.0.
