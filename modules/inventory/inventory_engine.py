"""Inventory 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class InventoryError(ValueError):
    """An inventory command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_id(value: object, *, field: str = "product_id") -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise InventoryError(f"invalid {field}")
    return value


def _require_quantity(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryError("invalid quantity")
    if value < 0:
        raise InventoryError("quantity must be >= 0")
    return value


def _require_delta(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryError("invalid delta")
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


def _stock_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "product_id": _row_str(row, "product_id"),
        "quantity": int(row["quantity"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


class InventoryEngine:
    """Per-store on-hand stock. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._stock: dict[str, dict[str, Any]] = {}

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

    def _memory_record(self, product_id: str) -> dict[str, Any] | None:
        return self._stock.get(product_id)

    def get_stock(self, product_id: object) -> dict[str, Any] | None:
        product_id = _require_id(product_id)
        if not self._using_sql():
            record = self._memory_record(product_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, product_id, quantity, created_at, updated_at "
                "FROM stock_items WHERE store_id = %s AND product_id = %s",
                (self.store_id, product_id),
            )
        if row is None:
            return None
        return _stock_record(row)

    def list_stock(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                dict(self._stock[key]) for key in sorted(self._stock)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, product_id, quantity, created_at, updated_at "
                "FROM stock_items WHERE store_id = %s ORDER BY product_id",
                (self.store_id,),
            )
        return tuple(_stock_record(row) for row in rows)

    def get_quantity(self, product_id: object) -> int:
        record = self.get_stock(product_id)
        if record is None:
            return 0
        return int(record["quantity"])

    def set_stock(self, product_id: object, quantity: object, *, action: str = "set") -> dict[str, Any]:
        product_id = _require_id(product_id)
        quantity = _require_quantity(quantity)
        stamp = _now()
        record = {
            "store_id": self.store_id,
            "product_id": product_id,
            "quantity": quantity,
            "created_at": stamp,
            "updated_at": stamp,
        }
        if not self._using_sql():
            existing = self._stock.get(product_id)
            if existing is not None:
                record["created_at"] = existing["created_at"]
            self._stock[product_id] = dict(record)
            self._emit(product_id=product_id, quantity=quantity, action=action, stamp=stamp)
            return dict(record)
        with self.runtime.sql.transaction() as tx:
            existing = tx.fetchone(
                "SELECT created_at FROM stock_items WHERE store_id = %s AND product_id = %s",
                (self.store_id, product_id),
            )
            if existing is not None:
                record["created_at"] = _iso(existing["created_at"])
            tx.execute(
                "INSERT INTO stock_items (store_id, product_id, quantity, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (store_id, product_id) DO UPDATE SET "
                "quantity = EXCLUDED.quantity, updated_at = EXCLUDED.updated_at",
                (
                    self.store_id,
                    product_id,
                    quantity,
                    record["created_at"],
                    stamp,
                ),
            )
        self._emit(product_id=product_id, quantity=quantity, action=action, stamp=stamp)
        return record

    def adjust_stock(self, product_id: object, delta: object) -> dict[str, Any]:
        product_id = _require_id(product_id)
        delta = _require_delta(delta)
        current = self.get_quantity(product_id)
        return self.set_stock(product_id, current + delta, action="adjusted")

    def ensure_zero(self, product_id: object) -> dict[str, Any] | None:
        product_id = _require_id(product_id)
        if self.get_stock(product_id) is not None:
            return None
        return self.set_stock(product_id, 0, action="ensured")

    def sync_from_catalog(self) -> None:
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            return
        try:
            catalog = resolve("catalog.query", ">=1.0.0,<2.0.0")
        except Exception:
            return
        if not callable(getattr(catalog, "list", None)):
            return
        for product in catalog.list():
            if not isinstance(product, dict):
                continue
            try:
                self.ensure_zero(product.get("id"))
            except InventoryError:
                continue

    def _emit(self, *, product_id: str, quantity: int, action: str, stamp: str) -> None:
        payload = {"product_id": product_id, "quantity": quantity}
        self.runtime.events.publish(
            "inventory.changed",
            "1.0.0",
            payload,
            idempotency_key=_event_key("inventory.changed", product_id, action, stamp),
        )
        self.runtime.events.publish(
            "inventory.stockChanged",
            "1.0.0",
            {"product_id": product_id, "quantity": quantity, "action": action},
            idempotency_key=_event_key(
                "inventory.stockChanged", product_id, action, stamp
            ),
        )


class InventoryQuery:
    def __init__(self, engine: InventoryEngine) -> None:
        self._engine = engine

    def get(self, product_id) -> int:
        return self._engine.get_quantity(product_id)

    def list(self) -> tuple[dict, ...]:
        return tuple(
            {"product_id": item["product_id"], "quantity": item["quantity"]}
            for item in self._engine.list_stock()
        )

    def set(self, product_id, quantity: int) -> dict:
        record = self._engine.set_stock(product_id, quantity)
        return {"product_id": record["product_id"], "quantity": record["quantity"]}


class InventoryStock:
    def __init__(self, engine: InventoryEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_stock()

    def get(self, product_id: str) -> dict | None:
        return self._engine.get_stock(product_id)

    def set(self, product_id: str, quantity: int) -> dict:
        return self._engine.set_stock(product_id, quantity)

    def adjust(self, product_id: str, delta: int) -> dict:
        return self._engine.adjust_stock(product_id, delta)
