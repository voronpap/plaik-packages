# Shipping

Official PLAIK shipping module 1.0.1. Provides `shipping.methods`. Method identity is `(store_id, method_id)`. Quote is flat/manual from the stored method amount. There are no live carrier APIs.

This package does not read cart or orders tables. Checkout later copies a quote into the order snapshot.

Admin commands live under `shipping.manage`. Storefront binding uses the frozen Default Theme slot `storefront.checkout.shipping`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
