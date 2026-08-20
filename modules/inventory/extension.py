"""Inventory package entry point. Depends only on public plaik-sdk."""

from plaik_sdk import ExtensionRuntime


class InventoryQuery:
    def __init__(self) -> None:
        self._stock: dict[int, int] = {}

    def set(self, product_id: int, quantity: int) -> None:
        self._stock[int(product_id)] = int(quantity)

    def get(self, product_id: int) -> int:
        return self._stock.get(int(product_id), 0)

    def list(self) -> tuple[dict, ...]:
        return tuple(
            {"product_id": product_id, "quantity": quantity}
            for product_id, quantity in sorted(self._stock.items())
        )


def _catalog_query(runtime: ExtensionRuntime):
    resolve = getattr(runtime.services, "resolve", None)
    if not callable(resolve):
        return None
    try:
        provider = resolve("catalog.query", ">=1.0.0,<2.0.0")
    except Exception:
        return None
    if not callable(getattr(provider, "list", None)):
        return None
    return provider


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "inventory":
        raise ValueError("runtime package id does not match this package")

    query = InventoryQuery()
    threshold = runtime.settings.get("low-stock-threshold", 4)
    default_quantity = 8 if not isinstance(threshold, int) else max(int(threshold) * 2, 1)

    def sync_from_catalog() -> None:
        catalog = _catalog_query(runtime)
        if catalog is None:
            return
        for product in catalog.list():
            product_id = int(product["id"])
            if query.get(product_id) == 0:
                query.set(product_id, default_quantity)

    def on_catalog_changed(payload) -> None:
        product_id = payload.get("product_id") if isinstance(payload, dict) else None
        if product_id is None:
            sync_from_catalog()
            return
        if query.get(int(product_id)) == 0:
            query.set(int(product_id), default_quantity)
        runtime.events.publish(
            "inventory.changed",
            "1.0.0",
            {"product_id": int(product_id), "quantity": query.get(int(product_id))},
        )

    sync_from_catalog()
    runtime.services.register("inventory.query", "1.0.0", query)
    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)

    def handle_sync(context) -> None:
        del context
        sync_from_catalog()

    runtime.jobs.register("inventory.sync", handle_sync)
