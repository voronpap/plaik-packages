"""Data Exchange 1.0.0. JSON/CSV import into catalog.query.upsert."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SOURCES = frozenset({"json", "csv"})
_PRODUCT_KEYS = ("id", "sku", "title")


class DataExchangeError(ValueError):
    """A data-exchange command was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex


def _require_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise DataExchangeError(f"invalid {field}")
    return value


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


def _run_record(row: Mapping[str, Any]) -> dict[str, Any]:
    product_ids = str(row.get("product_ids") or "")
    identifiers = [item for item in product_ids.split(",") if item]
    return {
        "store_id": _row_str(row, "store_id"),
        "import_id": _row_str(row, "import_id"),
        "source": _row_str(row, "source"),
        "product_count": int(row["product_count"]),
        "product_ids": identifiers,
        "created_at": _iso(row["created_at"]),
        "replayed": bool(row.get("replayed")),
    }


def _product_document(item: object) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise DataExchangeError("product must be an object")
    document: dict[str, Any] = {}
    for key in _PRODUCT_KEYS:
        value = item.get(key)
        if value is None or value == "":
            raise DataExchangeError(f"{key} is required")
        document[key] = str(value)
    attributes = item.get("attributes")
    if attributes is not None:
        if not isinstance(attributes, Mapping):
            raise DataExchangeError("attributes must be an object")
        document["attributes"] = dict(attributes)
    return document


def _products_from_json(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    products = payload.get("products")
    if isinstance(products, str):
        try:
            products = json.loads(products)
        except json.JSONDecodeError as error:
            raise DataExchangeError("invalid json products") from error
    if not isinstance(products, list):
        raise DataExchangeError("products must be a list")
    return [_product_document(item) for item in products]


def _products_from_csv(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    text = payload.get("csv")
    if not isinstance(text, str) or not text.strip():
        raise DataExchangeError("csv text is required")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise DataExchangeError("csv header is required")
    got = {str(name).strip() for name in reader.fieldnames}
    if not set(_PRODUCT_KEYS) <= got:
        raise DataExchangeError("csv columns id,sku,title are required")
    documents: list[dict[str, Any]] = []
    for row in reader:
        documents.append(
            _product_document(
                {
                    "id": str(row.get("id") or "").strip(),
                    "sku": str(row.get("sku") or "").strip(),
                    "title": str(row.get("title") or "").strip(),
                }
            )
        )
    return documents


class DataExchangeEngine:
    """Per-store catalog import. PostgreSQL journal is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._runs: dict[str, dict[str, Any]] = {}

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

    def import_products(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise DataExchangeError("payload must be an object")
        if payload.get("url"):
            raise DataExchangeError("remote urls are forbidden")
        source = str(payload.get("format") or payload.get("source") or "json")
        if source not in _SOURCES:
            raise DataExchangeError("format must be json or csv")
        raw_id = payload.get("import_id") or payload.get("idempotency_key")
        import_id = _new_id() if raw_id in (None, "") else _require_id(
            raw_id, field="import_id"
        )
        existing = self._load(import_id)
        if existing is not None:
            replay = dict(existing)
            replay["replayed"] = True
            return _run_record(replay)
        documents = (
            _products_from_csv(payload) if source == "csv" else _products_from_json(payload)
        )
        catalog = self.runtime.services.resolve("catalog.query", "==1.0.0")
        product_ids: list[str] = []
        for document in documents:
            upserted = catalog.upsert(document)
            product_ids.append(str(upserted["id"]))
        stamp = _now()
        record = {
            "store_id": self.store_id,
            "import_id": import_id,
            "source": source,
            "product_count": len(product_ids),
            "product_ids": ",".join(product_ids),
            "created_at": stamp,
            "replayed": False,
        }
        self._write(record)
        self._publish(record, stamp)
        return _run_record(record)

    def get_import(self, import_id: object) -> dict[str, Any] | None:
        import_id = _require_id(import_id, field="import_id")
        row = self._load(import_id)
        if row is None:
            return None
        return _run_record(row)

    def _load(self, import_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._runs.get(import_id)
            return None if record is None else dict(record)
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                "SELECT store_id, import_id, source, product_count, product_ids, created_at "
                "FROM import_runs WHERE store_id = %s AND import_id = %s",
                (self.store_id, import_id),
            )
        if row is None:
            return None
        return dict(row)

    def _write(self, record: Mapping[str, Any]) -> None:
        if not self._using_sql():
            self._runs[str(record["import_id"])] = dict(record)
            return
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "INSERT INTO import_runs ("
                "store_id, import_id, source, product_count, product_ids, created_at"
                ") VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    record["store_id"],
                    record["import_id"],
                    record["source"],
                    record["product_count"],
                    record["product_ids"],
                    record["created_at"],
                ),
            )

    def _publish(self, record: Mapping[str, Any], stamp: str) -> None:
        self.runtime.events.publish(
            "data-exchange.imported",
            "1.0.0",
            {
                "import_id": record["import_id"],
                "product_count": record["product_count"],
            },
            idempotency_key=_event_key(
                "data-exchange.imported",
                str(record["import_id"]),
                "imported",
                stamp,
            ),
        )


class DataExchangeImport:
    def __init__(self, engine: DataExchangeEngine) -> None:
        self._engine = engine

    def import_products(self, payload: Mapping[str, Any]) -> dict:
        return self._engine.import_products(payload)

    def get(self, import_id) -> dict | None:
        return self._engine.get_import(import_id)
