# Payments

Official PLAIK payments module 1.0.1. Provides `payments.capture` as the offline/manual port. Payment identity is `(store_id, payment_id)`. Capture is Admin-managed. When `psp-outbound.charge` is bound, capture dispatches a recorded outbound charge before writing `captured`; otherwise capture stays manual. The payment row method remains `manual`.

This package does not read orders tables and does not store card numbers. Optional `ConnectionRef` values are pointers only; secret keys are never persisted.

Admin commands live under `payments.manage`. Storefront binding uses the frozen Default Theme slot `storefront.checkout.payment`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
