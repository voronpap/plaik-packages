# Data Exchange

Official PLAIK integration 1.0.0. Admin-managed JSON/CSV import into catalog through `catalog.query.upsert`. Product identity is a string `ResourceRef.id`. Payload `store_id` / `owner_id` are ignored; `store_id` is `ExtensionRuntime.store_id`.

This package does not read catalog tables, does not fetch URLs, and does not import XML. Replay of the same `import_id` returns the journaled result without a second upsert.

Depends only on public `plaik-sdk`.
