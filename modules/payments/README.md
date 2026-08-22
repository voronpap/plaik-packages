# Payments

Official PLAIK payments module 1.0.0. Provides `payments.capture` as the offline/manual port. Payment identity is `(store_id, payment_id)`. Capture is Admin-managed and does not charge a live PSP.

This package does not read orders tables and does not store card numbers. Optional `ConnectionRef` values are pointers only; secret keys are never persisted.

Admin commands live under `payments.manage`. Storefront binding uses the frozen Default Theme slot `storefront.checkout.payment`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
