"""Bounded anonymous Catalog projections for the PLAIK public boundary."""

from __future__ import annotations

from typing import Any, Mapping

from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope


def register_public(runtime: Any, storefront: Any) -> None:
    def product_dto(item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            raise ValueError("not found")
        return {key: str(item[key]) for key in ("id", "sku", "title")}

    def category_dto(item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            raise ValueError("not found")
        return {key: str(item[key]) for key in ("id", "slug", "name")}

    def products(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [product_dto(item) for item in storefront.list()]})

    def product(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        item = storefront.get(payload["product_id"])
        return PublicResponseEnvelope(data=product_dto(item))

    def category(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context
        return PublicResponseEnvelope(data=category_dto(storefront.category(payload["category_id"])))

    def categories_list(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [category_dto(item) for item in storefront.categories()]})

    def home(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [product_dto(item) for item in storefront.list()[:24]]})

    def catalog_page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data={"items": [product_dto(item) for item in storefront.list()[:128]], "categories": [category_dto(item) for item in storefront.categories()[:128]]})

    def category_page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        resource_id = getattr(getattr(context, "request", None), "resource_id", None)
        return PublicResponseEnvelope(data={"category": category_dto(storefront.category(resource_id)), "items": [product_dto(item) for item in storefront.products(resource_id)[:128]]})

    def product_page(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del payload
        resource_id = getattr(getattr(context, "request", None), "resource_id", None)
        return PublicResponseEnvelope(data={"product": product_dto(storefront.get(resource_id))})

    def sitemap(context: Any, payload: Mapping[str, Any]) -> PublicResponseEnvelope:
        del context, payload
        return PublicResponseEnvelope(data=[f"/product/{item['id']}" for item in storefront.list()[:128] if item.get("id")])

    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="products"), products)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="product"), product)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="category"), category)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.QUERY, id="categories"), categories_list)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="home"), home)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="catalog"), catalog_page)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="category"), category_page)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.PAGE_PROJECTION, id="product"), product_page)
    runtime.public.register(PublicHandlerRef(kind=PublicDeclarationKind.SITEMAP_PROJECTION, id="products"), sitemap)
