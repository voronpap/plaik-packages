"""Cart package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("cart_engine.py")
_SPEC = importlib.util.spec_from_file_location("plaik_pkg_cart_engine", _ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load cart_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

CartEngine = _engine_mod.CartEngine
CartQuery = _engine_mod.CartQuery

_ADMIN_PATH = Path(__file__).with_name("cart_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location("plaik_pkg_cart_admin", _ADMIN_PATH)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load cart_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "cart":
        raise ValueError("runtime package id does not match this package")

    engine = CartEngine(runtime)
    runtime.services.register("cart.query", "1.0.0", CartQuery(engine))
    register_admin(runtime, engine)
