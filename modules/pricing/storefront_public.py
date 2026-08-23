"""Safe public price projections."""
from __future__ import annotations

from typing import Any, Mapping

from plaik_sdk import PublicHandlerRef
from plaik_contracts import PublicDeclarationKind, PublicResponseEnvelope


def _published_ids(catalog: Any) -> tuple[str, ...]:
    lightweight = getattr(catalog, "published_ids", None)
    if callable(lightweight):
        return tuple(str(value) for value in lightweight())[:128]

    return tuple(
        str(item["id"])
        for item in catalog.list()[:128]
        if isinstance(item, Mapping) and item.get("id")
    )


def register_public(runtime: Any, query: Any) -> None:
    def price(
        context: Any,
        payload: Mapping[str, Any],
    ) -> PublicResponseEnvelope:
        del context
        product_id = payload["product_id"]

        catalog = runtime.services.resolve(
            "catalog.storefront",
            ">=1.0.0,<2.0.0",
        )
        if catalog.get(product_id) is None:
            return PublicResponseEnvelope(data={})

        record = query.get(product_id)
        if not isinstance(record, Mapping):
            return PublicResponseEnvelope(data={})

        return PublicResponseEnvelope(
            data={
                "product_id": str(product_id),
                "amount_minor": int(record["amount_minor"]),
                "currency": str(record["currency"]),
            }
        )

    def prices(
        context: Any,
        payload: Mapping[str, Any],
    ) -> PublicResponseEnvelope:
        del context, payload

        catalog = runtime.services.resolve(
            "catalog.storefront",
            ">=1.0.0,<2.0.0",
        )
        product_ids = _published_ids(catalog)

        items = []
        for record in query.list_for(product_ids):
            if not isinstance(record, Mapping):
                continue
            items.append(
                {
                    "product_id": str(record["product_id"]),
                    "amount_minor": int(record["amount_minor"]),
                    "currency": str(record["currency"]),
                }
            )

        return PublicResponseEnvelope(data={"items": items})

    runtime.public.register(
        PublicHandlerRef(
            kind=PublicDeclarationKind.QUERY,
            id="price",
        ),
        price,
    )
    runtime.public.register(
        PublicHandlerRef(
            kind=PublicDeclarationKind.QUERY,
            id="prices",
        ),
        prices,
    )
