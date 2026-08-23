"""Public read-only shipping method and quote projections."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def public_method(item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            return {}
        return {key: item[key] for key in ("method_id", "name", "amount_minor", "currency", "enabled") if key in item}
    def methods(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [public_method(item) for item in query.list() if item.get("enabled", False)]})
    def quote(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        return PublicResponseEnvelope(data=public_method(query.quote(payload["shipping_method_id"])))
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="methods"), methods)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="quote"), quote)
