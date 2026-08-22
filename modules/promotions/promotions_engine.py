"""Promotions 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")


class PromotionsError(ValueError):
    """A promotions command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise PromotionsError(f"invalid {field}")
    return value


def _require_code(value: object) -> str:
    if not isinstance(value, str):
        raise PromotionsError("invalid code")
    code = value.strip().upper()
    if not _CODE.fullmatch(code):
        raise PromotionsError("invalid code")
    return code


def _require_amount(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PromotionsError(f"invalid {field}")
    if value < 0:
        raise PromotionsError(f"{field} must be >= 0")
    return value


def _require_currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise PromotionsError("invalid currency")
    return value


def _require_enabled(value: object, *, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise PromotionsError("invalid enabled")
        return default
    if not isinstance(value, bool):
        raise PromotionsError("invalid enabled")
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


def _coupon_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "coupon_id": _row_str(row, "coupon_id"),
        "code": _row_str(row, "code"),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
        "enabled": _as_bool(row["enabled"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


class PromotionsEngine:
    """Per-store coupons. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._coupons: dict[str, dict[str, Any]] = {}

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

    def create_coupon(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise PromotionsError("payload must be an object")
        stamp = _now()
        coupon_id = _new_id()
        code = _require_code(payload.get("code"))
        if self._code_taken(code):
            raise PromotionsError("code already exists")
        record = {
            "store_id": self.store_id,
            "coupon_id": coupon_id,
            "code": code,
            "amount_minor": _require_amount(
                payload.get("amount_minor"), field="amount_minor"
            ),
            "currency": _require_currency(payload.get("currency")),
            "enabled": _require_enabled(payload.get("enabled"), default=True),
            "created_at": stamp,
            "updated_at": stamp,
        }
        self._write(record, insert=True)
        self._publish(coupon_id, "created", stamp)
        return _coupon_record(record)

    def get_coupon(self, coupon_id: object) -> dict[str, Any] | None:
        coupon_id = _require_id(coupon_id, field="coupon_id")
        row = self._load(coupon_id)
        if row is None:
            return None
        return _coupon_record(row)

    def list_coupons(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                _coupon_record(self._coupons[coupon_id])
                for coupon_id in sorted(self._coupons)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, coupon_id, code, amount_minor, currency, "
                "enabled, created_at, updated_at FROM promotion_coupons "
                "WHERE store_id = %s ORDER BY coupon_id",
                (self.store_id,),
            )
        return tuple(_coupon_record(row) for row in rows)

    def set_coupon(self, coupon_id: object, payload: Mapping[str, Any]) -> dict[str, Any]:
        coupon_id = _require_id(coupon_id, field="coupon_id")
        if not isinstance(payload, Mapping):
            raise PromotionsError("payload must be an object")
        current = self._load(coupon_id)
        if current is None:
            raise PromotionsError("unknown coupon")
        stamp = _now()
        code = (
            _require_code(payload["code"])
            if "code" in payload
            else _row_str(current, "code")
        )
        if self._code_taken(code, exclude=coupon_id):
            raise PromotionsError("code already exists")
        record = {
            "store_id": self.store_id,
            "coupon_id": coupon_id,
            "code": code,
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
        self._publish(coupon_id, "set", stamp)
        return _coupon_record(record)

    def apply(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise PromotionsError("payload must be an object")
        code = _require_code(payload.get("code"))
        goods_minor = _require_amount(payload.get("goods_minor"), field="goods_minor")
        currency = _require_currency(payload.get("currency"))
        row = self._load_by_code(code)
        if row is None:
            raise PromotionsError("unknown code")
        if not _as_bool(row["enabled"]):
            raise PromotionsError("coupon is disabled")
        if _row_str(row, "currency") != currency:
            raise PromotionsError("currency mismatch")
        discount = min(int(row["amount_minor"]), goods_minor)
        return {
            "store_id": self.store_id,
            "coupon_id": _row_str(row, "coupon_id"),
            "code": _row_str(row, "code"),
            "goods_minor": goods_minor,
            "discount_amount_minor": discount,
            "currency": currency,
        }

    def _code_taken(self, code: str, *, exclude: str | None = None) -> bool:
        existing = self._load_by_code(code)
        if existing is None:
            return False
        return _row_str(existing, "coupon_id") != (exclude or "")

    def _load(self, coupon_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._coupons.get(coupon_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, coupon_id, code, amount_minor, currency, "
                "enabled, created_at, updated_at FROM promotion_coupons "
                "WHERE store_id = %s AND coupon_id = %s",
                (self.store_id, coupon_id),
            )
        if row is None:
            return None
        return dict(row)

    def _load_by_code(self, code: str) -> dict[str, Any] | None:
        if not self._using_sql():
            for record in self._coupons.values():
                if str(record["code"]) == code:
                    return dict(record)
            return None
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, coupon_id, code, amount_minor, currency, "
                "enabled, created_at, updated_at FROM promotion_coupons "
                "WHERE store_id = %s AND code = %s",
                (self.store_id, code),
            )
        if row is None:
            return None
        return dict(row)

    def _write(self, record: Mapping[str, Any], *, insert: bool) -> None:
        if not self._using_sql():
            self._coupons[str(record["coupon_id"])] = dict(record)
            return
        if insert:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO promotion_coupons ("
                    "store_id, coupon_id, code, amount_minor, currency, "
                    "enabled, created_at, updated_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        record["store_id"],
                        record["coupon_id"],
                        record["code"],
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
                "UPDATE promotion_coupons SET code = %s, amount_minor = %s, "
                "currency = %s, enabled = %s, updated_at = %s "
                "WHERE store_id = %s AND coupon_id = %s",
                (
                    record["code"],
                    record["amount_minor"],
                    record["currency"],
                    record["enabled"],
                    record["updated_at"],
                    record["store_id"],
                    record["coupon_id"],
                ),
            )

    def _publish(self, coupon_id: str, action: str, stamp: str) -> None:
        self.runtime.events.publish(
            "promotions.changed",
            "1.0.0",
            {"coupon_id": coupon_id, "action": action},
            idempotency_key=_event_key("promotions.changed", coupon_id, action, stamp),
        )


class PromotionsQuery:
    def __init__(self, engine: PromotionsEngine) -> None:
        self._engine = engine

    def create(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.create_coupon(payload)

    def get(self, coupon_id) -> dict | None:
        return self._engine.get_coupon(coupon_id)

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_coupons()

    def set(self, coupon_id, payload: Mapping[str, Any]) -> dict:
        return self._engine.set_coupon(coupon_id, payload)

    def apply(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.apply(payload)
