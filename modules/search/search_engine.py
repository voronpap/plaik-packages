"""Search 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from plaik_sdk import ExtensionRuntime

_FACET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_FACET_VALUE = re.compile(r"^[^\x00-\x1f]{1,128}$")


class SearchError(ValueError):
    """A search command or service call was rejected."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


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


def _facet_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "store_id": _row_str(row, "store_id"),
        "name": _row_str(row, "name"),
        "value": _row_str(row, "value"),
        "product_count": int(row["product_count"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _facade_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": record["name"],
        "value": record["value"],
        "product_count": int(record["product_count"]),
    }


def _facet_limit(raw: object) -> int:
    if raw is None or raw == "":
        return 50
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 50
    if value < 1:
        return 50
    return min(value, 500)


def _counts_from_products(products: Sequence[object]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        attributes = product.get("attributes")
        if not isinstance(attributes, dict):
            continue
        for name, value in attributes.items():
            name_text = str(name)
            if isinstance(value, (dict, list, tuple)):
                continue
            value_text = str(value)
            if not _FACET_NAME.fullmatch(name_text):
                continue
            if not _FACET_VALUE.fullmatch(value_text):
                continue
            key = (name_text, value_text)
            counts[key] = counts.get(key, 0) + 1
    return counts


class SearchEngine:
    """Per-store attribute facets. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._facets: dict[tuple[str, str], dict[str, Any]] = {}

    def facet_limit(self) -> int:
        return _facet_limit(self.runtime.settings.get("facet-limit"))

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

    def list_facets(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(
                dict(self._facets[key])
                for key in sorted(self._facets)
            )
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT store_id, name, value, product_count, created_at, updated_at "
                "FROM facet_values WHERE store_id = %s ORDER BY name, value",
                (self.store_id,),
            )
        return tuple(_facet_record(row) for row in rows)

    def replace_counts(self, counts: Mapping[tuple[str, str], int]) -> int:
        stamp = _now()
        records = []
        for name, value in sorted(counts):
            records.append(
                {
                    "store_id": self.store_id,
                    "name": name,
                    "value": value,
                    "product_count": int(counts[(name, value)]),
                    "created_at": stamp,
                    "updated_at": stamp,
                }
            )
        if not self._using_sql():
            self._facets = {
                (item["name"], item["value"]): dict(item) for item in records
            }
            self._emit(len(records), stamp)
            return len(records)
        with self.runtime.sql.transaction() as tx:
            tx.execute(
                "DELETE FROM facet_values WHERE store_id = %s",
                (self.store_id,),
            )
            for item in records:
                tx.execute(
                    "INSERT INTO facet_values ("
                    "store_id, name, value, product_count, created_at, updated_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        item["store_id"],
                        item["name"],
                        item["value"],
                        item["product_count"],
                        item["created_at"],
                        item["updated_at"],
                    ),
                )
        self._emit(len(records), stamp)
        return len(records)

    def rebuild_from_products(self, products: Sequence[object]) -> int:
        return self.replace_counts(_counts_from_products(products))

    def rebuild_from_catalog(self) -> int:
        resolve = getattr(self.runtime.services, "resolve", None)
        if not callable(resolve):
            return self.replace_counts({})
        try:
            catalog = resolve("catalog.query", ">=1.0.0,<2.0.0")
        except Exception:
            return self.replace_counts({})
        if not callable(getattr(catalog, "list", None)):
            return self.replace_counts({})
        return self.rebuild_from_products(catalog.list())

    def _emit(self, facet_count: int, stamp: str) -> None:
        payload = {"facet_count": facet_count}
        self.runtime.events.publish(
            "search.reindexed",
            "1.0.0",
            payload,
            idempotency_key=_event_key(
                "search.reindexed", self.store_id, "rebuilt", stamp
            ),
        )
        self.runtime.events.publish(
            "search.facetsChanged",
            "1.0.0",
            {"facet_count": facet_count, "action": "rebuilt"},
            idempotency_key=_event_key(
                "search.facetsChanged", self.store_id, "rebuilt", stamp
            ),
        )


class SearchQuery:
    def __init__(self, engine: SearchEngine) -> None:
        self._engine = engine

    def facets(self) -> tuple[dict, ...]:
        limit = self._engine.facet_limit()
        items = tuple(_facade_record(item) for item in self._engine.list_facets())
        return items[:limit]

    def rebuild(self, products: Sequence[object]) -> None:
        self._engine.rebuild_from_products(products)


class SearchFacets:
    def __init__(self, engine: SearchEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_facets()
