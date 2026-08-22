"""The first Storefront payment surface is deliberately manual/offline only."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any) -> None:
    def methods(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [{"id": "manual", "label": "Manual payment", "offline": True}]})
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="methods"), methods)
