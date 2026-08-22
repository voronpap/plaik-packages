"""Safe public inventory projection."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def availability(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        product_id = payload["product_id"]
        return PublicResponseEnvelope(data={"product_id": product_id, "quantity": query.get(product_id)})
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="availability"), availability)
