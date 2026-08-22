# Checkout

Official PLAIK checkout module 1.0.1. Provides `checkout.place`. Place is an orchestrator: it quotes the cart, applies an optional coupon, quotes shipping, adjusts inventory, snapshots the order, captures a manual payment, marks the order paid, and clears the cart.

This package does not read sibling tables. Compensation after a failed place is owned here. Business facts stay in cart, orders, shipping, payments, promotions, inventory, and catalog.

Admin commands live under `checkout.manage`. Storefront binding uses the frozen Default Theme slot `storefront.checkout.customer`. Slot templates live under `web/`.

Depends only on public `plaik-sdk`.
