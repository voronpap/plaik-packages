"""Cart 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_PUBLIC_QUANTITY = 100


class CartError(ValueError):
    """A cart command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise CartError(f"invalid {field}")
    return value


def _require_quantity(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CartError("invalid quantity")
    if value < 1:
        raise CartError("quantity must be >= 1")
    if value > _MAX_PUBLIC_QUANTITY:
        raise CartError("quantity exceeds the permitted limit")
    return value


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


def _cart_record(
    *,
    store_id: str,
    cart_id: str,
    created_at: str,
    updated_at: str,
    lines: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "store_id": store_id,
        "cart_id": cart_id,
        "created_at": created_at,
        "updated_at": updated_at,
        "lines": list(lines),
    }


def _line_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "cart_id": _row_str(row, "cart_id"),
        "product_id": _row_str(row, "product_id"),
        "quantity": int(row["quantity"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


class CartEngine:
    """Per-store Admin-managed carts. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._carts: dict[str, dict[str, Any]] = {}
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

    def _require_product(self, product_id: str) -> None:
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            raise CartError("catalog is unavailable")
        try:
            catalog = resolve("catalog.storefront", ">=1.0.0,<2.0.0")
        except Exception as error:
            raise CartError("catalog is unavailable") from error
        getter = getattr(catalog, "get", None)
        if not callable(getter):
            raise CartError("catalog is unavailable")
        product = getter(product_id)
        if not isinstance(product, dict):
            raise CartError("unknown product")

    def _price_of(self, product_id: str) -> dict[str, Any] | None:
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            return None
        try:
            pricing = resolve("pricing.query", ">=1.0.0,<2.0.0")
        except Exception:
            return None
        getter = getattr(pricing, "get", None)
        if not callable(getter):
            return None
        record = getter(product_id)
        if not isinstance(record, dict):
            return None
        amount = record.get("amount_minor")
        currency = record.get("currency")
        if not isinstance(amount, int) or isinstance(amount, bool):
            return None
        if not isinstance(currency, str):
            return None
        return {"amount_minor": amount, "currency": currency}

    def create_cart(self, *, owner_subject: str | None = None) -> dict[str, Any]:
        """Create a cart, optionally bound to the opaque shopper subject.

        ``owner_subject`` is supplied only by the public boundary.  It is the
        Core-issued opaque handle, never a browser cookie or request value.
        """
        cart_id = _new_id()
        stamp = _now()
        if not self._using_sql():
            self._carts[cart_id] = {
                "store_id": self.store_id,
                "cart_id": cart_id,
                "created_at": stamp,
                "updated_at": stamp,
                "owner_subject": owner_subject,
            }
            self._emit(cart_id=cart_id, action="created", stamp=stamp)
            return _cart_record(
                store_id=self.store_id,
                cart_id=cart_id,
                created_at=stamp,
                updated_at=stamp,
                lines=(),
            )
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "INSERT INTO carts (store_id, cart_id, created_at, updated_at, owner_subject) "
                "VALUES (%s, %s, %s, %s, %s)",
                (self.store_id, cart_id, stamp, stamp, owner_subject),
            )
        self._emit(cart_id=cart_id, action="created", stamp=stamp)
        return _cart_record(
            store_id=self.store_id,
            cart_id=cart_id,
            created_at=stamp,
            updated_at=stamp,
            lines=(),
        )

    def cart_for_subject(self, owner_subject: object) -> dict[str, Any]:
        """Return the single cart owned by a resolved public subject.

        The method deliberately has no public cart-id input.  This prevents a
        shopper from selecting another shopper's cart by guessing an id.
        """
        subject = _require_id(owner_subject, field="owner_subject")
        if not self._using_sql():
            for cart_id, record in self._carts.items():
                if record.get("owner_subject") == subject:
                    cart = self.get_cart(cart_id)
                    if cart is not None:
                        return cart
            return self.create_cart(owner_subject=subject)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT cart_id FROM carts WHERE store_id = %s AND owner_subject = %s",
                (self.store_id, subject),
            )
        if row is not None:
            cart = self.get_cart(str(row["cart_id"]))
            if cart is not None:
                return cart
        try:
            return self.create_cart(owner_subject=subject)
        except Exception:
            # A concurrent request may have won the unique owner index.
            with self.runtime.sql.transaction() as tx:
                row = tx.fetchone(
                    "SELECT cart_id FROM carts WHERE store_id = %s AND owner_subject = %s",
                    (self.store_id, subject),
                )
            if row is None:
                raise
            cart = self.get_cart(str(row["cart_id"]))
            if cart is None:
                raise CartError("owned cart is unavailable")
            return cart

    def get_cart(self, cart_id: object) -> dict[str, Any] | None:
        cart_id = _require_id(cart_id, field="cart_id")
        header = self._header(cart_id)
        if header is None:
            return None
        return _cart_record(
            store_id=header["store_id"],
            cart_id=header["cart_id"],
            created_at=header["created_at"],
            updated_at=header["updated_at"],
            lines=self._lines_for(cart_id),
        )

    def list_carts(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                self.get_cart(cart_id)
                for cart_id in sorted(self._carts)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, cart_id, created_at, updated_at FROM carts "
                "WHERE store_id = %s ORDER BY cart_id",
                (self.store_id,),
            )
        return tuple(
            _cart_record(
                store_id=_row_str(row, "store_id"),
                cart_id=_row_str(row, "cart_id"),
                created_at=_iso(row["created_at"]),
                updated_at=_iso(row["updated_at"]),
                lines=self._lines_for(_row_str(row, "cart_id")),
            )
            for row in rows
        )

    def add_line(self, cart_id: object, product_id: object, quantity: object = 1) -> dict[str, Any]:
        cart_id = _require_id(cart_id, field="cart_id")
        product_id = _require_id(product_id, field="product_id")
        quantity = _require_quantity(quantity)
        self._require_cart(cart_id)
        self._require_product(product_id)
        existing = self._line(cart_id, product_id)
        next_qty = quantity if existing is None else int(existing["quantity"]) + quantity
        if next_qty > _MAX_PUBLIC_QUANTITY:
            raise CartError("quantity exceeds the permitted limit")
        return self._write_line(cart_id, product_id, next_qty, action="added")

    def set_line(self, cart_id: object, product_id: object, quantity: object) -> dict[str, Any] | None:
        cart_id = _require_id(cart_id, field="cart_id")
        product_id = _require_id(product_id, field="product_id")
        self._require_cart(cart_id)
        if quantity == 0:
            return self.remove_line(cart_id, product_id)
        quantity = _require_quantity(quantity)
        self._require_product(product_id)
        return self._write_line(cart_id, product_id, quantity, action="set")

    def remove_line(self, cart_id: object, product_id: object) -> dict[str, Any] | None:
        cart_id = _require_id(cart_id, field="cart_id")
        product_id = _require_id(product_id, field="product_id")
        self._require_cart(cart_id)
        existing = self._line(cart_id, product_id)
        if existing is None:
            return None
        stamp = _now()
        if not self._using_sql():
            self._lines.pop((cart_id, product_id), None)
            self._touch_memory(cart_id, stamp)
        else:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "DELETE FROM cart_lines WHERE store_id = %s AND cart_id = %s "
                    "AND product_id = %s",
                    (self.store_id, cart_id, product_id),
                )
                tx.execute(
                    "UPDATE carts SET updated_at = %s WHERE store_id = %s AND cart_id = %s",
                    (stamp, self.store_id, cart_id),
                )
        self._emit(cart_id=cart_id, action="removed", stamp=stamp, product_id=product_id)
        return self.get_cart(cart_id)

    def clear_cart(self, cart_id: object) -> dict[str, Any]:
        cart_id = _require_id(cart_id, field="cart_id")
        self._require_cart(cart_id)
        stamp = _now()
        if not self._using_sql():
            for key in [item for item in self._lines if item[0] == cart_id]:
                self._lines.pop(key, None)
            self._touch_memory(cart_id, stamp)
        else:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "DELETE FROM cart_lines WHERE store_id = %s AND cart_id = %s",
                    (self.store_id, cart_id),
                )
                tx.execute(
                    "UPDATE carts SET updated_at = %s WHERE store_id = %s AND cart_id = %s",
                    (stamp, self.store_id, cart_id),
                )
        self._emit(cart_id=cart_id, action="cleared", stamp=stamp)
        record = self.get_cart(cart_id)
        assert record is not None
        return record

    def quote(self, cart_id: object) -> dict[str, Any]:
        cart = self.get_cart(cart_id)
        if cart is None:
            raise CartError("unknown cart")
        quoted_lines: list[dict[str, Any]] = []
        goods_minor = 0
        currency: str | None = None
        for line in cart["lines"]:
            priced = dict(line)
            price = self._price_of(line["product_id"])
            if price is None:
                priced["amount_minor"] = None
                priced["currency"] = None
            else:
                priced["amount_minor"] = price["amount_minor"]
                priced["currency"] = price["currency"]
                goods_minor += int(price["amount_minor"]) * int(line["quantity"])
                currency = price["currency"] if currency is None else currency
            quoted_lines.append(priced)
        return {
            "store_id": cart["store_id"],
            "cart_id": cart["cart_id"],
            "lines": quoted_lines,
            "goods_minor": goods_minor,
            "currency": currency,
        }

    def _header(self, cart_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._carts.get(cart_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, cart_id, created_at, updated_at FROM carts "
                "WHERE store_id = %s AND cart_id = %s",
                (self.store_id, cart_id),
            )
        if row is None:
            return None
        return {
            "store_id": _row_str(row, "store_id"),
            "cart_id": _row_str(row, "cart_id"),
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
        }

    def _require_cart(self, cart_id: str) -> dict[str, Any]:
        header = self._header(cart_id)
        if header is None:
            raise CartError("unknown cart")
        return header

    def _lines_for(self, cart_id: str) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            rows = [
                dict(record)
                for key, record in sorted(self._lines.items())
                if key[0] == cart_id
            ]
            return tuple(rows)
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, cart_id, product_id, quantity, created_at, updated_at "
                "FROM cart_lines WHERE store_id = %s AND cart_id = %s "
                "ORDER BY product_id",
                (self.store_id, cart_id),
            )
        return tuple(_line_record(row) for row in rows)

    def _line(self, cart_id: str, product_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._lines.get((cart_id, product_id))
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, cart_id, product_id, quantity, created_at, updated_at "
                "FROM cart_lines WHERE store_id = %s AND cart_id = %s AND product_id = %s",
                (self.store_id, cart_id, product_id),
            )
        if row is None:
            return None
        return _line_record(row)

    def _touch_memory(self, cart_id: str, stamp: str) -> None:
        header = self._carts[cart_id]
        header["updated_at"] = stamp

    def _write_line(
        self,
        cart_id: str,
        product_id: str,
        quantity: int,
        *,
        action: str,
    ) -> dict[str, Any]:
        stamp = _now()
        existing = self._line(cart_id, product_id)
        created_at = stamp if existing is None else existing["created_at"]
        record = {
            "store_id": self.store_id,
            "cart_id": cart_id,
            "product_id": product_id,
            "quantity": quantity,
            "created_at": created_at,
            "updated_at": stamp,
        }
        if not self._using_sql():
            self._lines[(cart_id, product_id)] = dict(record)
            self._touch_memory(cart_id, stamp)
        else:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO cart_lines "
                    "(store_id, cart_id, product_id, quantity, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (store_id, cart_id, product_id) DO UPDATE SET "
                    "quantity = EXCLUDED.quantity, updated_at = EXCLUDED.updated_at",
                    (
                        self.store_id,
                        cart_id,
                        product_id,
                        quantity,
                        created_at,
                        stamp,
                    ),
                )
                tx.execute(
                    "UPDATE carts SET updated_at = %s WHERE store_id = %s AND cart_id = %s",
                    (stamp, self.store_id, cart_id),
                )
        self._emit(
            cart_id=cart_id,
            action=action,
            stamp=stamp,
            product_id=product_id,
            quantity=quantity,
        )
        cart = self.get_cart(cart_id)
        assert cart is not None
        return cart

    def _emit(
        self,
        *,
        cart_id: str,
        action: str,
        stamp: str,
        product_id: str | None = None,
        quantity: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {"cart_id": cart_id, "action": action}
        if product_id is not None:
            payload["product_id"] = product_id
        if quantity is not None:
            payload["quantity"] = quantity
        self.runtime.events.publish(
            "cart.changed",
            "1.0.0",
            payload,
            idempotency_key=_event_key("cart.changed", cart_id, action, stamp),
        )


class CartQuery:
    def __init__(self, engine: CartEngine) -> None:
        self._engine = engine

    def create(self) -> dict:
        return self._engine.create_cart()

    def get(self, cart_id) -> dict | None:
        return self._engine.get_cart(cart_id)

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_carts()

    def add(self, cart_id, product_id, quantity: int = 1) -> dict:
        return self._engine.add_line(cart_id, product_id, quantity)

    def set(self, cart_id, product_id, quantity: int) -> dict | None:
        return self._engine.set_line(cart_id, product_id, quantity)

    def remove(self, cart_id, product_id) -> dict | None:
        return self._engine.remove_line(cart_id, product_id)

    def clear(self, cart_id) -> dict:
        return self._engine.clear_cart(cart_id)

    def quote(self, cart_id) -> dict:
        return self._engine.quote(cart_id)


class CartShopper:
    """Package service used by other Storefront packages, never by HTTP directly."""

    def __init__(self, engine: CartEngine) -> None:
        self._engine = engine

    def for_subject(self, owner_subject: str) -> dict:
        return self._engine.cart_for_subject(owner_subject)
