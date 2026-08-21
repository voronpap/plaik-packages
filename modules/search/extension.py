"""Search package entry point. Depends only on public plaik-sdk."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from plaik_sdk import ExtensionRuntime

_ENGINE_PATH = Path(__file__).with_name("search_engine.py")
_SPEC = importlib.util.spec_from_file_location("plaik_pkg_search_engine", _ENGINE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("cannot load search_engine.py")
_engine_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_engine_mod)

SearchEngine = _engine_mod.SearchEngine
SearchQuery = _engine_mod.SearchQuery
SearchFacets = _engine_mod.SearchFacets

_ADMIN_PATH = Path(__file__).with_name("search_admin.py")
_ADMIN_SPEC = importlib.util.spec_from_file_location(
    "plaik_pkg_search_admin", _ADMIN_PATH
)
if _ADMIN_SPEC is None or _ADMIN_SPEC.loader is None:
    raise ImportError("cannot load search_admin.py")
_admin_mod = importlib.util.module_from_spec(_ADMIN_SPEC)
_ADMIN_SPEC.loader.exec_module(_admin_mod)
register_admin = _admin_mod.register_admin


def register(runtime: ExtensionRuntime) -> None:
    if runtime.package_id != "search":
        raise ValueError("runtime package id does not match this package")

    engine = SearchEngine(runtime)
    runtime.services.register("search.query", "1.0.0", SearchQuery(engine))
    runtime.services.register("search.facets", "1.0.0", SearchFacets(engine))

    def on_catalog_changed(payload) -> None:
        del payload
        engine.rebuild_from_catalog()

    subscribe = getattr(runtime.events, "subscribe", None)
    if callable(subscribe):
        try:
            subscribe("catalog.changed", ">=1.0.0,<2.0.0", on_catalog_changed)
        except Exception as error:
            if "no compatible" not in str(error).lower():
                raise

    def handle_reindex(context) -> None:
        del context
        engine.rebuild_from_catalog()

    runtime.jobs.register("search.reindex", handle_reindex)
    register_admin(runtime, engine)
