"""Bounded catalog-backed Storefront search."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def product_dto(item: Any) -> dict[str, str]:
        if not isinstance(item, Mapping):
            raise ValueError("invalid catalog product")
        return {key: str(item[key]) for key in ("id", "sku", "title")}

    def facet_dto(item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            raise ValueError("invalid search facet")
        return {
            "name": str(item["name"]),
            "value": str(item["value"]),
            "product_count": int(item["product_count"]),
        }

    def search(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        needle = str(payload.get("q") or "").strip().casefold()
        catalog = runtime.services.resolve("catalog.storefront", ">=1.0.0,<2.0.0")
        items = [item for item in catalog.list() if not needle or needle in str(item.get("title", "")).casefold() or needle in str(item.get("sku", "")).casefold()][:128]
        return PublicResponseEnvelope(data={"items": [product_dto(item) for item in items], "facets": [facet_dto(item) for item in query.facets()]})
    def page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        values = {item.name: item.values for item in getattr(context.request, "query", ())}
        return search(context, {"q": (values.get("q") or ("",))[0]})
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="search"), search)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="search"), page)
