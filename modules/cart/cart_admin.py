"""Cart Admin JSON commands. Mapping in, Mapping out."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from plaik_sdk import ExtensionRuntime


def _jsonable(value: object) -> object:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _require_id(payload: Mapping[str, Any], *, field: str) -> str:
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
        "cart.create",
        _wrap(lambda _payload: engine.create_cart()),
    )
    runtime.admin.register(
        "cart.list",
        _wrap(lambda _payload: engine.list_carts()),
    )
    runtime.admin.register(
        "cart.get",
        _wrap(lambda payload: engine.get_cart(_require_id(payload, field="cart_id"))),
    )
    runtime.admin.register(
        "cart.add",
        _wrap(
            lambda payload: engine.add_line(
                _require_id(payload, field="cart_id"),
                _require_id(payload, field="product_id"),
                payload.get("quantity", 1),
            )
        ),
    )
    runtime.admin.register(
        "cart.set",
        _wrap(
            lambda payload: engine.set_line(
                _require_id(payload, field="cart_id"),
                _require_id(payload, field="product_id"),
                payload.get("quantity"),
            )
        ),
    )
    runtime.admin.register(
        "cart.remove",
        _wrap(
            lambda payload: engine.remove_line(
                _require_id(payload, field="cart_id"),
                _require_id(payload, field="product_id"),
            )
        ),
    )
    runtime.admin.register(
        "cart.clear",
        _wrap(lambda payload: engine.clear_cart(_require_id(payload, field="cart_id"))),
    )
    runtime.admin.register(
        "cart.quote",
        _wrap(lambda payload: engine.quote(_require_id(payload, field="cart_id"))),
    )
