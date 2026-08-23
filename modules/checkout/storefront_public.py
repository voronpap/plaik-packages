"""Session-bound checkout projection and place action."""
from __future__ import annotations
import hashlib
import json
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def public_cart(cart: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "lines": [
                {
                    "product_id": str(line["product_id"]),
                    "quantity": int(line["quantity"]),
                }
                for line in cart.get("lines", [])
                if isinstance(line, Mapping)
            ]
        }

    def public_quote(quote: Mapping[str, Any]) -> dict[str, Any]:
        lines = []
        for line in quote.get("lines", []):
            if not isinstance(line, Mapping):
                continue
            item = {
                "product_id": str(line["product_id"]),
                "quantity": int(line["quantity"]),
            }
            if isinstance(line.get("amount_minor"), int) and not isinstance(line.get("amount_minor"), bool):
                item["amount_minor"] = int(line["amount_minor"])
            if isinstance(line.get("currency"), str):
                item["currency"] = line["currency"]
            lines.append(item)
        return {
            "lines": lines,
            "goods_minor": int(quote.get("goods_minor") or 0),
            "currency": str(quote.get("currency") or ""),
        }

    def public_method(method: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "method_id": str(method["method_id"]),
            "name": str(method["name"]),
            "amount_minor": int(method["amount_minor"]),
            "currency": str(method["currency"]),
        }
    def cart_for(context: Any) -> Mapping[str, Any]:
        subject = getattr(getattr(context, "subject", None), "value", None)
        if not subject:
            raise ValueError("session subject required")
        return runtime.services.resolve("cart.shopper", ">=1.0.0,<2.0.0").for_subject(subject)
    def preview(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        cart = cart_for(context)
        quote = runtime.services.resolve("cart.query", ">=1.0.0,<2.0.0").quote(cart["cart_id"])
        methods = runtime.services.resolve("shipping.query", ">=1.0.0,<2.0.0").list()
        return PublicResponseEnvelope(data={"cart": public_cart(cart), "quote": public_quote(quote), "shipping_methods": [public_method(item) for item in methods if item.get("enabled", False)], "payment_method": "manual"})
    def place(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        if payload.get("payment_method", "manual") != "manual":
            raise ValueError("only manual payment is supported")
        cart = cart_for(context)
        idem = getattr(getattr(context, "idempotency", None), "value", None)
        if not idem:
            raise ValueError("idempotency reference required")
        request = dict(payload)
        request["cart_id"] = cart["cart_id"]
        request["idempotency_key"] = idem
        request["_public_subject"] = getattr(context.subject, "value", "")
        request["_public_fingerprint"] = hashlib.sha256(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        request.pop("payment_method", None)
        result = query.place(request)
        return PublicResponseEnvelope(data={key: result[key] for key in ("order_id", "payment_state", "goods_amount_minor", "shipping_amount_minor", "discount_amount_minor", "payable_amount_minor", "currency") if key in result})
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="preview"), preview)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="place"), place)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="checkout"), lambda context, payload: preview(context, payload))
