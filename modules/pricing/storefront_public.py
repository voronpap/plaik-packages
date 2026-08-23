"""Safe public price projection."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def price(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        product_id = payload["product_id"]
        catalog = runtime.services.resolve("catalog.storefront", ">=1.0.0,<2.0.0")
        if catalog.get(product_id) is None:
            return PublicResponseEnvelope(data={})
        record = query.get(product_id)
        if not isinstance(record, Mapping):
            return PublicResponseEnvelope(data={})
        return PublicResponseEnvelope(
            data={
                "product_id": str(product_id),
                "amount_minor": int(record["amount_minor"]),
                "currency": str(record["currency"]),
            }
        )
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="price"), price)
