"""Payments package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("payments_engine.py")
_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_payments_engine", _ENGINE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load payments_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

PaymentsEngine = _engine_mod.PaymentsEngine
PaymentsQuery = _engine_mod.PaymentsQuery

_ADMIN_PATH = Path(__file__).with_name("payments_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_payments_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load payments_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "payments":
        raise ValueError("runtime package id does not match this package")

    engine = PaymentsEngine(runtime)
    runtime.services.register("payments.query", "1.0.0", PaymentsQuery(engine))
    register_admin(runtime, engine)
