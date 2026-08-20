"""Inventory package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("inventory_engine.py")
_SPEC = importlib.util.spec_from_file_location("plaik_pkg_inventory_engine", _ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load inventory_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

InventoryEngine = _engine_mod.InventoryEngine
InventoryQuery = _engine_mod.InventoryQuery
InventoryStock = _engine_mod.InventoryStock

_ADMIN_PATH = Path(__file__).with_name("inventory_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_inventory_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load inventory_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "inventory":
        raise ValueError("runtime package id does not match this package")

    engine = InventoryEngine(runtime)
    runtime.services.register("inventory.query", "1.0.0", InventoryQuery(engine))
    runtime.services.register("inventory.stock", "1.0.0", InventoryStock(engine))

    def on_catalog_changed(payload) -> None:
        product_id = payload.get("product_id") if isinstance(payload, dict) else None
        if product_id is None:
            engine.sync_from_catalog()
            return
        try:
            engine.ensure_zero(product_id)
        except _engine_mod.InventoryError:
            return

    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        try:
            subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)
        except Exception as error:
            if "no compatible" not in str(error).lower():
                raise

    def handle_sync(context) -> None:
        del context
        engine.sync_from_catalog()

    runtime.jobs.register("inventory.sync", handle_sync)
    register_admin(runtime, engine)
