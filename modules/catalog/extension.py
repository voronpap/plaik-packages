"""Catalog package entry point. Depends only on public plaik-sdk."""

from plaik_sdk import ExtensionRuntime


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "catalog":
        raise ValueError("runtime package id does not match this package")

    def handle_reindex(context) -> None:
        del context

    runtime.jobs.register("catalog.reindex", handle_reindex)
    runtime.slots.bind(
        "storefront.collection.products",
        "1.0.0",
        "templates/product-grid.html",
    )
