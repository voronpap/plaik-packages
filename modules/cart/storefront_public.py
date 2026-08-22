"""Session-owned cart boundary; the platform supplies the opaque subject."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, engine: Any, query: Any) -> None:
    carts: dict[str, str] = {}

    def cart_for(context: Any) -> str:
        subject = getattr(getattr(context, "subject", None), "value", None)
        if not subject:
            raise ValueError("session subject required")
        if subject not in carts:
            carts[subject] = str(query.create()["cart_id"])
        return carts[subject]

    def read(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        return PublicResponseEnvelope(data=query.get(cart_for(context)) or {})

    def add(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        return PublicResponseEnvelope(data=query.add(cart_for(context), payload["product_id"], payload["quantity"]))

    def set_line(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        return PublicResponseEnvelope(data=query.set(cart_for(context), payload["product_id"], payload["quantity"]) or {})

    def remove(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        return PublicResponseEnvelope(data=query.remove(cart_for(context), payload["product_id"]) or {})

    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="cart"), read)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="add"), add)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="set"), set_line)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.ACTION, id="remove"), remove)
