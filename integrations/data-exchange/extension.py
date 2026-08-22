"""Data Exchange package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("data_exchange_engine.py")
_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_data_exchange_engine", _ENGINE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load data_exchange_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

DataExchangeEngine = _engine_mod.DataExchangeEngine
DataExchangeImport = _engine_mod.DataExchangeImport

_ADMIN_PATH = Path(__file__).with_name("data_exchange_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_data_exchange_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load data_exchange_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "data-exchange":
        raise ValueError("runtime package id does not match this package")

    engine = DataExchangeEngine(runtime)
    runtime.services.register(
        "data-exchange.import", "1.0.0", DataExchangeImport(engine)
    )
    register_admin(runtime, engine)
