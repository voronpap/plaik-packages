"""SEO package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("seo_engine.py")
_SPEC = importlib.util.spec_from_file_location("plaik_pkg_seo_engine", _ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load seo_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

SeoEngine = _engine_mod.SeoEngine
SeoQuery = _engine_mod.SeoQuery
SeoStorefront = _engine_mod.SeoStorefront

_ADMIN_PATH = Path(__file__).with_name("seo_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location("plaik_pkg_seo_admin", _ADMIN_PATH)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load seo_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "seo":
        raise ValueError("runtime package id does not match this package")

    engine = SeoEngine(runtime)
    runtime.services.register("seo.query", "1.0.0", SeoQuery(engine))
    runtime.services.register("seo.storefront", "1.0.0", SeoStorefront(engine))

    def on_catalog_changed(payload) -> None:
        product_id = payload.get("product_id") if isinstance(payload, dict) else None
        if product_id is None:
            engine.ensure_from_catalog()
            return
        engine.ensure_one(product_id)

    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        try:
            subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)
        except Exception as error:
            if "no compatible" not in str(error).lower():
                raise

    def handle_refresh(context) -> None:
        del context
        engine.ensure_from_catalog()

    runtime.jobs.register("seo.refresh", handle_refresh)
    register_admin(runtime, engine)
