"""Session-owned cart boundary; the platform supplies the opaque subject."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, engine: Any, query: Any) -> None:
    def public_cart(cart: Any) -> dict[str, Any]:
        if not isinstance(cart, Mapping):
            return {}
        lines = []
        for line in cart.get("lines", []):
            if isinstance(line, Mapping):
                lines.append({key: line[key] for key in ("product_id", "quantity") if key in line})
        return {"lines": lines}
    def cart_for(context: Any) -> str:
        subject = getattr(getattr(context, "subject", None), "value", None)
        if not subject:
            raise ValueError("session subject required")
        return str(engine.cart_for_subject(subject)["cart_id"])

    def read(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        return PublicResponseEnvelope(data=public_cart(query.get(cart_for(context))))

    def add(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        query.add(cart_for(context), payload["product_id"], payload["quantity"])
        return PublicResponseEnvelope(data=public_cart(query.get(cart_for(context))))

    def set_line(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        query.set(cart_for(context), payload["product_id"], payload["quantity"])
        return PublicResponseEnvelope(data=public_cart(query.get(cart_for(context))))

    def remove(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        query.remove(cart_for(context), payload["product_id"])
        return PublicResponseEnvelope(data=public_cart(query.get(cart_for(context))))

    def page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        return PublicResponseEnvelope(data={"cart": public_cart(query.get(cart_for(context)))})

    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="cart"), read)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="add"), add)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="set"), set_line)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="remove"), remove)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="cart"), page)
