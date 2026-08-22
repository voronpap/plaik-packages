"""Payments Admin JSON commands. Mapping in, Mapping out."""

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
    runtime.admin.register("payments.create", _wrap(engine.create_payment))
    runtime.admin.register("payments.list", _wrap(lambda _payload: engine.list_payments()))
    runtime.admin.register(
        "payments.get",
        _wrap(lambda payload: engine.get_payment(_require_id(payload, field="payment_id"))),
    )
    runtime.admin.register(
        "payments.capture",
        _wrap(lambda payload: engine.capture(_require_id(payload, field="payment_id"))),
    )
