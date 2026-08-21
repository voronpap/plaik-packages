"""SEO 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,253}$")
_TITLE = re.compile(r"^[^\x00-\x1f]{1,200}$")


class SeoError(ValueError):
    """An SEO command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_id(value: object, *, field: str = "product_id") -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise SeoError(f"invalid {field}")
    return value


def _require_title(value: object) -> str:
    if not isinstance(value, str) or not _TITLE.fullmatch(value):
        raise SeoError("invalid title")
    return value


def _require_description(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or "\x00" in value or len(value) > 2000:
        raise SeoError("invalid description")
    return value


def _require_host(value: object) -> str:
    text = str(value or "shop.example.test").strip().lower()
    if text.startswith("http://") or text.startswith("https://") or "/" in text:
        raise SeoError("invalid canonical-host")
    if not _HOST.fullmatch(text):
        raise SeoError("invalid canonical-host")
    return text


def _canonical(host: str, product_id: str, sku: object) -> str:
    slug = sku if isinstance(sku, str) and sku else product_id
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", slug):
        slug = product_id
    return f"https://{host}/p/{slug}"


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


def _seo_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "product_id": _row_str(row, "product_id"),
        "title": _row_str(row, "title"),
        "description": _row_str(row, "description"),
        "canonical": _row_str(row, "canonical"),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _facade_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "product_id": record["product_id"],
        "title": record["title"],
        "canonical": record["canonical"],
    }


class SeoEngine:
    """Per-store SEO records. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._records: dict[str, dict[str, Any]] = {}

    def host(self) -> str:
        return _require_host(self.runtime.settings.get("canonical-host"))

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

    def get_record(self, product_id: object) -> dict[str, Any] | None:
        product_id = _require_id(product_id)
        if not self._using_sql():
            record = self._records.get(product_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, product_id, title, description, canonical, "
                "created_at, updated_at FROM seo_records "
                "WHERE store_id = %s AND product_id = %s",
                (self.store_id, product_id),
            )
        if row is None:
            return None
        return _seo_record(row)

    def list_records(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                dict(self._records[key]) for key in sorted(self._records)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, product_id, title, description, canonical, "
                "created_at, updated_at FROM seo_records "
                "WHERE store_id = %s ORDER BY product_id",
                (self.store_id,),
            )
        return tuple(_seo_record(row) for row in rows)

    def _persist(self, record: dict[str, Any], *, action: str) -> dict[str, Any]:
        stamp = record["updated_at"]
        product_id = record["product_id"]
        if not self._using_sql():
            self._records[product_id] = dict(record)
            self._emit(product_id, record["title"], action, stamp)
            return dict(record)
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "INSERT INTO seo_records ("
                "store_id, product_id, title, description, canonical, created_at, updated_at"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (store_id, product_id) DO UPDATE SET "
                "title = EXCLUDED.title, "
                "description = EXCLUDED.description, "
                "canonical = EXCLUDED.canonical, "
                "updated_at = EXCLUDED.updated_at",
                (
                    record["store_id"],
                    record["product_id"],
                    record["title"],
                    record["description"],
                    record["canonical"],
                    record["created_at"],
                    stamp,
                ),
            )
        self._emit(product_id, record["title"], action, stamp)
        return dict(record)

    def ensure_from_product(self, product: Mapping[str, Any]) -> dict[str, Any] | None:
        raw_id = product.get("id")
        try:
            product_id = _require_id(raw_id)
        except SeoError:
            return None
        if self.get_record(product_id) is not None:
            return None
        title = product.get("title")
        if not isinstance(title, str) or not title:
            title = f"Product {product_id}"
        try:
            title = _require_title(title)
        except SeoError:
            title = f"Product {product_id}"
        stamp = _now()
        record = {
            "store_id": self.store_id,
            "product_id": product_id,
            "title": title,
            "description": "",
            "canonical": _canonical(self.host(), product_id, product.get("sku")),
            "created_at": stamp,
            "updated_at": stamp,
        }
        return self._persist(record, action="ensured")

    def upsert_from_product(self, product: Mapping[str, Any]) -> dict[str, Any]:
        product_id = _require_id(product.get("id"), field="id")
        title = product.get("title")
        if not isinstance(title, str) or not title:
            title = f"Product {product_id}"
        title = _require_title(title)
        stamp = _now()
        existing = self.get_record(product_id)
        record = {
            "store_id": self.store_id,
            "product_id": product_id,
            "title": title,
            "description": _require_description(product.get("description")),
            "canonical": _canonical(self.host(), product_id, product.get("sku")),
            "created_at": existing["created_at"] if existing is not None else stamp,
            "updated_at": stamp,
        }
        return self._persist(record, action="upserted")

    def set_record(
        self, product_id: object, title: object, description: object = ""
    ) -> dict[str, Any]:
        product_id = _require_id(product_id)
        title = _require_title(title)
        description = _require_description(description)
        stamp = _now()
        existing = self.get_record(product_id)
        record = {
            "store_id": self.store_id,
            "product_id": product_id,
            "title": title,
            "description": description,
            "canonical": (
                existing["canonical"]
                if existing is not None
                else _canonical(self.host(), product_id, None)
            ),
            "created_at": existing["created_at"] if existing is not None else stamp,
            "updated_at": stamp,
        }
        return self._persist(record, action="set")

    def ensure_from_catalog(self) -> int:
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            return 0
        try:
            catalog = resolve("catalog.query", ">=1.0.0,<2.0.0")
        except Exception:
            return 0
        lister = getattr(catalog, "list", None)
        created = 0
        if not callable(lister):
            return 0
        for product in lister():
            if isinstance(product, dict) and self.ensure_from_product(product) is not None:
                created += 1
        return created

    def ensure_one(self, product_id: object) -> dict[str, Any] | None:
        try:
            product_id = _require_id(product_id)
        except SeoError:
            return None
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            return None
        try:
            catalog = resolve("catalog.query", ">=1.0.0,<2.0.0")
        except Exception:
            return None
        getter = getattr(catalog, "get", None)
        if not callable(getter):
            return None
        product = getter(product_id)
        if not isinstance(product, dict):
            return None
        return self.ensure_from_product(product)

    def _emit(self, product_id: str, title: str, action: str, stamp: str) -> None:
        self.runtime.events.publish(
            "seo.changed",
            "1.0.0",
            {"product_id": product_id, "title": title},
            idempotency_key=_event_key("seo.changed", product_id, action, stamp),
        )
        self.runtime.events.publish(
            "seo.recordChanged",
            "1.0.0",
            {"product_id": product_id, "title": title, "action": action},
            idempotency_key=_event_key(
                "seo.recordChanged", product_id, action, stamp
            ),
        )


class SeoQuery:
    def __init__(self, engine: SeoEngine) -> None:
        self._engine = engine

    def get(self, product_id) -> dict | None:
        record = self._engine.get_record(product_id)
        if record is None:
            return None
        return _facade_record(record)

    def list(self) -> tuple[dict, ...]:
        return tuple(_facade_record(item) for item in self._engine.list_records())

    def upsert(self, product: dict) -> dict:
        if not isinstance(product, dict):
            raise SeoError("product must be an object")
        return _facade_record(self._engine.upsert_from_product(product))


class SeoStorefront:
    def __init__(self, engine: SeoEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_records()

    def get(self, product_id: str) -> dict | None:
        return self._engine.get_record(product_id)

    def set(self, product_id: str, title: str, description: str = "") -> dict:
        return self._engine.set_record(product_id, title, description)
