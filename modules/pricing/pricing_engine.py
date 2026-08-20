"""Pricing 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")


class PricingError(ValueError):
    """A pricing command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_id(value: object, *, field: str = "product_id") -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise PricingError(f"invalid {field}")
    return value


def _require_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PricingError("invalid amount_minor")
    if value < 0:
        raise PricingError("amount_minor must be >= 0")
    return value


def _require_currency(value: object) -> str:
    text = str(value or "UAH").strip().upper()
    if not _CURRENCY.fullmatch(text):
        raise PricingError("invalid currency")
    return text


def _iso(value: object) -> str:
    converter = getattr(value, "isoformat", None)
    if callable(converter):
        return str(converter())
    return str(value)


def _sql_unbound(error: BaseException) -> bool:
    """True only when the host never bound a package SQL connector."""

    text = str(error).lower()
    if "no longer bound" in text or "connection failed" in text:
        return False
    return "package sql is unavailable" in text


def _event_key(contract: str, entity_id: str, action: str, stamp: str) -> str:
    compact = stamp.replace("+", "p").replace(":", "").replace(".", "")
    return f"{contract}:{entity_id}:{action}:{compact}"[:128]


def _row_str(row: Mapping[str, Any], key: str) -> str:
    return str(row[key])


def _price_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "product_id": _row_str(row, "product_id"),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _facade_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "product_id": record["product_id"],
        "amount_minor": int(record["amount_minor"]),
        "currency": record["currency"],
    }


class PricingEngine:
    """Per-store list prices. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._prices: dict[str, dict[str, Any]] = {}

    def currency(self) -> str:
        return _require_currency(self.runtime.settings.get("currency"))

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

    def get_price(self, product_id: object) -> dict[str, Any] | None:
        product_id = _require_id(product_id)
        if not self._using_sql():
            record = self._prices.get(product_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, product_id, amount_minor, currency, created_at, updated_at "
                "FROM list_prices WHERE store_id = %s AND product_id = %s",
                (self.store_id, product_id),
            )
        if row is None:
            return None
        return _price_record(row)

    def list_prices(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                dict(self._prices[key]) for key in sorted(self._prices)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, product_id, amount_minor, currency, created_at, updated_at "
                "FROM list_prices WHERE store_id = %s ORDER BY product_id",
                (self.store_id,),
            )
        return tuple(_price_record(row) for row in rows)

    def set_price(self, product_id: object, amount_minor: object) -> dict[str, Any]:
        product_id = _require_id(product_id)
        amount_minor = _require_amount(amount_minor)
        currency = self.currency()
        stamp = _now()
        record = {
            "store_id": self.store_id,
            "product_id": product_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "created_at": stamp,
            "updated_at": stamp,
        }
        if not self._using_sql():
            existing = self._prices.get(product_id)
            if existing is not None:
                record["created_at"] = existing["created_at"]
            self._prices[product_id] = dict(record)
            self._emit(
                product_id=product_id,
                amount_minor=amount_minor,
                currency=currency,
                stamp=stamp,
            )
            return dict(record)
        with self.runtime.sql.transaction() as tx:
            existing = tx.fetchone(
                "SELECT created_at FROM list_prices WHERE store_id = %s AND product_id = %s",
                (self.store_id, product_id),
            )
            if existing is not None:
                record["created_at"] = _iso(existing["created_at"])
            tx.execute(
                "INSERT INTO list_prices "
                "(store_id, product_id, amount_minor, currency, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (store_id, product_id) DO UPDATE SET "
                "amount_minor = EXCLUDED.amount_minor, currency = EXCLUDED.currency, "
                "updated_at = EXCLUDED.updated_at",
                (
                    self.store_id,
                    product_id,
                    amount_minor,
                    currency,
                    record["created_at"],
                    stamp,
                ),
            )
        self._emit(
            product_id=product_id,
            amount_minor=amount_minor,
            currency=currency,
            stamp=stamp,
        )
        return record

    def _emit(
        self,
        *,
        product_id: str,
        amount_minor: int,
        currency: str,
        stamp: str,
    ) -> None:
        payload = {
            "product_id": product_id,
            "amount_minor": amount_minor,
            "currency": currency,
        }
        self.runtime.events.publish(
            "pricing.changed",
            "1.0.0",
            payload,
            idempotency_key=_event_key("pricing.changed", product_id, "set", stamp),
        )
        self.runtime.events.publish(
            "pricing.listChanged",
            "1.0.0",
            {**payload, "action": "set"},
            idempotency_key=_event_key(
                "pricing.listChanged", product_id, "set", stamp
            ),
        )


class PricingQuery:
    def __init__(self, engine: PricingEngine) -> None:
        self._engine = engine

    def get(self, product_id) -> dict | None:
        record = self._engine.get_price(product_id)
        if record is None:
            return None
        return _facade_record(record)

    def list(self) -> tuple[dict, ...]:
        return tuple(_facade_record(item) for item in self._engine.list_prices())

    def set(self, product_id, amount_minor: int) -> dict:
        return _facade_record(self._engine.set_price(product_id, amount_minor))


class PricingList:
    def __init__(self, engine: PricingEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_prices()

    def get(self, product_id: str) -> dict | None:
        return self._engine.get_price(product_id)

    def set(self, product_id: str, amount_minor: int) -> dict:
        return self._engine.set_price(product_id, amount_minor)
