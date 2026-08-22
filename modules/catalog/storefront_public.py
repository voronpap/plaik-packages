"""Bounded anonymous Catalog projections for the PLAIK public boundary."""

from __future__ import annotations

from typing import Any, Mapping

from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope


def register_public(runtime: Any, query: Any, categories: Any) -> None:
    def public_category(item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            return {}
        return {key: item[key] for key in ("id", "slug", "name", "parent_id") if key in item}
    def products(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": list(query.list())})

    def product(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        item = query.get(payload["product_id"])
        return PublicResponseEnvelope(data=item or {})

    def category(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        return PublicResponseEnvelope(data=public_category(categories.get(payload["category_id"])))

    def categories_list(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [public_category(item) for item in categories.list()]})

    def home(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": list(query.list())[:24]})

    def catalog_page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": list(query.list())[:128], "categories": [public_category(item) for item in categories.list()[:128]]})

    def category_page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        resource_id = getattr(getattr(context, "request", None), "resource_id", None)
        return PublicResponseEnvelope(data={"category": public_category(categories.get(resource_id)), "items": list(query.list())[:128]})

    def product_page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        resource_id = getattr(getattr(context, "request", None), "resource_id", None)
        return PublicResponseEnvelope(data={"product": query.get(resource_id) or {}})

    def sitemap(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data=[f"/product/{item['id']}" for item in query.list()[:128] if item.get("id")])

    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="products"), products)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="product"), product)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="category"), category)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="categories"), categories_list)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="home"), home)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="catalog"), catalog_page)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="category"), category_page)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="product"), product_page)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.SITEMAP_PROJECTION, id="products"), sitemap)
