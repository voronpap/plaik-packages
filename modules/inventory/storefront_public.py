"""Safe public inventory projections."""
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
    def availability(
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

        return PublicResponseEnvelope(
            data={
                "product_id": product_id,
                "quantity": query.get(product_id),
            }
        )

    def availability_list(
        context: Any,
        payload: Mapping[str, Any],
    ) -> PublicResponseEnvelope:
        del context, payload

        catalog = runtime.services.resolve(
            "catalog.storefront",
            ">=1.0.0,<2.0.0",
        )
        product_ids = _published_ids(catalog)

        items = [
            {
                "product_id": str(record["product_id"]),
                "quantity": int(record["quantity"]),
            }
            for record in query.list_for(product_ids)
            if isinstance(record, Mapping)
        ]

        return PublicResponseEnvelope(data={"items": items})

    runtime.public.register(
        PublicHandlerRef(
            kind=PublicDeclarationKind.QUERY,
            id="availability",
        ),
        availability,
    )
    runtime.public.register(
        PublicHandlerRef(
            kind=PublicDeclarationKind.QUERY,
            id="availability-list",
        ),
        availability_list,
    )
