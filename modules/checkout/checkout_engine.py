"""Checkout 1.0.0 orchestrator. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CURRENCY = re.compile(r"^[A-Z]{3,8}$")


class CheckoutError(ValueError):
    """A checkout command was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise CheckoutError(f"invalid {field}")
    return value


def _optional_code(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CheckoutError("invalid coupon_code")
    return value.strip()


def _text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CheckoutError("invalid text field")
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


def _placement_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "idempotency_key": _row_str(row, "idempotency_key"),
        "cart_id": _row_str(row, "cart_id"),
        "order_id": _row_str(row, "order_id"),
        "payment_id": _row_str(row, "payment_id"),
        "created_at": _iso(row["created_at"]),
    }


class CheckoutEngine:
    """Per-store place orchestrator. PostgreSQL stores idempotency when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._placements: dict[str, dict[str, Any]] = {}
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

    def _resolve(self, contract: str):
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            raise CheckoutError(f"{contract} is unavailable")
        try:
            return resolve(contract, ">=1.0.0,<2.0.0")
        except Exception as error:
            raise CheckoutError(f"{contract} is unavailable") from error

    def _invoke(self, contract: str, method: str, *args, **kwargs):
        service = self._resolve(contract)
        worker = getattr(service, method, None)
        if not callable(worker):
            raise CheckoutError(f"{contract}.{method} is unavailable")
        try:
            return worker(*args, **kwargs)
        except CheckoutError:
            raise
        except Exception as error:
            raise CheckoutError(str(error)) from error

    def place(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise CheckoutError("payload must be an object")
        cart_id = _require_id(payload.get("cart_id"), field="cart_id")
        shipping_method_id = _require_id(
            payload.get("shipping_method_id"), field="shipping_method_id"
        )
        idempotency_key = _require_id(
            payload.get("idempotency_key"), field="idempotency_key"
        )
        coupon_code = _optional_code(payload.get("coupon_code"))
        subject = _require_id(payload.get("_public_subject"), field="public subject")
        fingerprint = str(payload.get("_public_fingerprint") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise CheckoutError("invalid request fingerprint")
        existing = self._load(idempotency_key)
        if existing is not None:
            if str(existing.get("subject") or "") != subject or str(existing.get("fingerprint") or "") != fingerprint or str(existing.get("cart_id") or "") != cart_id:
                raise CheckoutError("idempotency conflict")
            if str(existing.get("state") or "") == "completed":
                return self._replay(existing)
            raise CheckoutError("checkout in progress")
        quoted = self._quote_cart(cart_id)
        discount = 0
        if coupon_code:
            applied = self._invoke(
                "promotions.query",
                "apply",
                {
                    "code": coupon_code,
                    "goods_minor": quoted["goods_minor"],
                    "currency": quoted["currency"],
                },
            )
            discount = int(applied["discount_amount_minor"])
        shipping = self._invoke("shipping.query", "quote", shipping_method_id)
        shipping_amount = int(shipping["amount_minor"])
        shipping_currency = str(shipping["currency"])
        if shipping_currency != quoted["currency"]:
            raise CheckoutError("mixed currencies")
        payable = quoted["goods_minor"] + shipping_amount - discount
        if payable < 0:
            raise CheckoutError("payable_amount_minor must be >= 0")
        existing = self._claim(idempotency_key, cart_id, subject, fingerprint)
        if existing is not None:
            if str(existing.get("state") or "") == "completed":
                return self._replay(existing)
            raise CheckoutError("checkout in progress")
        adjusted: list[tuple[str, int]] = []
        order_id = ""
        payment_id = ""
        order: dict[str, Any] | None = None
        try:
            for line in quoted["lines"]:
                product_id = str(line["product_id"])
                quantity = int(line["quantity"])
                self._invoke("inventory.stock", "adjust", product_id, -quantity)
                adjusted.append((product_id, quantity))
            order_lines = []
            for line in quoted["lines"]:
                product = self._invoke("catalog.storefront", "get", line["product_id"])
                if not isinstance(product, dict) or not product.get("title"):
                    raise CheckoutError("unknown product")
                order_lines.append(
                    {
                        "product_id": line["product_id"],
                        "title": product["title"],
                        "quantity": line["quantity"],
                        "amount_minor": line["amount_minor"],
                        "currency": line["currency"],
                    }
                )
            order = self._invoke(
                "orders.query",
                "place",
                {
                    "lines": order_lines,
                    "shipping_method_id": shipping_method_id,
                    "shipping_amount_minor": shipping_amount,
                    "discount_amount_minor": discount,
                    "contact_name": _text(payload.get("contact_name")),
                    "contact_email": _text(payload.get("contact_email")),
                    "contact_phone": _text(payload.get("contact_phone")),
                    "address_line": _text(payload.get("address_line")),
                    "address_city": _text(payload.get("address_city")),
                    "address_postal": _text(payload.get("address_postal")),
                    "address_country": _text(payload.get("address_country")),
                },
            )
            order_id = str(order["order_id"])
            payment = self._invoke(
                "payments.query",
                "create",
                {
                    "order_id": order_id,
                    "amount_minor": payable,
                    "currency": quoted["currency"],
                },
            )
            payment_id = str(payment["payment_id"])
            # Storefront v1 is manual/offline only.  Capturing here would
            # call the PSP path; payment remains open until an operator acts.
            self._complete(idempotency_key, cart_id, order_id, payment_id)
        except Exception:
            # A failure after the durable claim may have placed an order or
            # adjusted stock.  It must be reconciled, never made retryable.
            self._mark_needs_reconciliation(idempotency_key)
            raise
        stamp = _now()
        record = {
            "store_id": self.store_id,
            "idempotency_key": idempotency_key,
            "cart_id": cart_id,
            "order_id": order_id,
            "payment_id": payment_id,
            "created_at": stamp,
        }
        try:
            self._invoke("cart.query", "clear", cart_id)
        except CheckoutError:
            pass
        self.runtime.events.publish(
            "checkout.placed",
            "1.0.0",
            {"order_id": order_id, "payment_id": record["payment_id"]},
            idempotency_key=_event_key(
                "checkout.placed", order_id, "placed", stamp
            ),
        )
        return self._result(record, order=order, payable=payable, currency=quoted["currency"])

    def _quote_cart(self, cart_id: str) -> dict[str, Any]:
        quoted = self._invoke("cart.query", "quote", cart_id)
        lines = quoted.get("lines")
        if not isinstance(lines, list) or not lines:
            raise CheckoutError("cart is empty")
        currency = None
        goods = 0
        for line in lines:
            if not isinstance(line, dict):
                raise CheckoutError("invalid line")
            amount = line.get("amount_minor")
            line_currency = line.get("currency")
            if amount is None or line_currency is None:
                raise CheckoutError("unpriced line")
            if not isinstance(amount, int) or isinstance(amount, bool):
                raise CheckoutError("unpriced line")
            if not isinstance(line_currency, str) or not _CURRENCY.fullmatch(line_currency):
                raise CheckoutError("invalid currency")
            if currency is None:
                currency = line_currency
            elif line_currency != currency:
                raise CheckoutError("mixed currencies")
            goods += int(amount) * int(line["quantity"])
        return {
            "cart_id": cart_id,
            "lines": lines,
            "goods_minor": goods,
            "currency": currency,
        }

    def _compensate(self, adjusted: list[tuple[str, int]]) -> None:
        for product_id, quantity in reversed(adjusted):
            try:
                self._invoke("inventory.stock", "adjust", product_id, quantity)
            except Exception:
                continue

    def _replay(self, row: Mapping[str, Any]) -> dict[str, Any]:
        order_id = _row_str(row, "order_id")
        order = self._invoke("orders.query", "get", order_id) if order_id else None
        try:
            self._invoke("cart.query", "clear", _row_str(row, "cart_id"))
        except CheckoutError:
            pass
        payable = int(order["payable_amount_minor"]) if isinstance(order, dict) else 0
        currency = str(order["currency"]) if isinstance(order, dict) else ""
        return self._result(row, order=order, payable=payable, currency=currency)

    def _result(
        self,
        row: Mapping[str, Any],
        *,
        order: Mapping[str, Any] | None,
        payable: int,
        currency: str,
    ) -> dict[str, Any]:
        record = _placement_record(row)
        if isinstance(order, dict):
            record["payment_state"] = str(order.get("payment_state") or "unpaid")
            record["goods_amount_minor"] = int(order.get("goods_amount_minor") or 0)
            record["shipping_amount_minor"] = int(order.get("shipping_amount_minor") or 0)
            record["discount_amount_minor"] = int(order.get("discount_amount_minor") or 0)
        record["payable_amount_minor"] = payable
        record["currency"] = currency
        return record

    def _payment_state(self, payment_id: str) -> str:
        try:
            loaded = self._invoke("payments.query", "get", payment_id)
        except CheckoutError:
            return ""
        if not isinstance(loaded, dict):
            return ""
        return str(loaded.get("state") or "")

    def _claim(self, idempotency_key: str, cart_id: str, subject: str, fingerprint: str) -> dict[str, Any] | None:
        with self._lock:
            existing = self._load(idempotency_key)
            if existing is not None:
                return existing
            record = {
                "store_id": self.store_id,
                "idempotency_key": idempotency_key,
                "cart_id": cart_id,
                "order_id": "",
                "payment_id": "",
                "subject": subject,
                "fingerprint": fingerprint,
                "state": "in_flight",
                "created_at": _now(),
            }
            try:
                self._insert(record)
            except Exception as error:
                text = str(error).lower()
                if "connection failed" in text or "no longer bound" in text:
                    raise
                existing = self._load(idempotency_key)
                if existing is not None:
                    return existing
                raise
            return None

    def _insert(self, record: Mapping[str, Any]) -> None:
        if not self._using_sql():
            key = str(record["idempotency_key"])
            if key in self._placements:
                raise CheckoutError("checkout in progress")
            self._placements[key] = dict(record)
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "INSERT INTO checkout_placements ("
                "store_id, idempotency_key, cart_id, order_id, payment_id, subject, fingerprint, state, created_at"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record["store_id"],
                    record["idempotency_key"],
                    record["cart_id"],
                    record["order_id"],
                    record["payment_id"],
                    record["subject"],
                    record["fingerprint"],
                    record["state"],
                    record["created_at"],
                ),
            )

    def _complete(
        self,
        idempotency_key: str,
        cart_id: str,
        order_id: str,
        payment_id: str,
    ) -> None:
        stamp = _now()
        if not self._using_sql():
            current = dict(self._placements.get(idempotency_key) or {})
            current.update(
                {
                    "store_id": self.store_id,
                    "idempotency_key": idempotency_key,
                    "cart_id": cart_id,
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "created_at": current.get("created_at") or stamp,
                    "state": "completed",
                }
            )
            self._placements[idempotency_key] = current
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "UPDATE checkout_placements SET cart_id = %s, order_id = %s, payment_id = %s, state = %s "
                "WHERE store_id = %s AND idempotency_key = %s",
                (cart_id, order_id, payment_id, "completed", self.store_id, idempotency_key),
            )

    def _mark_needs_reconciliation(self, idempotency_key: str) -> None:
        if not self._using_sql():
            if idempotency_key in self._placements:
                self._placements[idempotency_key]["state"] = "needs_reconciliation"
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute("UPDATE checkout_placements SET state = %s WHERE store_id = %s AND idempotency_key = %s", ("needs_reconciliation", self.store_id, idempotency_key))

    def _release(self, idempotency_key: str) -> None:
        current = self._load(idempotency_key)
        if current is None or str(current.get("payment_id") or ""):
            return
        if not self._using_sql():
            self._placements.pop(idempotency_key, None)
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "DELETE FROM checkout_placements WHERE store_id = %s "
                "AND idempotency_key = %s AND payment_id = %s",
                (self.store_id, idempotency_key, ""),
            )

    def _load(self, idempotency_key: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._placements.get(idempotency_key)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, idempotency_key, cart_id, order_id, payment_id, subject, fingerprint, state, "
                "created_at FROM checkout_placements "
                "WHERE store_id = %s AND idempotency_key = %s",
                (self.store_id, idempotency_key),
            )
        if row is None:
            return None
        return dict(row)


class CheckoutQuery:
    def __init__(self, engine: CheckoutEngine) -> None:
        self._engine = engine

    def place(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.place(payload)
