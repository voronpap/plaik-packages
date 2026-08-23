"""SEO projections expose only public metadata and canonical paths."""
from __future__ import annotations
from typing import Any, Mapping
from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope

def register_public(runtime: Any, query: Any) -> None:
    def public_metadata(record: Any) -> dict[str, str]:
        if not isinstance(record, Mapping):
            return {}
        return {
            key: str(record[key])
            for key in ("title", "description", "canonical")
            if key in record
        }

    def metadata(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        catalog = runtime.services.resolve("catalog.storefront", ">=1.0.0,<2.0.0")
        if catalog.get(payload["product_id"]) is None:
            return PublicResponseEnvelope(data={})
        return PublicResponseEnvelope(data=public_metadata(query.get(payload["product_id"])))
    def sitemap(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        catalog = runtime.services.resolve("catalog.storefront", ">=1.0.0,<2.0.0")
        return PublicResponseEnvelope(
            data=[f"/product/{row['id']}" for row in catalog.list()[:128]]
        )
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="metadata"), metadata)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.SITEMAP_PROJECTION, id="products"), sitemap)
