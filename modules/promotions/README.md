# Promotions

Official PLAIK promotions module 1.0.1. Provides `promotions.coupons`. Coupon identity is `(store_id, coupon_id)` with a unique `code` per store. Apply returns a cart-level discount against a quote and does not write `pricing.list`.

This package does not read cart, orders, or pricing tables. Checkout later copies `discount_amount_minor` into the order snapshot.

Admin commands live under `promotions.manage`. Storefront binding uses the frozen Default Theme slot `storefront.checkout.review`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
