"""Orders 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")
_PAYMENT_STATES = frozenset({"unpaid", "paid"})


class OrdersError(ValueError):
    """An orders command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise OrdersError(f"invalid {field}")
    return value


def _require_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise OrdersError("invalid text field")
    return value


def _require_amount(value: object, *, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise OrdersError(f"invalid {field}")
    if value < 0:
        raise OrdersError(f"{field} must be >= 0")
    return value


def _require_quantity(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OrdersError("invalid quantity")
    if value < 1:
        raise OrdersError("quantity must be >= 1")
    return value


def _require_currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise OrdersError("invalid currency")
    return value


def _iso(value: object) -> str:
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


def _header_record(row: Mapping[str, Any], lines: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "order_id": _row_str(row, "order_id"),
        "contact_name": _row_str(row, "contact_name"),
        "contact_email": _row_str(row, "contact_email"),
        "contact_phone": _row_str(row, "contact_phone"),
        "address_line": _row_str(row, "address_line"),
        "address_city": _row_str(row, "address_city"),
        "address_postal": _row_str(row, "address_postal"),
        "address_country": _row_str(row, "address_country"),
        "shipping_method_id": _row_str(row, "shipping_method_id"),
        "shipping_amount_minor": int(row["shipping_amount_minor"]),
        "discount_amount_minor": int(row["discount_amount_minor"]),
        "goods_amount_minor": int(row["goods_amount_minor"]),
        "payable_amount_minor": int(row["payable_amount_minor"]),
        "currency": _row_str(row, "currency"),
        "payment_state": _row_str(row, "payment_state"),
        "placed_at": _iso(row["placed_at"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "lines": list(lines),
    }


def _line_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "order_id": _row_str(row, "order_id"),
        "product_id": _row_str(row, "product_id"),
        "title": _row_str(row, "title"),
        "quantity": int(row["quantity"]),
        "amount_minor": int(row["amount_minor"]),
        "currency": _row_str(row, "currency"),
    }


def _parse_lines(raw: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list) or not raw:
        raise OrdersError("lines are required")
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    currency: str | None = None
    for item in raw:
        if not isinstance(item, dict):
            raise OrdersError("invalid line")
        product_id = _require_id(item.get("product_id"), field="product_id")
        if product_id in seen:
            raise OrdersError("duplicate product_id")
        seen.add(product_id)
        line_currency = _require_currency(item.get("currency"))
        if currency is None:
            currency = line_currency
        elif line_currency != currency:
            raise OrdersError("mixed currencies")
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            raise OrdersError("title is required")
        parsed.append(
            {
                "product_id": product_id,
                "title": title.strip(),
                "quantity": _require_quantity(item.get("quantity")),
                "amount_minor": _require_amount(item.get("amount_minor"), field="amount_minor"),
                "currency": line_currency,
            }
        )
    return tuple(parsed)


class OrdersEngine:
    """Per-store placed orders. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._orders: dict[str, dict[str, Any]] = {}
        self._lines: dict[tuple[str, str], dict[str, Any]] = {}

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

    def place(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise OrdersError("payload must be an object")
        lines = _parse_lines(payload.get("lines"))
        currency = lines[0]["currency"]
        goods = sum(int(line["amount_minor"]) * int(line["quantity"]) for line in lines)
        shipping = _require_amount(
            payload.get("shipping_amount_minor"), field="shipping_amount_minor"
        )
        discount = _require_amount(
            payload.get("discount_amount_minor"), field="discount_amount_minor"
        )
        payable = goods + shipping - discount
        if payable < 0:
            raise OrdersError("payable_amount_minor must be >= 0")
        stamp = _now()
        order_id = _new_id()
        header = {
            "store_id": self.store_id,
            "order_id": order_id,
            "contact_name": _require_text(payload.get("contact_name")),
            "contact_email": _require_text(payload.get("contact_email")),
            "contact_phone": _require_text(payload.get("contact_phone")),
            "address_line": _require_text(payload.get("address_line")),
            "address_city": _require_text(payload.get("address_city")),
            "address_postal": _require_text(payload.get("address_postal")),
            "address_country": _require_text(payload.get("address_country")),
            "shipping_method_id": _require_text(payload.get("shipping_method_id")),
            "shipping_amount_minor": shipping,
            "discount_amount_minor": discount,
            "goods_amount_minor": goods,
            "payable_amount_minor": payable,
            "currency": currency,
            "payment_state": "unpaid",
            "placed_at": stamp,
            "created_at": stamp,
            "updated_at": stamp,
        }
        stored_lines = tuple(
            {
                "store_id": self.store_id,
                "order_id": order_id,
                **line,
                "created_at": stamp,
            }
            for line in lines
        )
        if not self._using_sql():
            self._orders[order_id] = dict(header)
            for line in stored_lines:
                self._lines[(order_id, line["product_id"])] = dict(line)
        else:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO orders ("
                    "store_id, order_id, contact_name, contact_email, contact_phone, "
                    "address_line, address_city, address_postal, address_country, "
                    "shipping_method_id, shipping_amount_minor, discount_amount_minor, "
                    "goods_amount_minor, payable_amount_minor, currency, payment_state, "
                    "placed_at, created_at, updated_at"
                    ") VALUES ("
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s"
                    ")",
                    (
                        header["store_id"],
                        header["order_id"],
                        header["contact_name"],
                        header["contact_email"],
                        header["contact_phone"],
                        header["address_line"],
                        header["address_city"],
                        header["address_postal"],
                        header["address_country"],
                        header["shipping_method_id"],
                        header["shipping_amount_minor"],
                        header["discount_amount_minor"],
                        header["goods_amount_minor"],
                        header["payable_amount_minor"],
                        header["currency"],
                        header["payment_state"],
                        header["placed_at"],
                        header["created_at"],
                        header["updated_at"],
                    ),
                )
                for line in stored_lines:
                    tx.execute(
                        "INSERT INTO order_lines ("
                        "store_id, order_id, product_id, title, quantity, "
                        "amount_minor, currency, created_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            line["store_id"],
                            line["order_id"],
                            line["product_id"],
                            line["title"],
                            line["quantity"],
                            line["amount_minor"],
                            line["currency"],
                            line["created_at"],
                        ),
                    )
        self.runtime.events.publish(
            "orders.placed",
            "1.0.0",
            {"order_id": order_id, "payable_amount_minor": payable, "currency": currency},
            idempotency_key=_event_key("orders.placed", order_id, "placed", stamp),
        )
        return _header_record(header, tuple(_line_record(line) for line in stored_lines))

    def get_order(self, order_id: object) -> dict[str, Any] | None:
        order_id = _require_id(order_id, field="order_id")
        header = self._header(order_id)
        if header is None:
            return None
        return _header_record(header, self._lines_for(order_id))

    def list_orders(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(self.get_order(order_id) for order_id in sorted(self._orders))
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT * FROM orders WHERE store_id = %s ORDER BY order_id",
                (self.store_id,),
            )
        return tuple(
            _header_record(row, self._lines_for(_row_str(row, "order_id")))
            for row in rows
        )

    def set_payment_state(self, order_id: object, payment_state: object) -> dict[str, Any]:
        order_id = _require_id(order_id, field="order_id")
        if payment_state not in _PAYMENT_STATES:
            raise OrdersError("invalid payment_state")
        header = self._header(order_id)
        if header is None:
            raise OrdersError("unknown order")
        current = str(header["payment_state"])
        if current == "paid" and payment_state != "paid":
            raise OrdersError("payment_state is immutable after paid")
        if current == payment_state:
            return _header_record(header, self._lines_for(order_id))
        stamp = _now()
        if not self._using_sql():
            stored = self._orders[order_id]
            stored["payment_state"] = str(payment_state)
            stored["updated_at"] = stamp
        else:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "UPDATE orders SET payment_state = %s, updated_at = %s "
                    "WHERE store_id = %s AND order_id = %s",
                    (payment_state, stamp, self.store_id, order_id),
                )
        record = self.get_order(order_id)
        assert record is not None
        return record

    def _header(self, order_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._orders.get(order_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT * FROM orders WHERE store_id = %s AND order_id = %s",
                (self.store_id, order_id),
            )
        if row is None:
            return None
        return dict(row)

    def _lines_for(self, order_id: str) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                _line_record(record)
                for key, record in sorted(self._lines.items())
                if key[0] == order_id
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, order_id, product_id, title, quantity, "
                "amount_minor, currency, created_at FROM order_lines "
                "WHERE store_id = %s AND order_id = %s ORDER BY product_id",
                (self.store_id, order_id),
            )
        return tuple(_line_record(row) for row in rows)


class OrdersQuery:
    def __init__(self, engine: OrdersEngine) -> None:
        self._engine = engine

    def place(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.place(payload)

    def get(self, order_id) -> dict | None:
        return self._engine.get_order(order_id)

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_orders()

    def set_payment_state(self, order_id, payment_state: str) -> dict:
        return self._engine.set_payment_state(order_id, payment_state)
