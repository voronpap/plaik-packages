"""Bounded anonymous Catalog projections for the PLAIK public boundary."""

from __future__ import annotations

from typing import Any, Mapping

from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope


def register_public(runtime: Any, query: Any) -> None:
    def products(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": list(query.list())})

    def product(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        item = query.get(payload["product_id"])
        return PublicResponseEnvelope(data=item or {})

    def sitemap(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data=[{"id": item.get("id"), "slug": item.get("slug")} for item in query.list()])

    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="products"), products)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="product"), product)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.SITEMAP_PROJECTION, id="products"), sitemap)
