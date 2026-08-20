"""Pricing package entry point. Depends only on public plaik-sdk."""

from plaik_sdk import ExtensionRuntime


class PricingQuery:
    def __init__(self, currency: str) -> None:
        self.currency = currency
        self._prices: dict[str, dict] = {}

    def set(self, product_id, amount_minor: int) -> dict:
        record = {
            "product_id": str(product_id),
            "amount_minor": int(amount_minor),
            "currency": self.currency,
        }
        self._prices[str(product_id)] = record
        return record

    def get(self, product_id) -> dict | None:
        return self._prices.get(str(product_id))

    def list(self) -> tuple[dict, ...]:
        return tuple(self._prices[key] for key in sorted(self._prices))


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
    if runtime.package_id != "pricing":
        raise ValueError("runtime package id does not match this package")

    currency = runtime.settings.get("currency") or "UAH"
    query = PricingQuery(str(currency))

    def sync_from_catalog() -> None:
        catalog = _catalog_query(runtime)
        if catalog is None:
            return
        for product in catalog.list():
            product_id = str(product["id"])
            if query.get(product_id) is None:
                query.set(product_id, 1990)

    def on_catalog_changed(payload) -> None:
        del payload
        sync_from_catalog()
        runtime.events.publish("pricing.changed", "1.0.0", {"currency": query.currency})

    sync_from_catalog()
    runtime.services.register("pricing.query", "1.0.0", query)
    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)

    def handle_reprice(context) -> None:
        del context
        sync_from_catalog()

    runtime.jobs.register("pricing.reprice", handle_reprice)
