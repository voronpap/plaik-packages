"""SEO package entry point. Depends only on public plaik-sdk."""

from plaik_sdk import ExtensionRuntime


class SeoQuery:
    def __init__(self, host: str) -> None:
        self.host = host
        self._records: dict[int, dict] = {}

    def upsert(self, product: dict) -> dict:
        product_id = int(product["id"])
        record = {
            "product_id": product_id,
            "title": str(product.get("title") or f"Product {product_id}"),
            "canonical": f"https://{self.host}/p/{product.get('sku') or product_id}",
        }
        self._records[product_id] = record
        return record

    def get(self, product_id: int) -> dict | None:
        return self._records.get(int(product_id))

    def list(self) -> tuple[dict, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


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
    if runtime.package_id != "seo":
        raise ValueError("runtime package id does not match this package")

    query = SeoQuery(str(runtime.settings.get("canonical-host") or "shop.example.test"))

    def refresh() -> None:
        catalog = _catalog_query(runtime)
        if catalog is None:
            return
        for product in catalog.list():
            query.upsert(product)

    def on_catalog_changed(payload) -> None:
        del payload
        refresh()
        runtime.events.publish("seo.changed", "1.0.0", {"count": len(query.list())})

    refresh()
    runtime.services.register("seo.query", "1.0.0", query)
    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)

    def handle_refresh(context) -> None:
        del context
        refresh()

    runtime.jobs.register("seo.refresh", handle_refresh)
