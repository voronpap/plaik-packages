"""Checkout package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("checkout_engine.py")
_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_checkout_engine", _ENGINE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load checkout_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

CheckoutEngine = _engine_mod.CheckoutEngine
CheckoutQuery = _engine_mod.CheckoutQuery

_ADMIN_PATH = Path(__file__).with_name("checkout_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_checkout_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load checkout_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin
_PUBLIC_SPEC = importlib.util.spec_from_file_location("plaik_pkg_checkout_public", Path(__file__).with_name("storefront_public.py"))
if _PUBLIC_SPEC is None or _PUBLIC_SPEC.loader is None: raise ImportError("cannot load storefront_public.py")
_public_mod = importlib.util.module_from_spec(_PUBLIC_SPEC); _PUBLIC_SPEC.loader.exec_module(_public_mod)
register_public = _public_mod.register_public


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "checkout":
        raise ValueError("runtime package id does not match this package")

    engine = CheckoutEngine(runtime)
    runtime.services.register("checkout.query", "1.0.0", CheckoutQuery(engine))
    register_admin(runtime, engine)
    register_public(runtime, CheckoutQuery(engine))
