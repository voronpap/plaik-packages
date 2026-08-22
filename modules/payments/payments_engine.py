"""Payments 1.0.1 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

from plaik_sdk import ConnectionRef, ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")
_CARD_FIELDS = frozenset({"pan", "card_number", "card", "cvv", "cvc", "expiry"})
_STATES = frozenset({"open", "captured"})


class PaymentsError(ValueError):
    """A payments command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise PaymentsError(f"invalid {field}")
    return value


def _require_amount(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaymentsError(f"invalid {field}")
    if value < 0:
        raise PaymentsError(f"{field} must be >= 0")
    return value


def _require_currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise PaymentsError("invalid currency")
    return value


def _reject_card_data(payload: Mapping[str, Any]) -> None:
    found = _CARD_FIELDS.intersection(payload)
    if found:
        raise PaymentsError("card data is forbidden")


def _connection_id(value: object) -> str:
    if value is None:
        return ""
    try:
        ref = ConnectionRef.model_validate(value)
    except Exception as error:
        raise PaymentsError("invalid connection") from error
    return ref.id


def _iso(value: object) -> str | None:
    if value is None:
        return None
    converter = getattr(value, "isoformat", None)
    if callable(converter):
        return str(converter())
    return str(value)


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


def _payment_record(row: Mapping[str, Any]) -> dict[str, Any]:
    captured = row.get("captured_at")
    return {
        "store_id": _row_str(row, "store_id"),
        "payment_id": _row_str(row, "payment_id"),
        "order_id": _row_str(row, "order_id"),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
        "method": _row_str(row, "method"),
        "state": _row_str(row, "state"),
        "connection_id": _row_str(row, "connection_id"),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "captured_at": _iso(captured) if captured not in (None, "") else None,
    }


class PaymentsEngine:
    """Per-store manual payments. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._payments: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

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

    def create_payment(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise PaymentsError("payload must be an object")
        _reject_card_data(payload)
        stamp = _now()
        payment_id = _new_id()
        record = {
            "store_id": self.store_id,
            "payment_id": payment_id,
            "order_id": _require_id(payload.get("order_id"), field="order_id"),
            "amount_minor": _require_amount(
                payload.get("amount_minor"), field="amount_minor"
            ),
            "currency": _require_currency(payload.get("currency")),
            "method": "manual",
            "state": "open",
            "connection_id": _connection_id(payload.get("connection")),
            "created_at": stamp,
            "updated_at": stamp,
            "captured_at": None,
        }
        self._write(record, insert=True)
        return _payment_record(record)

    def get_payment(self, payment_id: object) -> dict[str, Any] | None:
        payment_id = _require_id(payment_id, field="payment_id")
        row = self._load(payment_id)
        if row is None:
            return None
        return _payment_record(row)

    def list_payments(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                _payment_record(self._payments[payment_id])
                for payment_id in sorted(self._payments)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, payment_id, order_id, amount_minor, currency, "
                "method, state, connection_id, created_at, updated_at, captured_at "
                "FROM payments WHERE store_id = %s ORDER BY payment_id",
                (self.store_id,),
            )
        return tuple(_payment_record(row) for row in rows)

    def capture(self, payment_id: object) -> dict[str, Any]:
        payment_id = _require_id(payment_id, field="payment_id")
        with self._lock:
            current = self._load(payment_id)
            if current is None:
                raise PaymentsError("unknown payment")
            if str(current["state"]) == "captured":
                record = _payment_record(current)
                self._publish(record["payment_id"], record["updated_at"] or _now())
                return record
            if str(current["state"]) not in _STATES:
                raise PaymentsError("invalid state")
            self._dispatch_outbound_charge(current)
            stamp = _now()
            self._commit_captured(str(current["payment_id"]), stamp)
            loaded = self._load(payment_id)
            if loaded is None:
                raise PaymentsError("unknown payment")
            self._publish(payment_id, stamp)
            return _payment_record(loaded)

    def _dispatch_outbound_charge(self, record: Mapping[str, Any]) -> None:
        try:
            charger = self.runtime.services.resolve("psp-outbound.charge", "==1.0.0")
        except Exception as error:
            if "no compatible active service provider" in str(error).lower():
                return
            raise
        charger.charge(
            {
                "store_id": "ignored",
                "owner_id": "ignored",
                "payment_id": record["payment_id"],
                "amount_minor": int(record["amount_minor"]),
                "currency": record["currency"],
                "connection_id": record.get("connection_id") or "",
            }
        )

    def _commit_captured(self, payment_id: str, stamp: str) -> None:
        if not self._using_sql():
            current = self._payments.get(payment_id)
            if current is None or str(current["state"]) != "open":
                return
            current["state"] = "captured"
            current["updated_at"] = stamp
            current["captured_at"] = stamp
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "UPDATE payments SET state = %s, updated_at = %s, captured_at = %s "
                "WHERE store_id = %s AND payment_id = %s AND state = %s",
                ("captured", stamp, stamp, self.store_id, payment_id, "open"),
            )

    def _load(self, payment_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._payments.get(payment_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, payment_id, order_id, amount_minor, currency, "
                "method, state, connection_id, created_at, updated_at, captured_at "
                "FROM payments WHERE store_id = %s AND payment_id = %s",
                (self.store_id, payment_id),
            )
        if row is None:
            return None
        return dict(row)

    def _write(self, record: Mapping[str, Any], *, insert: bool) -> None:
        if not self._using_sql():
            self._payments[str(record["payment_id"])] = dict(record)
            return
        if insert:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO payments ("
                    "store_id, payment_id, order_id, amount_minor, currency, "
                    "method, state, connection_id, created_at, updated_at, captured_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        record["store_id"],
                        record["payment_id"],
                        record["order_id"],
                        record["amount_minor"],
                        record["currency"],
                        record["method"],
                        record["state"],
                        record["connection_id"],
                        record["created_at"],
                        record["updated_at"],
                        record["captured_at"],
                    ),
                )
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "UPDATE payments SET state = %s, updated_at = %s, captured_at = %s "
                "WHERE store_id = %s AND payment_id = %s",
                (
                    record["state"],
                    record["updated_at"],
                    record["captured_at"],
                    record["store_id"],
                    record["payment_id"],
                ),
            )

    def _publish(self, payment_id: str, stamp: str) -> None:
        self.runtime.events.publish(
            "payments.captured",
            "1.0.0",
            {"payment_id": payment_id, "method": "manual"},
            idempotency_key=_event_key("payments.captured", payment_id, "captured", stamp),
        )


class PaymentsQuery:
    def __init__(self, engine: PaymentsEngine) -> None:
        self._engine = engine

    def create(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.create_payment(payload)

    def get(self, payment_id) -> dict | None:
        return self._engine.get_payment(payment_id)

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_payments()

    def capture(self, payment_id) -> dict:
        return self._engine.capture(payment_id)
