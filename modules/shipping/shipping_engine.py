"""Shipping 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")


class ShippingError(ValueError):
    """A shipping command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise ShippingError(f"invalid {field}")
    return value


def _require_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShippingError("name is required")
    return value.strip()


def _require_amount(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShippingError(f"invalid {field}")
    if value < 0:
        raise ShippingError(f"{field} must be >= 0")
    return value


def _require_currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise ShippingError("invalid currency")
    return value


def _require_enabled(value: object, *, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise ShippingError("invalid enabled")
        return default
    if not isinstance(value, bool):
        raise ShippingError("invalid enabled")
    return value


def _iso(value: object) -> str:
    converter = getattr(value, "isoformat", None)
    if callable(converter):
        return str(converter())
    return str(value)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    return bool(value)


def _sql_unbound(error: BaseException) -> bool:
    text = str(error).lower()
    if "no longer bound" in text or "connection failed" in text:
        return False
    return "package sql is unavailable" in text


def _event_key(contract: str, entity_id: str, action: str, stamp: str) -> str:
    compact = stamp.replace("+", "p").replace(":", "").replace(".", "")
    return f"{contract}:{entity_id}:{action}:{compact}"[:128]


def _row_str(row: Mapping[str, Any], key: str) -> str:
    return str(row[key])


def _method_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "method_id": _row_str(row, "method_id"),
        "name": _row_str(row, "name"),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
        "enabled": _as_bool(row["enabled"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _quote_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "method_id": _row_str(row, "method_id"),
        "name": _row_str(row, "name"),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
    }


class ShippingEngine:
    """Per-store flat/manual shipping methods. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._methods: dict[str, dict[str, Any]] = {}

    def _using_sql(self) -> bool:
        if self._mode is not None:
            return self._mode == "sql"
        try:
            with self.runtime.sql.transaction() as tx:
                tx.fetchone("SELECT 1")
        except Exception as error:
            if _sql_unbound(error):
                self._mode = "memory"
                return False
            raise
        self._mode = "sql"
        return True

    def create_method(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ShippingError("payload must be an object")
        stamp = _now()
        method_id = _new_id()
        record = {
            "store_id": self.store_id,
            "method_id": method_id,
            "name": _require_name(payload.get("name")),
            "amount_minor": _require_amount(
                payload.get("amount_minor"), field="amount_minor"
            ),
            "currency": _require_currency(payload.get("currency")),
            "enabled": _require_enabled(payload.get("enabled"), default=True),
            "created_at": stamp,
            "updated_at": stamp,
        }
        self._write(record, insert=True)
        self._publish(method_id, "created", stamp)
        return _method_record(record)

    def get_method(self, method_id: object) -> dict[str, Any] | None:
        method_id = _require_id(method_id, field="method_id")
        row = self._load(method_id)
        if row is None:
            return None
        return _method_record(row)

    def list_methods(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                _method_record(self._methods[method_id])
                for method_id in sorted(self._methods)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, method_id, name, amount_minor, currency, "
                "enabled, created_at, updated_at FROM shipping_methods "
                "WHERE store_id = %s ORDER BY method_id",
                (self.store_id,),
            )
        return tuple(_method_record(row) for row in rows)

    def set_method(self, method_id: object, payload: Mapping[str, Any]) -> dict[str, Any]:
        method_id = _require_id(method_id, field="method_id")
        if not isinstance(payload, Mapping):
            raise ShippingError("payload must be an object")
        current = self._load(method_id)
        if current is None:
            raise ShippingError("unknown method")
        stamp = _now()
        record = {
            "store_id": self.store_id,
            "method_id": method_id,
            "name": _require_name(payload["name"])
            if "name" in payload
            else _row_str(current, "name"),
            "amount_minor": _require_amount(
                payload["amount_minor"], field="amount_minor"
            )
            if "amount_minor" in payload
            else int(current["amount_minor"]),
            "currency": _require_currency(payload["currency"])
            if "currency" in payload
            else _row_str(current, "currency"),
            "enabled": _require_enabled(payload["enabled"])
            if "enabled" in payload
            else _as_bool(current["enabled"]),
            "created_at": _iso(current["created_at"]),
            "updated_at": stamp,
        }
        self._write(record, insert=False)
        self._publish(method_id, "set", stamp)
        return _method_record(record)

    def quote(self, method_id: object) -> dict[str, Any]:
        method_id = _require_id(method_id, field="method_id")
        row = self._load(method_id)
        if row is None:
            raise ShippingError("unknown method")
        if not _as_bool(row["enabled"]):
            raise ShippingError("method is disabled")
        return _quote_record(row)

    def _load(self, method_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._methods.get(method_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, method_id, name, amount_minor, currency, "
                "enabled, created_at, updated_at FROM shipping_methods "
                "WHERE store_id = %s AND method_id = %s",
                (self.store_id, method_id),
            )
        if row is None:
            return None
        return dict(row)

    def _write(self, record: Mapping[str, Any], *, insert: bool) -> None:
        if not self._using_sql():
            self._methods[str(record["method_id"])] = dict(record)
            return
        if insert:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO shipping_methods ("
                    "store_id, method_id, name, amount_minor, currency, "
                    "enabled, created_at, updated_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        record["store_id"],
                        record["method_id"],
                        record["name"],
                        record["amount_minor"],
                        record["currency"],
                        record["enabled"],
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "UPDATE shipping_methods SET name = %s, amount_minor = %s, "
                "currency = %s, enabled = %s, updated_at = %s "
                "WHERE store_id = %s AND method_id = %s",
                (
                    record["name"],
                    record["amount_minor"],
                    record["currency"],
                    record["enabled"],
                    record["updated_at"],
                    record["store_id"],
                    record["method_id"],
                ),
            )

    def _publish(self, method_id: str, action: str, stamp: str) -> None:
        self.runtime.events.publish(
            "shipping.changed",
            "1.0.0",
            {"method_id": method_id, "action": action},
            idempotency_key=_event_key("shipping.changed", method_id, action, stamp),
        )


class ShippingQuery:
    def __init__(self, engine: ShippingEngine) -> None:
        self._engine = engine

    def create(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.create_method(payload)

    def get(self, method_id) -> dict | None:
        return self._engine.get_method(method_id)

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_methods()

    def set(self, method_id, payload: Mapping[str, Any]) -> dict:
        return self._engine.set_method(method_id, payload)

    def quote(self, method_id) -> dict:
        return self._engine.quote(method_id)
