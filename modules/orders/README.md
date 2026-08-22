# Orders

Official PLAIK orders module 1.0.0. Provides `orders.records`. Order identity is `(store_id, order_id)`. Place accepts a snapshot payload (lines, contact/address fields, shipping/discount amounts). Lines and money are immutable after place. `payment_state` may move `unpaid → paid`.

This package does not read cart, catalog, or pricing tables. Checkout later composes those modules into the snapshot.

Admin commands live under `orders.manage`. Storefront binding uses the frozen Default Theme slot `storefront.checkout.review`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
