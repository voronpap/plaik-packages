"""Safe public price projection."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def price(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        return PublicResponseEnvelope(data=query.get(payload["product_id"]) or {})
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="price"), price)
