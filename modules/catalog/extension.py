"""Catalog package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("catalog_engine.py")
_SPEC = importlib.util.spec_from_file_location("plaik_pkg_catalog_engine", _ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load catalog_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

CatalogEngine = _engine_mod.CatalogEngine
CatalogQuery = _engine_mod.CatalogQuery
CatalogProducts = _engine_mod.CatalogProducts
CatalogCategories = _engine_mod.CatalogCategories
CatalogAttributes = _engine_mod.CatalogAttributes

_ADMIN_PATH = Path(__file__).with_name("catalog_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_catalog_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load catalog_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin
_PUBLIC_PATH = Path(__file__).with_name("storefront_public.py")
_PUBLIC_SPEC = importlib.util.spec_from_file_location("plaik_pkg_catalog_public", _PUBLIC_PATH)
if _PUBLIC_SPEC is None or _PUBLIC_SPEC.loader is None:
    raise ImportError("cannot load storefront_public.py")
_public_mod = importlib.util.module_from_spec(_PUBLIC_SPEC)
_PUBLIC_SPEC.loader.exec_module(_public_mod)
register_public = _public_mod.register_public


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "catalog":
        raise ValueError("runtime package id does not match this package")

    engine = CatalogEngine(runtime)
    query = CatalogQuery(engine)
    runtime.services.register("catalog.query", "1.0.0", query)
    runtime.services.register("catalog.products", "1.0.0", CatalogProducts(engine))
    runtime.services.register("catalog.categories", "1.0.0", CatalogCategories(engine))
    runtime.services.register("catalog.attributes", "1.0.0", CatalogAttributes(engine))

    def handle_reindex(context) -> None:
        products_payload = context.payload.get("products") if context.payload else None
        if not isinstance(products_payload, list):
            return
        for item in products_payload:
            if not isinstance(item, dict):
                continue
            query.upsert(item)

    runtime.jobs.register("catalog.reindex", handle_reindex)
    register_admin(runtime, engine)
    register_public(runtime, query)
