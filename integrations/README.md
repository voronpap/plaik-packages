# Integrations

Official PLAIK external-provider adapters live here.

Integrations sit behind explicit public ports/contracts, use bounded timeouts and classified retries, and must provide protocol-level idempotency before retrying irreversible side effects.

Provider credentials are never committed to this repository; extensions receive granted secrets only through supported PLAIK SDK interfaces.

Official 0.6 close-gate packages:

- `data-exchange` — Admin JSON/CSV import into `catalog.query.upsert`
- `psp-outbound` — recorded outbound capture behind `payments.capture`
