"""Catalog Admin JSON commands. Mapping in, Mapping out."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from plaik_sdk import ExtensionRuntime

COMMANDS = (
    "catalog.products.list",
    "catalog.products.get",
    "catalog.products.create",
    "catalog.products.update",
    "catalog.products.archive",
    "catalog.categories.list",
    "catalog.categories.get",
    "catalog.categories.create",
    "catalog.categories.update",
    "catalog.attributes.list",
    "catalog.attributes.create",
    "catalog.attributes.update",
    "catalog.attributes.options",
)


def _jsonable(value: object) -> object:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _require_id(payload: Mapping[str, Any], *, field: str = "id") -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is required")
    return value


def _wrap(work: Callable[[dict[str, Any]], object]):
    def handler(payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            return {"ok": False, "error": "payload must be an object"}
        try:
            return {"ok": True, "result": _jsonable(work(dict(payload)))}
        except ValueError as error:
            return {"ok": False, "error": str(error)}

    return handler


def register_admin(runtime: ExtensionRuntime, engine: Any) -> None:
    runtime.admin.register(
        "catalog.products.list",
        _wrap(lambda _payload: engine.list_products()),
    )
    runtime.admin.register(
        "catalog.products.get",
        _wrap(lambda payload: engine.get_product(_require_id(payload))),
    )
    runtime.admin.register(
        "catalog.products.create",
        _wrap(lambda payload: engine.create_product(payload)),
    )
    runtime.admin.register(
        "catalog.products.update",
        _wrap(
            lambda payload: engine.update_product(
                _require_id(payload),
                {key: value for key, value in payload.items() if key != "id"},
            )
        ),
    )
    runtime.admin.register(
        "catalog.products.archive",
        _wrap(lambda payload: engine.archive_product(_require_id(payload))),
    )
    runtime.admin.register(
        "catalog.categories.list",
        _wrap(lambda _payload: engine.list_categories()),
    )
    runtime.admin.register(
        "catalog.categories.get",
        _wrap(lambda payload: engine.get_category(_require_id(payload))),
    )
    runtime.admin.register(
        "catalog.categories.create",
        _wrap(lambda payload: engine.create_category(payload)),
    )
    runtime.admin.register(
        "catalog.categories.update",
        _wrap(
            lambda payload: engine.update_category(
                _require_id(payload),
                {key: value for key, value in payload.items() if key != "id"},
            )
        ),
    )
    runtime.admin.register(
        "catalog.attributes.list",
        _wrap(lambda _payload: engine.list_attributes()),
    )
    runtime.admin.register(
        "catalog.attributes.create",
        _wrap(lambda payload: engine.create_attribute(payload)),
    )
    runtime.admin.register(
        "catalog.attributes.update",
        _wrap(
            lambda payload: engine.update_attribute(
                _require_id(payload),
                {key: value for key, value in payload.items() if key != "id"},
            )
        ),
    )

    def list_options(payload: dict[str, Any]) -> object:
        attribute_id = payload.get("attribute_id")
        if not isinstance(attribute_id, str) or not attribute_id:
            attribute_id = _require_id(payload)
        return engine.list_options(attribute_id)

    runtime.admin.register("catalog.attributes.options", _wrap(list_options))
