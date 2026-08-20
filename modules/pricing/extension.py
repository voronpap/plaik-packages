"""Pricing package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("pricing_engine.py")
_SPEC = importlib.util.spec_from_file_location("plaik_pkg_pricing_engine", _ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load pricing_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

PricingEngine = _engine_mod.PricingEngine
PricingQuery = _engine_mod.PricingQuery
PricingList = _engine_mod.PricingList

_ADMIN_PATH = Path(__file__).with_name("pricing_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_pricing_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load pricing_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "pricing":
        raise ValueError("runtime package id does not match this package")

    engine = PricingEngine(runtime)
    runtime.services.register("pricing.query", "1.0.0", PricingQuery(engine))
    runtime.services.register("pricing.list", "1.0.0", PricingList(engine))

    def on_catalog_changed(payload) -> None:
        del payload
        # Catalog identity changes do not invent list prices.

    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        try:
            subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)
        except Exception as error:
            if "no compatible" not in str(error).lower():
                raise

    def handle_reprice(context) -> None:
        del context
        # Preview-compat job. Do not invent default amounts.

    runtime.jobs.register("pricing.reprice", handle_reprice)
    register_admin(runtime, engine)
