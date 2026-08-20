"""Catalog 1.0.0 domain. Depends only on public plaik-sdk."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from plaik_sdk import ExtensionRuntime

_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STATUSES = frozenset({"draft", "published", "archived"})
_KINDS = frozenset({"standalone", "parent", "variant"})
_ATTR_TYPES = frozenset({"text", "integer", "boolean", "select"})
_PRODUCT_COLUMNS = (
    "id, store_id, sku, slug, title, status, kind, parent_id, brand_id, "
    "created_at, updated_at"
)


class CatalogError(ValueError):
    """A catalog command or service call was rejected."""


def _new_id() -> str:
    return uuid4().hex


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _require_id(value: object, *, field: str = "id") -> str:
    if not isinstance(value, str) or not _RESOURCE_ID.fullmatch(value):
        raise CatalogError(f"invalid {field}")
    return value


def _optional_id(value: object, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    return _require_id(value, field=field)


def _coerce_id(value: object, *, field: str = "id") -> str:
    if isinstance(value, str):
        return _require_id(value, field=field)
    if isinstance(value, int) and not isinstance(value, bool):
        return _require_id(str(value), field=field)
    raise CatalogError(f"invalid {field}")


def _slug_from(title: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")
    return slug or fallback.casefold()


def _iso(value: object) -> str:
    converter = getattr(value, "isoformat", None)
    if callable(converter):
        return str(converter())
    return str(value)


def _sql_missing(error: BaseException) -> bool:
    text = str(error).lower()
    return "unavailable" in text or "no longer bound" in text


def _sql_conflict(error: BaseException) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in ("unique", "duplicate", "integrity", "foreign key", "constraint")
    )


def _row_str(row: Mapping[str, Any], key: str) -> str:
    return str(row[key])


def _row_opt(row: Mapping[str, Any], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    return str(value)


def _product_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _row_str(row, "id"),
        "store_id": _row_str(row, "store_id"),
        "sku": _row_str(row, "sku"),
        "slug": _row_str(row, "slug"),
        "title": _row_str(row, "title"),
        "status": _row_str(row, "status"),
        "kind": _row_str(row, "kind"),
        "parent_id": _row_opt(row, "parent_id"),
        "brand_id": _row_opt(row, "brand_id"),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


class CatalogEngine:
    """Per-store catalog. PostgreSQL is the system of record when SQL is bound."""

    def __init__(self, runtime: ExtensionRuntime) -> None:
        self.runtime = runtime
        self.store_id = runtime.store_id
        self._mode: str | None = None
        self._brands: dict[str, dict[str, Any]] = {}
        self._categories: dict[str, dict[str, Any]] = {}
        self._attributes: dict[str, dict[str, Any]] = {}
        self._options: dict[str, dict[str, Any]] = {}
        self._products: dict[str, dict[str, Any]] = {}
        self._axes: dict[str, list[str]] = {}
        self._product_categories: dict[str, set[str]] = {}
        self._values: dict[tuple[str, str], dict[str, Any]] = {}
        self._media: dict[str, dict[str, Any]] = {}

    def _using_sql(self) -> bool:
        if self._mode is not None:
            return self._mode == "sql"
        try:
            with self.runtime.sql.transaction() as tx:
                tx.fetchone("SELECT 1")
        except Exception as error:
            if _sql_missing(error):
                self._mode = "memory"
                return False
            raise
        self._mode = "sql"
        return True

    def _page_size(self) -> int:
        raw = self.runtime.settings.get("page-size", 50)
        try:
            size = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 50
        return min(max(size, 1), 200)

    def _default_status(self) -> str:
        raw = self.runtime.settings.get("default-status", "draft")
        if raw in _STATUSES:
            return str(raw)
        return "draft"

    def _emit_product(self, *, action: str, product_id: str, sku: str) -> None:
        token = uuid4().hex
        payload = {"product_id": product_id, "sku": sku, "action": action}
        self.runtime.events.publish(
            "catalog.changed",
            "1.0.0",
            payload,
            idempotency_key=f"catalog.changed:{product_id}:{action}:{token}",
        )
        self.runtime.events.publish(
            "catalog.productChanged",
            "1.0.0",
            {"id": product_id, "sku": sku, "action": action},
            idempotency_key=f"catalog.productChanged:{product_id}:{action}:{token}",
        )

    def _emit_category(self, *, action: str, category_id: str) -> None:
        token = uuid4().hex
        self.runtime.events.publish(
            "catalog.categoryChanged",
            "1.0.0",
            {"id": category_id, "action": action},
            idempotency_key=f"catalog.categoryChanged:{category_id}:{action}:{token}",
        )

    def _emit_attribute(self, *, action: str, attribute_id: str) -> None:
        token = uuid4().hex
        self.runtime.events.publish(
            "catalog.attributeChanged",
            "1.0.0",
            {"id": attribute_id, "action": action},
            idempotency_key=f"catalog.attributeChanged:{attribute_id}:{action}:{token}",
        )

    def _load_attributes(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(self._attributes.values())
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT id, store_id, code, name, type, created_at, updated_at "
                "FROM attribute_definitions WHERE store_id = %s ORDER BY code",
                (self.store_id,),
            )
        return tuple(
            {
                "id": _row_str(row, "id"),
                "store_id": _row_str(row, "store_id"),
                "code": _row_str(row, "code"),
                "name": _row_str(row, "name"),
                "type": _row_str(row, "type"),
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
            }
            for row in rows
        )

    def _load_options(self) -> tuple[dict[str, Any], ...]:
        if not self._using_sql():
            return tuple(self._options.values())
        with self.runtime.sql.transaction() as tx:
            rows = tx.fetchall(
                "SELECT id, store_id, attribute_id, code, label, position, "
                "created_at, updated_at FROM attribute_options "
                "WHERE store_id = %s ORDER BY attribute_id, position, code",
                (self.store_id,),
            )
        return tuple(
            {
                "id": _row_str(row, "id"),
                "store_id": _row_str(row, "store_id"),
                "attribute_id": _row_str(row, "attribute_id"),
                "code": _row_str(row, "code"),
                "label": _row_str(row, "label"),
                "position": int(row["position"] or 0),
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
            }
            for row in rows
        )

    def _attribute_by_code(self) -> dict[str, dict[str, Any]]:
        return {item["code"]: item for item in self._load_attributes()}

    def _get_product_record(self, product_id: str) -> dict[str, Any] | None:
        if not self._using_sql():
            record = self._products.get(product_id)
            return dict(record) if record is not None else None
        with self.runtime.sql.transaction() as tx:
            row = tx.fetchone(
                f"SELECT {_PRODUCT_COLUMNS} FROM products "
                "WHERE store_id = %s AND id = %s",
                (self.store_id, product_id),
            )
        return None if row is None else _product_record(row)

    def _facade_attributes(self, product_id: str) -> dict[str, Any]:
        definitions = {item["id"]: item for item in self._load_attributes()}
        options = {item["id"]: item for item in self._load_options()}
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                rows = tx.fetchall(
                    "SELECT product_id, attribute_id, value_text, value_integer, "
                    "value_boolean, option_id FROM product_attribute_values "
                    "WHERE store_id = %s AND product_id = %s",
                    (self.store_id, product_id),
                )
            stored = [
                {
                    "attribute_id": _row_str(row, "attribute_id"),
                    "value_text": row["value_text"],
                    "value_integer": row["value_integer"],
                    "value_boolean": row["value_boolean"],
                    "option_id": _row_opt(row, "option_id"),
                }
                for row in rows
            ]
        else:
            stored = [
                {"attribute_id": attribute_id, **row}
                for (pid, attribute_id), row in self._values.items()
                if pid == product_id
            ]
        values: dict[str, Any] = {}
        for row in stored:
            definition = definitions.get(row["attribute_id"])
            if definition is None:
                continue
            code = definition["code"]
            if definition["type"] == "select":
                option = options.get(str(row.get("option_id") or ""))
                values[code] = option["code"] if option else None
            elif definition["type"] == "integer":
                values[code] = row.get("value_integer")
            elif definition["type"] == "boolean":
                raw = row.get("value_boolean")
                values[code] = None if raw is None else bool(raw)
            else:
                values[code] = row.get("value_text")
        return values

    def _facade_product(self, product: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": product["id"],
            "sku": product["sku"],
            "title": product["title"],
            "attributes": self._facade_attributes(str(product["id"])),
        }

    def query_get(self, product_id: object) -> dict[str, Any] | None:
        identifier = _coerce_id(product_id)
        product = self._get_product_record(identifier)
        if product is None:
            return None
        return self._facade_product(product)

    def query_list(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._facade_product(item) for item in self.list_products())

    def query_upsert(self, product: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(product, dict):
            raise CatalogError("product must be an object")
        raw_id = product.get("id")
        identifier = None if raw_id is None else _coerce_id(raw_id)
        existing = None if identifier is None else self._get_product_record(identifier)
        payload = {
            "id": identifier,
            "sku": product.get("sku") or (existing["sku"] if existing else None),
            "title": product.get("title") or (existing["title"] if existing else None),
            "attributes": product.get("attributes") if "attributes" in product else None,
        }
        if existing is None:
            created = self.create_product(payload)
            return self._facade_product(created)
        updated = self.update_product(existing["id"], payload)
        return self._facade_product(updated)

    def _sku_taken(self, sku: str, *, exclude: str | None = None) -> bool:
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                row = tx.fetchone(
                    "SELECT id FROM products WHERE store_id = %s AND sku = %s",
                    (self.store_id, sku),
                )
            return row is not None and (exclude is None or str(row["id"]) != exclude)
        return any(
            item["sku"] == sku and item["id"] != exclude
            for item in self._products.values()
        )

    def _slug_taken(self, slug: str, *, exclude: str | None = None) -> bool:
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                row = tx.fetchone(
                    "SELECT id FROM products WHERE store_id = %s AND slug = %s",
                    (self.store_id, slug),
                )
            return row is not None and (exclude is None or str(row["id"]) != exclude)
        return any(
            item["slug"] == slug and item["id"] != exclude
            for item in self._products.values()
        )

    def _brand_exists(self, brand_id: str) -> bool:
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                row = tx.fetchone(
                    "SELECT id FROM brands WHERE store_id = %s AND id = %s",
                    (self.store_id, brand_id),
                )
            return row is not None
        return brand_id in self._brands

    def _load_axes(self, parent_id: str) -> tuple[str, ...]:
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                rows = tx.fetchall(
                    "SELECT attribute_id FROM product_variant_axes "
                    "WHERE store_id = %s AND parent_product_id = %s "
                    "ORDER BY position, attribute_id",
                    (self.store_id, parent_id),
                )
            return tuple(_row_str(row, "attribute_id") for row in rows)
        return tuple(self._axes.get(parent_id, ()))

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        sku = str(payload.get("sku") or "")
        title = str(payload.get("title") or "")
        if not _SKU.fullmatch(sku):
            raise CatalogError("invalid sku")
        if not title:
            raise CatalogError("title is required")
        identifier = payload.get("id")
        product_id = _require_id(identifier) if identifier else _new_id()
        if self._get_product_record(product_id) is not None:
            raise CatalogError("product id already exists")
        if self._sku_taken(sku):
            raise CatalogError("sku already exists")
        slug = str(payload.get("slug") or _slug_from(title, sku))
        if not _SLUG.fullmatch(slug):
            raise CatalogError("invalid slug")
        if self._slug_taken(slug):
            raise CatalogError("slug already exists")
        status = str(payload.get("status") or self._default_status())
        kind = str(payload.get("kind") or "standalone")
        if status not in _STATUSES or kind not in _KINDS:
            raise CatalogError("invalid product status or kind")
        parent_id = _optional_id(payload.get("parent_id"), field="parent_id")
        parent = None if parent_id is None else self._get_product_record(parent_id)
        if kind == "variant":
            if parent is None or parent["kind"] != "parent":
                raise CatalogError("variant requires a parent product")
        elif parent_id is not None:
            raise CatalogError("only variants may set parent_id")
        brand_id = _optional_id(payload.get("brand_id"), field="brand_id")
        if brand_id is not None and not self._brand_exists(brand_id):
            raise CatalogError("brand is unknown")
        now = _now()
        record = {
            "id": product_id,
            "store_id": self.store_id,
            "sku": sku,
            "slug": slug,
            "title": title,
            "status": status,
            "kind": kind,
            "parent_id": parent_id,
            "brand_id": brand_id,
            "created_at": now,
            "updated_at": now,
        }
        attributes = payload.get("attributes")
        if attributes is not None:
            self._assign_attribute_map(product_id, attributes, persist=False)
        if kind == "variant":
            self._assert_variant_cover(parent_id or "", product_id, pending=attributes)
        if self._using_sql():
            self._sql_insert_product(record, attributes)
        else:
            self._products[product_id] = record
            if attributes is not None:
                self._assign_attribute_map(product_id, attributes)
        self._emit_product(action="created", product_id=product_id, sku=sku)
        return dict(record)

    def _sql_insert_product(
        self,
        record: dict[str, Any],
        attributes: object | None,
    ) -> None:
        try:
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO products ("
                    "id, store_id, sku, slug, title, status, kind, parent_id, "
                    "brand_id, created_at, updated_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        record["id"],
                        record["store_id"],
                        record["sku"],
                        record["slug"],
                        record["title"],
                        record["status"],
                        record["kind"],
                        record["parent_id"],
                        record["brand_id"],
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
                if attributes is not None:
                    self._sql_assign_values(tx, record["id"], attributes)
        except CatalogError:
            raise
        except Exception as error:
            if _sql_conflict(error):
                raise CatalogError("product could not be stored") from error
            raise

    def update_product(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self._get_product_record(_require_id(product_id))
        if record is None:
            raise CatalogError("product is unknown")
        sku = str(payload.get("sku") or record["sku"])
        title = str(payload.get("title") or record["title"])
        slug = str(payload.get("slug") or record["slug"])
        status = str(payload.get("status") or record["status"])
        if not _SKU.fullmatch(sku) or not title or not _SLUG.fullmatch(slug):
            raise CatalogError("invalid product fields")
        if status not in _STATUSES:
            raise CatalogError("invalid product status")
        if self._sku_taken(sku, exclude=product_id):
            raise CatalogError("sku already exists")
        if self._slug_taken(slug, exclude=product_id):
            raise CatalogError("slug already exists")
        if payload.get("brand_id") is not None or "brand_id" in payload:
            brand_id = _optional_id(payload.get("brand_id"), field="brand_id")
            if brand_id is not None and not self._brand_exists(brand_id):
                raise CatalogError("brand is unknown")
            record["brand_id"] = brand_id
        record.update(
            {
                "sku": sku,
                "title": title,
                "slug": slug,
                "status": status,
                "updated_at": _now(),
            }
        )
        attributes = payload.get("attributes")
        if attributes is not None:
            self._assign_attribute_map(product_id, attributes, persist=False)
        if self._using_sql():
            try:
                with self.runtime.sql.transaction() as tx:
                    tx.execute(
                        "UPDATE products SET sku = %s, title = %s, slug = %s, "
                        "status = %s, brand_id = %s, updated_at = %s "
                        "WHERE store_id = %s AND id = %s",
                        (
                            record["sku"],
                            record["title"],
                            record["slug"],
                            record["status"],
                            record["brand_id"],
                            record["updated_at"],
                            self.store_id,
                            product_id,
                        ),
                    )
                    if attributes is not None:
                        self._sql_assign_values(tx, product_id, attributes)
            except CatalogError:
                raise
            except Exception as error:
                if _sql_conflict(error):
                    raise CatalogError("product could not be stored") from error
                raise
        else:
            self._products[product_id].update(record)
            if attributes is not None:
                self._assign_attribute_map(product_id, attributes)
        action = "archived" if status == "archived" else "changed"
        self._emit_product(action=action, product_id=product_id, sku=sku)
        return dict(record)

    def archive_product(self, product_id: str) -> dict[str, Any]:
        return self.update_product(product_id, {"status": "archived"})

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        return self._get_product_record(_require_id(product_id))

    def list_products(self) -> tuple[dict[str, Any], ...]:
        limit = self._page_size()
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                rows = tx.fetchall(
                    f"SELECT {_PRODUCT_COLUMNS} FROM products "
                    "WHERE store_id = %s ORDER BY id LIMIT %s",
                    (self.store_id, limit),
                )
            return tuple(_product_record(row) for row in rows)
        rows = [dict(self._products[key]) for key in sorted(self._products)]
        return tuple(rows[:limit])

    def _assign_attribute_map(
        self,
        product_id: str,
        attributes: object,
        *,
        persist: bool = True,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not isinstance(attributes, dict):
            raise CatalogError("attributes must be an object")
        by_code = self._attribute_by_code()
        assigned: dict[tuple[str, str], dict[str, Any]] = {}
        for code, value in attributes.items():
            if not isinstance(code, str) or code not in by_code:
                raise CatalogError(f"unknown attribute code: {code}")
            assigned[(product_id, by_code[code]["id"])] = self._value_row(
                by_code[code], value
            )
        if persist and not self._using_sql():
            self._values.update(assigned)
        elif persist and self._using_sql():
            with self.runtime.sql.transaction() as tx:
                self._sql_write_values(tx, product_id, assigned)
        return assigned

    def _value_row(self, definition: dict[str, Any], value: object) -> dict[str, Any]:
        row: dict[str, Any] = {
            "value_text": None,
            "value_integer": None,
            "value_boolean": None,
            "option_id": None,
        }
        attr_type = definition["type"]
        if attr_type == "text":
            row["value_text"] = "" if value is None else str(value)
        elif attr_type == "integer":
            try:
                row["value_integer"] = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError) as error:
                raise CatalogError("attribute value must be an integer") from error
        elif attr_type == "boolean":
            if not isinstance(value, bool):
                raise CatalogError("attribute value must be a boolean")
            row["value_boolean"] = value
        elif attr_type == "select":
            option = None
            for item in self._load_options():
                if item["attribute_id"] != definition["id"]:
                    continue
                if value in {item["id"], item["code"]}:
                    option = item
                    break
            if option is None:
                raise CatalogError("attribute option is unknown")
            row["option_id"] = option["id"]
        return row

    def _sql_assign_values(self, tx: Any, product_id: str, attributes: object) -> None:
        assigned = self._assign_attribute_map(product_id, attributes, persist=False)
        self._sql_write_values(tx, product_id, assigned)

    def _sql_write_values(
        self,
        tx: Any,
        product_id: str,
        assigned: Mapping[tuple[str, str], dict[str, Any]],
    ) -> None:
        for (_pid, attribute_id), row in assigned.items():
            tx.execute(
                "INSERT INTO product_attribute_values ("
                "store_id, product_id, attribute_id, value_text, value_integer, "
                "value_boolean, option_id"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (store_id, product_id, attribute_id) DO UPDATE SET "
                "value_text = EXCLUDED.value_text, "
                "value_integer = EXCLUDED.value_integer, "
                "value_boolean = EXCLUDED.value_boolean, "
                "option_id = EXCLUDED.option_id",
                (
                    self.store_id,
                    product_id,
                    attribute_id,
                    row["value_text"],
                    row["value_integer"],
                    row["value_boolean"],
                    row["option_id"],
                ),
            )

    def _assert_variant_cover(
        self,
        parent_id: str,
        product_id: str,
        pending: object | None,
    ) -> None:
        axes = self._load_axes(parent_id)
        if not axes:
            raise CatalogError("variant requires parent axes")
        facade = dict(self._facade_attributes(product_id))
        if isinstance(pending, dict):
            facade.update(pending)
        definitions = {item["id"]: item for item in self._load_attributes()}
        for attribute_id in axes:
            definition = definitions.get(attribute_id)
            if definition is None or definition["code"] not in facade:
                raise CatalogError("variant must cover parent axes")
        seen: set[tuple[object, ...]] = set()
        siblings = [
            item
            for item in self.list_products()
            if item["kind"] == "variant"
            and item["parent_id"] == parent_id
            and item["id"] != product_id
        ]
        for sibling in siblings:
            values = self._facade_attributes(sibling["id"])
            key = tuple(values.get(definitions[attr]["code"]) for attr in axes)
            seen.add(key)
        current = tuple(facade.get(definitions[attr]["code"]) for attr in axes)
        if current in seen:
            raise CatalogError("variant axis combination already exists")

    def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "")
        if not name:
            raise CatalogError("category name is required")
        identifier = payload.get("id")
        category_id = _require_id(identifier) if identifier else _new_id()
        if self.get_category(category_id) is not None:
            raise CatalogError("category id already exists")
        slug = str(payload.get("slug") or _slug_from(name, category_id[:8]))
        if not _SLUG.fullmatch(slug):
            raise CatalogError("invalid slug")
        if any(item["slug"] == slug for item in self.list_categories()):
            raise CatalogError("slug already exists")
        parent_id = _optional_id(payload.get("parent_id"), field="parent_id")
        if parent_id is not None and self.get_category(parent_id) is None:
            raise CatalogError("parent category is unknown")
        now = _now()
        record = {
            "id": category_id,
            "store_id": self.store_id,
            "slug": slug,
            "name": name,
            "parent_id": parent_id,
            "created_at": now,
            "updated_at": now,
        }
        if self._using_sql():
            try:
                with self.runtime.sql.transaction() as tx:
                    tx.execute(
                        "INSERT INTO categories ("
                        "id, store_id, slug, name, parent_id, created_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            category_id,
                            self.store_id,
                            slug,
                            name,
                            parent_id,
                            now,
                            now,
                        ),
                    )
            except Exception as error:
                if _sql_conflict(error):
                    raise CatalogError("category could not be stored") from error
                raise
        else:
            self._categories[category_id] = record
        self._emit_category(action="created", category_id=category_id)
        return dict(record)

    def update_category(self, category_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.get_category(category_id)
        if record is None:
            raise CatalogError("category is unknown")
        name = str(payload.get("name") or record["name"])
        slug = str(payload.get("slug") or record["slug"])
        if not name or not _SLUG.fullmatch(slug):
            raise CatalogError("invalid category fields")
        record.update({"name": name, "slug": slug, "updated_at": _now()})
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "UPDATE categories SET name = %s, slug = %s, updated_at = %s "
                    "WHERE store_id = %s AND id = %s",
                    (name, slug, record["updated_at"], self.store_id, category_id),
                )
        else:
            self._categories[category_id].update(record)
        self._emit_category(action="changed", category_id=category_id)
        return dict(record)

    def get_category(self, category_id: str) -> dict[str, Any] | None:
        identifier = _require_id(category_id)
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                row = tx.fetchone(
                    "SELECT id, store_id, slug, name, parent_id, created_at, updated_at "
                    "FROM categories WHERE store_id = %s AND id = %s",
                    (self.store_id, identifier),
                )
            if row is None:
                return None
            return {
                "id": _row_str(row, "id"),
                "store_id": _row_str(row, "store_id"),
                "slug": _row_str(row, "slug"),
                "name": _row_str(row, "name"),
                "parent_id": _row_opt(row, "parent_id"),
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
            }
        record = self._categories.get(identifier)
        return dict(record) if record is not None else None

    def list_categories(self) -> tuple[dict[str, Any], ...]:
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                rows = tx.fetchall(
                    "SELECT id, store_id, slug, name, parent_id, created_at, updated_at "
                    "FROM categories WHERE store_id = %s ORDER BY slug",
                    (self.store_id,),
                )
            return tuple(
                {
                    "id": _row_str(row, "id"),
                    "store_id": _row_str(row, "store_id"),
                    "slug": _row_str(row, "slug"),
                    "name": _row_str(row, "name"),
                    "parent_id": _row_opt(row, "parent_id"),
                    "created_at": _iso(row["created_at"]),
                    "updated_at": _iso(row["updated_at"]),
                }
                for row in rows
            )
        return tuple(dict(self._categories[key]) for key in sorted(self._categories))

    def create_attribute(self, payload: dict[str, Any]) -> dict[str, Any]:
        code = str(payload.get("code") or "")
        name = str(payload.get("name") or code)
        attr_type = str(payload.get("type") or "text")
        if not _CODE.fullmatch(code) or attr_type not in _ATTR_TYPES or not name:
            raise CatalogError("invalid attribute definition")
        if any(item["code"] == code for item in self._load_attributes()):
            raise CatalogError("attribute code already exists")
        identifier = payload.get("id")
        attribute_id = _require_id(identifier) if identifier else _new_id()
        now = _now()
        record = {
            "id": attribute_id,
            "store_id": self.store_id,
            "code": code,
            "name": name,
            "type": attr_type,
            "created_at": now,
            "updated_at": now,
        }
        if self._using_sql():
            try:
                with self.runtime.sql.transaction() as tx:
                    tx.execute(
                        "INSERT INTO attribute_definitions ("
                        "id, store_id, code, name, type, created_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (attribute_id, self.store_id, code, name, attr_type, now, now),
                    )
            except Exception as error:
                if _sql_conflict(error):
                    raise CatalogError("attribute could not be stored") from error
                raise
        else:
            self._attributes[attribute_id] = record
        self._emit_attribute(action="created", attribute_id=attribute_id)
        return dict(record)

    def update_attribute(self, attribute_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        identifier = _require_id(attribute_id)
        current = next(
            (item for item in self._load_attributes() if item["id"] == identifier),
            None,
        )
        if current is None:
            raise CatalogError("attribute is unknown")
        name = str(payload.get("name") or current["name"])
        if not name:
            raise CatalogError("attribute name is required")
        current = dict(current)
        current.update({"name": name, "updated_at": _now()})
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "UPDATE attribute_definitions SET name = %s, updated_at = %s "
                    "WHERE store_id = %s AND id = %s",
                    (name, current["updated_at"], self.store_id, identifier),
                )
        else:
            self._attributes[identifier].update(current)
        self._emit_attribute(action="changed", attribute_id=identifier)
        return current

    def list_attributes(self) -> tuple[dict[str, Any], ...]:
        return tuple(sorted(self._load_attributes(), key=lambda item: item["id"]))

    def create_option(self, attribute_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        definition = next(
            (
                item
                for item in self._load_attributes()
                if item["id"] == _require_id(attribute_id)
            ),
            None,
        )
        if definition is None or definition["type"] != "select":
            raise CatalogError("select attribute is required")
        code = str(payload.get("code") or "")
        label = str(payload.get("label") or code)
        if not _CODE.fullmatch(code) or not label:
            raise CatalogError("invalid attribute option")
        option_id = _new_id()
        now = _now()
        record = {
            "id": option_id,
            "store_id": self.store_id,
            "attribute_id": attribute_id,
            "code": code,
            "label": label,
            "position": int(payload.get("position") or 0),
            "created_at": now,
            "updated_at": now,
        }
        if self._using_sql():
            try:
                with self.runtime.sql.transaction() as tx:
                    tx.execute(
                        "INSERT INTO attribute_options ("
                        "id, store_id, attribute_id, code, label, position, "
                        "created_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            option_id,
                            self.store_id,
                            attribute_id,
                            code,
                            label,
                            record["position"],
                            now,
                            now,
                        ),
                    )
            except Exception as error:
                if _sql_conflict(error):
                    raise CatalogError("attribute option could not be stored") from error
                raise
        else:
            self._options[option_id] = record
        self._emit_attribute(action="changed", attribute_id=attribute_id)
        return dict(record)

    def list_options(self, attribute_id: str) -> tuple[dict[str, Any], ...]:
        identifier = _require_id(attribute_id)
        return tuple(
            dict(item)
            for item in self._load_options()
            if item["attribute_id"] == identifier
        )

    def assign_category(self, product_id: str, category_id: str) -> None:
        if self._get_product_record(_require_id(product_id)) is None:
            raise CatalogError("product is unknown")
        if self.get_category(_require_id(category_id)) is None:
            raise CatalogError("category is unknown")
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO product_categories (store_id, product_id, category_id) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (store_id, product_id, category_id) DO NOTHING",
                    (self.store_id, product_id, category_id),
                )
        else:
            self._product_categories.setdefault(product_id, set()).add(category_id)

    def set_variant_axes(self, parent_id: str, attribute_ids: list[str]) -> None:
        parent = self._get_product_record(_require_id(parent_id))
        if parent is None or parent["kind"] != "parent":
            raise CatalogError("parent product is required")
        unique: list[str] = []
        seen: set[str] = set()
        definitions = {item["id"]: item for item in self._load_attributes()}
        for raw in attribute_ids:
            attribute_id = _require_id(raw, field="attribute_id")
            if attribute_id in seen:
                continue
            if attribute_id not in definitions:
                raise CatalogError("axis attribute is unknown")
            seen.add(attribute_id)
            unique.append(attribute_id)
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "DELETE FROM product_variant_axes "
                    "WHERE store_id = %s AND parent_product_id = %s",
                    (self.store_id, parent_id),
                )
                for position, attribute_id in enumerate(unique):
                    tx.execute(
                        "INSERT INTO product_variant_axes ("
                        "store_id, parent_product_id, attribute_id, position"
                        ") VALUES (%s, %s, %s, %s)",
                        (self.store_id, parent_id, attribute_id, position),
                    )
        else:
            self._axes[parent_id] = unique

    def add_media(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._get_product_record(_require_id(product_id)) is None:
            raise CatalogError("product is unknown")
        storage_id = str(payload.get("storage_id") or "")
        if not storage_id:
            raise CatalogError("storage_id is required")
        media_id = _new_id()
        now = _now()
        record = {
            "id": media_id,
            "store_id": self.store_id,
            "product_id": product_id,
            "storage_id": storage_id,
            "alt": str(payload.get("alt") or ""),
            "position": int(payload.get("position") or 0),
            "created_at": now,
            "updated_at": now,
        }
        if self._using_sql():
            with self.runtime.sql.transaction() as tx:
                tx.execute(
                    "INSERT INTO product_media ("
                    "id, store_id, product_id, storage_id, alt, position, "
                    "created_at, updated_at"
                    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        media_id,
                        self.store_id,
                        product_id,
                        storage_id,
                        record["alt"],
                        record["position"],
                        now,
                        now,
                    ),
                )
        else:
            self._media[media_id] = record
        return dict(record)

    def create_brand(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "")
        if not name:
            raise CatalogError("brand name is required")
        brand_id = payload.get("id")
        identifier = _require_id(brand_id) if brand_id else _new_id()
        slug = str(payload.get("slug") or _slug_from(name, identifier[:8]))
        if not _SLUG.fullmatch(slug):
            raise CatalogError("invalid slug")
        now = _now()
        record = {
            "id": identifier,
            "store_id": self.store_id,
            "slug": slug,
            "name": name,
            "created_at": now,
            "updated_at": now,
        }
        if self._using_sql():
            try:
                with self.runtime.sql.transaction() as tx:
                    tx.execute(
                        "INSERT INTO brands ("
                        "id, store_id, slug, name, created_at, updated_at"
                        ") VALUES (%s, %s, %s, %s, %s, %s)",
                        (identifier, self.store_id, slug, name, now, now),
                    )
            except Exception as error:
                if _sql_conflict(error):
                    raise CatalogError("brand could not be stored") from error
                raise
        else:
            self._brands[identifier] = record
        return dict(record)


class CatalogQuery:
    def __init__(self, engine: CatalogEngine) -> None:
        self._engine = engine

    def get(self, product_id) -> dict | None:
        return self._engine.query_get(product_id)

    def list(self) -> tuple[dict, ...]:
        return self._engine.query_list()

    def upsert(self, product: dict) -> dict:
        return self._engine.query_upsert(product)


class CatalogProducts:
    def __init__(self, engine: CatalogEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_products()

    def get(self, product_id: str) -> dict | None:
        return self._engine.get_product(product_id)

    def create(self, payload: dict) -> dict:
        return self._engine.create_product(payload)

    def update(self, product_id: str, payload: dict) -> dict:
        return self._engine.update_product(product_id, payload)

    def archive(self, product_id: str) -> dict:
        return self._engine.archive_product(product_id)

    def set_axes(self, parent_id: str, attribute_ids: list[str]) -> None:
        self._engine.set_variant_axes(parent_id, attribute_ids)

    def add_media(self, product_id: str, payload: dict) -> dict:
        return self._engine.add_media(product_id, payload)


class CatalogCategories:
    def __init__(self, engine: CatalogEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_categories()

    def get(self, category_id: str) -> dict | None:
        return self._engine.get_category(category_id)

    def create(self, payload: dict) -> dict:
        return self._engine.create_category(payload)

    def update(self, category_id: str, payload: dict) -> dict:
        return self._engine.update_category(category_id, payload)

    def assign(self, product_id: str, category_id: str) -> None:
        self._engine.assign_category(product_id, category_id)


class CatalogAttributes:
    def __init__(self, engine: CatalogEngine) -> None:
        self._engine = engine

    def list(self) -> tuple[dict, ...]:
        return self._engine.list_attributes()

    def create(self, payload: dict) -> dict:
        return self._engine.create_attribute(payload)

    def update(self, attribute_id: str, payload: dict) -> dict:
        return self._engine.update_attribute(attribute_id, payload)

    def options(self, attribute_id: str) -> tuple[dict, ...]:
        return self._engine.list_options(attribute_id)

    def add_option(self, attribute_id: str, payload: dict) -> dict:
        return self._engine.create_option(attribute_id, payload)

    def assign(self, product_id: str, attributes: dict) -> None:
        self._engine._assign_attribute_map(product_id, attributes)
        product = self._engine.get_product(product_id)
        if product is None:
            raise CatalogError("product is unknown")
        self._engine._emit_product(
            action="changed", product_id=product_id, sku=product["sku"]
        )
