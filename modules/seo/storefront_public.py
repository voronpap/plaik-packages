"""SEO projections expose only public metadata and canonical paths."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def metadata(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        return PublicResponseEnvelope(data=query.get(payload["product_id"]) or {})
    def sitemap(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data=[f"/product/{row['product_id']}" for row in query.list()[:128]])
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="metadata"), metadata)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.SITEMAP_PROJECTION, id="products"), sitemap)
