"""PSP outbound 1.0.0. Recorded HTTP capture. No live network. No PAN."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")
_CARD_FIELDS = frozenset({"pan", "card_number", "card", "cvv", "cvc", "expiry"})
RECORDED_CAPTURE_URL = "https://psp.test/v1/captures"


class PspOutboundError(ValueError):
    """A recorded outbound charge was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise PspOutboundError(f"invalid {field}")
    return value


def _require_amount(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PspOutboundError(f"invalid {field}")
    if value < 0:
        raise PspOutboundError(f"{field} must be >= 0")
    return value


def _require_currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise PspOutboundError("invalid currency")
    return value


def _reject_card_data(payload: Mapping[str, Any]) -> None:
    found = _CARD_FIELDS.intersection(payload)
    if found:
        raise PspOutboundError("card data is forbidden")


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


def _charge_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "payment_id": _row_str(row, "payment_id"),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
        "connection_id": _row_str(row, "connection_id"),
        "provider_ref": _row_str(row, "provider_ref"),
        "created_at": _iso(row["created_at"]),
        "replayed": bool(row.get("replayed")),
    }


def _recorded_post(method: str, url: str, body: Mapping[str, Any]) -> dict[str, Any]:
    """Return a recorded fixture. Never opens a socket."""
    if method != "POST" or url != RECORDED_CAPTURE_URL:
        raise PspOutboundError("unknown recorded fixture")
    payment_id = str(body.get("payment_id") or "")
    if not payment_id:
        raise PspOutboundError("recorded fixture requires payment_id")
    return {"ok": True, "id": f"rec:{payment_id}"}


class PspOutboundEngine:
    """Per-store recorded outbound charges. SQL journal when bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._charges: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self.recorded_calls: list[tuple[str, str, dict[str, Any]]] = []

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

    def charge(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise PspOutboundError("payload must be an object")
        _reject_card_data(payload)
        payment_id = _require_id(payload.get("payment_id"), field="payment_id")
        connection_id = payload.get("connection_id") or ""
        if connection_id not in (None, "") and not isinstance(connection_id, str):
            raise PspOutboundError("invalid connection_id")
        connection_id = str(connection_id or "")
        body = {
            "payment_id": payment_id,
            "amount_minor": _require_amount(
                payload.get("amount_minor"), field="amount_minor"
            ),
            "currency": _require_currency(payload.get("currency")),
            "connection_id": connection_id,
        }
        stamp = _now()
        claimed = {
            "store_id": self.store_id,
            "payment_id": payment_id,
            "amount_minor": body["amount_minor"],
            "currency": body["currency"],
            "connection_id": connection_id,
            "provider_ref": "",
            "created_at": stamp,
            "replayed": False,
        }
        with self._lock:
            existing = self._claim(claimed)
            if existing is not None:
                replay = dict(existing)
                replay["replayed"] = True
                return _charge_record(replay)
            self.recorded_calls.append(("POST", RECORDED_CAPTURE_URL, dict(body)))
            fixture = _recorded_post("POST", RECORDED_CAPTURE_URL, body)
            claimed["provider_ref"] = str(fixture["id"])
            self._complete(claimed)
            self._publish(claimed, stamp)
            return _charge_record(claimed)

    def get_charge(self, payment_id: object) -> dict[str, Any] | None:
        payment_id = _require_id(payment_id, field="payment_id")
        row = self._load(payment_id)
        if row is None:
            return None
        return _charge_record(row)

    def _load(self, payment_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._charges.get(payment_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, payment_id, amount_minor, currency, "
                "connection_id, provider_ref, created_at "
                "FROM outbound_charges WHERE store_id = %s AND payment_id = %s",
                (self.store_id, payment_id),
            )
        if row is None:
            return None
        return dict(row)

    def _claim(self, record: Mapping[str, Any]) -> dict[str, Any] | None:
        existing = self._load(str(record["payment_id"]))
        if existing is not None:
            return existing
        try:
            self._insert_claim(record)
        except Exception as error:
            text = str(error).lower()
            if "connection failed" in text or "no longer bound" in text:
                raise
            existing = self._load(str(record["payment_id"]))
            if existing is not None:
                return existing
            raise
        return None

    def _insert_claim(self, record: Mapping[str, Any]) -> None:
        if not self._using_sql():
            payment_id = str(record["payment_id"])
            if payment_id in self._charges:
                raise PspOutboundError("charge in progress")
            self._charges[payment_id] = dict(record)
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "INSERT INTO outbound_charges ("
                "store_id, payment_id, amount_minor, currency, "
                "connection_id, provider_ref, created_at"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    record["store_id"],
                    record["payment_id"],
                    record["amount_minor"],
                    record["currency"],
                    record["connection_id"],
                    record["provider_ref"],
                    record["created_at"],
                ),
            )

    def _complete(self, record: Mapping[str, Any]) -> None:
        if not self._using_sql():
            self._charges[str(record["payment_id"])] = dict(record)
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "UPDATE outbound_charges SET provider_ref = %s "
                "WHERE store_id = %s AND payment_id = %s",
                (
                    record["provider_ref"],
                    record["store_id"],
                    record["payment_id"],
                ),
            )

    def _publish(self, record: Mapping[str, Any], stamp: str) -> None:
        self.runtime.events.publish(
            "psp-outbound.charged",
            "1.0.0",
            {
                "payment_id": record["payment_id"],
                "provider_ref": record["provider_ref"],
            },
            idempotency_key=_event_key(
                "psp-outbound.charged",
                str(record["payment_id"]),
                "charged",
                stamp,
            ),
        )


class PspOutboundCharge:
    def __init__(self, engine: PspOutboundEngine) -> None:
        self._engine = engine

    def charge(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.charge(payload)

    def get(self, payment_id) -> dict | None:
        return self._engine.get_charge(payment_id)
