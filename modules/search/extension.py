"""Search package entry point. Depends only on public plaik-sdk."""

from plaik_sdk import ExtensionRuntime


class SearchQuery:
    def __init__(self) -> None:
        self._facets: dict[tuple[str, str], int] = {}

    def rebuild(self, products: tuple[dict, ...]) -> None:
        counts: dict[tuple[str, str], int] = {}
        for product in products:
            attributes = product.get("attributes") if isinstance(product, dict) else None
            if not isinstance(attributes, dict):
                continue
            for name, value in attributes.items():
                key = (str(name), str(value))
                counts[key] = counts.get(key, 0) + 1
        self._facets = counts

    def facets(self) -> tuple[dict, ...]:
        return tuple(
            {"name": name, "value": value, "product_count": count}
            for (name, value), count in sorted(self._facets.items())
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
    if runtime.package_id != "search":
        raise ValueError("runtime package id does not match this package")

    query = SearchQuery()

    def reindex() -> None:
        catalog = _catalog_query(runtime)
        query.rebuild(catalog.list() if catalog is not None else ())

    def on_catalog_changed(payload) -> None:
        del payload
        reindex()
        runtime.events.publish(
            "search.reindexed",
            "1.0.0",
            {"facet_count": len(query.facets())},
        )

    reindex()
    runtime.services.register("search.query", "1.0.0", query)
    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)

    def handle_reindex(context) -> None:
        del context
        reindex()

    runtime.jobs.register("search.reindex", handle_reindex)
