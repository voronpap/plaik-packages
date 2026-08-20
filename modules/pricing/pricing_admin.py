"""Pricing Admin JSON commands. Mapping in, Mapping out."""

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


def _require_id(payload: Mapping[str, Any], *, field: str = "product_id") -> str:
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
        "pricing.list.list",
        _wrap(lambda _payload: engine.list_prices()),
    )
    runtime.admin.register(
        "pricing.list.get",
        _wrap(lambda payload: engine.get_price(_require_id(payload))),
    )
    runtime.admin.register(
        "pricing.list.set",
        _wrap(
            lambda payload: engine.set_price(
                _require_id(payload),
                payload.get("amount_minor"),
            )
        ),
    )
