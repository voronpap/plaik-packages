"""Coupon application derived from the caller-owned cart only."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def apply(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        subject = getattr(getattr(context, "subject", None), "value", None)
        if not subject:
            raise ValueError("session subject required")
        shopper = runtime.services.resolve("cart.shopper", ">=1.0.0,<2.0.0")
        cart = shopper.for_subject(subject)
        quoted = runtime.services.resolve("cart.query", ">=1.0.0,<2.0.0").quote(cart["cart_id"])
        goods = sum(int(line["amount_minor"]) * int(line["quantity"]) for line in quoted["lines"])
        return PublicResponseEnvelope(data=query.apply({"code": payload["code"], "goods_minor": goods, "currency": quoted["lines"][0]["currency"] if quoted["lines"] else ""}))
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="apply"), apply)
