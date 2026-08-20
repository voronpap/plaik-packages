"""Catalog package entry point. Depends only on public plaik-sdk."""

from plaik_sdk import ExtensionRuntime


class CatalogQuery:
    """In-process product identity for other proof-stack packages."""

    def __init__(self) -> None:
        self._products: dict[int, dict] = {}

    def upsert(self, product: dict) -> dict:
        product_id = int(product["id"])
        record = {
            "id": product_id,
            "sku": str(product.get("sku") or f"sku-{product_id}"),
            "title": str(product.get("title") or record_title(product_id)),
            "attributes": dict(product.get("attributes") or {}),
        }
        self._products[product_id] = record
        return record

    def get(self, product_id: int) -> dict | None:
        return self._products.get(int(product_id))

    def list(self) -> tuple[dict, ...]:
        return tuple(self._products[key] for key in sorted(self._products))


def record_title(product_id: int) -> str:
    return f"Product {product_id}"


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "catalog":
        raise ValueError("runtime package id does not match this package")

    query = CatalogQuery()
    query.upsert(
        {
            "id": 1,
            "sku": "AP-OIL-FILTER",
            "title": "Oil Filter",
            "attributes": {"brand": "Bosch", "category": "filters"},
        }
    )
    runtime.services.register("catalog.query", "1.0.0", query)

    def handle_reindex(context) -> None:
        products = context.payload.get("products") if context.payload else None
        if not isinstance(products, list):
            return
        for item in products:
            if not isinstance(item, dict) or "id" not in item:
                continue
            record = query.upsert(item)
            runtime.events.publish(
                "catalog.changed",
                "1.0.0",
                {"product_id": record["id"], "sku": record["sku"]},
                idempotency_key=f"catalog.changed:{record['id']}:{context.idempotency_key}",
            )

    runtime.jobs.register("catalog.reindex", handle_reindex)
