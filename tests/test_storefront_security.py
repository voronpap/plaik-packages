"""Regression coverage for package-owned Storefront safety invariants."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from contextlib import contextmanager


ROOT = Path(__file__).parents[1] / "modules"


def load(package: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / package / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cart_quantity_has_a_hard_business_bound() -> None:
    cart = load("cart", "cart_engine")
    assert cart._require_quantity(100) == 100
    with pytest.raises(cart.CartError):
        cart._require_quantity(101)
    with pytest.raises(cart.CartError):
        cart.CartEngine._write_line(object(), "cart", "product", 101, action="added")


def test_storefront_catalog_never_exposes_unpublished_products() -> None:
    catalog = load("catalog", "catalog_engine")

    class Runtime:
        store_id = "test-store"
        class settings:
            @staticmethod
            def get(_key, default=None):
                return default

    engine = catalog.CatalogEngine(Runtime())
    engine._mode = "memory"
    engine._products = {
        "published-product": {"id": "published-product", "sku": "PUB", "title": "Published", "status": "published"},
        "draft-product": {"id": "draft-product", "sku": "DRF", "title": "Draft", "status": "draft"},
    }
    storefront = catalog.CatalogStorefront(engine)
    assert storefront.get("draft-product") is None
    assert [item["id"] for item in storefront.list()] == ["published-product"]


def test_all_public_response_schemas_are_closed() -> None:
    def assert_closed(schema: dict) -> None:
        if schema.get("type") == "object":
            assert schema.get("additional_properties") is False
            for nested in schema.get("properties", {}).values():
                assert_closed(nested)
        if schema.get("type") == "array":
            assert_closed(schema["items"])

    for manifest_path in ROOT.glob("*/manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for family in ("queries", "actions", "page_projections", "sitemap_projections"):
            for declaration in manifest.get("public", {}).get(family, []):
                assert_closed(declaration["response_schema"])


def test_checkout_rejects_cross_subject_replay_and_unresolved_new_key() -> None:
    checkout = load("checkout", "checkout_engine")

    class Runtime:
        store_id = "test-store"

    engine = checkout.CheckoutEngine(Runtime())
    engine._mode = "memory"
    engine._placements["shared-key"] = {
        "store_id": "test-store",
        "idempotency_key": "shared-key",
        "cart_id": "cart-alice",
        "order_id": "order-alice",
        "payment_id": "payment-alice",
        "subject": "subject-alice-0001",
        "fingerprint": "a" * 64,
        "state": "completed",
        "created_at": "2026-08-23T00:00:00+00:00",
    }
    with pytest.raises(checkout.CheckoutError, match="idempotency conflict"):
        engine.place(
            {
                "cart_id": "cart-bob",
                "shipping_method_id": "manual-shipping",
                "idempotency_key": "shared-key",
                "_public_subject": "subject-bob-0000001",
                "_public_fingerprint": "b" * 64,
            }
        )

    engine._placements["uncertain-key"] = {
        "store_id": "test-store",
        "idempotency_key": "uncertain-key",
        "cart_id": "cart-uncertain",
        "order_id": "order-alice",
        "payment_id": "",
        "subject": "subject-alice-0001",
        "fingerprint": "c" * 64,
        "state": "needs_reconciliation",
        "created_at": "2026-08-23T00:00:00+00:00",
    }
    with pytest.raises(checkout.CheckoutError, match="requires reconciliation"):
        engine._claim("new-key", "cart-uncertain", "subject-alice-0001", "d" * 64)


def test_catalog_category_membership_is_published_only() -> None:
    catalog = load("catalog", "catalog_engine")

    class Runtime:
        store_id = "test-store"
        class settings:
            @staticmethod
            def get(_key, default=None):
                return default

    engine = catalog.CatalogEngine(Runtime())
    engine._mode = "memory"
    engine._categories = {
        "brakes": {"id": "brakes", "slug": "brakes", "name": "Brakes", "parent_id": None}
    }
    engine._products = {
        "live": {"id": "live", "sku": "LIVE", "title": "Live", "status": "published"},
        "draft": {"id": "draft", "sku": "DRAFT", "title": "Draft", "status": "draft"},
        "other": {"id": "other", "sku": "OTHER", "title": "Other", "status": "published"},
    }
    engine._product_categories = {"live": {"brakes"}, "draft": {"brakes"}}
    storefront = catalog.CatalogStorefront(engine)
    assert [row["id"] for row in storefront.products("brakes")] == ["live"]
    assert storefront.category("brakes")["id"] == "brakes"


def test_catalog_category_sql_qualifies_joined_product_columns() -> None:
    catalog = load("catalog", "catalog_engine")
    statements: list[str] = []

    class Transaction:
        def fetchall(self, sql, _params):
            statements.append(sql)
            return []

    class SQL:
        @contextmanager
        def transaction(self):
            yield Transaction()

    class Runtime:
        store_id = "test-store"
        sql = SQL()

    engine = catalog.CatalogEngine(Runtime())
    engine._mode = "sql"
    assert catalog.CatalogStorefront(engine).products("brakes") == ()
    assert statements and "SELECT p.id, p.store_id, p.sku" in statements[0]
    assert "JOIN product_categories" in statements[0]
    assert statements[0].endswith("LIMIT %s")


def test_catalog_storefront_memory_bounds_are_deterministic() -> None:
    catalog = load("catalog", "catalog_engine")

    class Runtime:
        store_id = "test-store"

    engine = catalog.CatalogEngine(Runtime())
    engine._mode = "memory"
    for index in reversed(range(140)):
        product_id = f"p-{index:03d}"
        engine._products[product_id] = {
            "id": product_id,
            "sku": product_id,
            "slug": f"slug-{index % 3:03d}",
            "title": product_id,
            "status": "published",
        }
        engine._product_categories[product_id] = {"brakes"}
    storefront = catalog.CatalogStorefront(engine)
    expected = sorted(
        engine._products,
        key=lambda product_id: (engine._products[product_id]["slug"], product_id),
    )[:128]
    assert [item["id"] for item in storefront.list()] == expected
    assert [item["id"] for item in storefront.products("brakes")] == expected


def test_auto_parts_browser_client_uses_fixed_safe_public_boundary() -> None:
    client = (ROOT.parent / "themes" / "auto-parts" / "assets" / "js" / "storefront.js").read_text(encoding="utf-8")
    assert 'fetch("/api/storefront/session"' in client
    assert '"X-PLAIK-CSRF-Token": token' in client
    assert '"Idempotency-Key": key' in client
    assert "element.dataset.plaikIdempotencyKey || idempotencyKey()" in client
    assert "delete element.dataset.plaikIdempotencyKey" in client
    assert '"/api/storefront/" + packageId + "/actions/" + actionId' in client
    assert "innerHTML" not in client
    assert "eval(" not in client
    assert "Math.random" not in client


def test_auto_parts_layouts_load_the_declared_browser_client() -> None:
    theme = ROOT.parent / "themes" / "auto-parts"
    manifest = json.loads((theme / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"]["js"] == ["assets/js/storefront.js"]
    for layout in (theme / "templates" / "layouts").glob("*.html"):
        assert '{{ theme_assets("js") }}' in layout.read_text(encoding="utf-8")


def test_checkout_cart_claim_fences_concurrent_different_keys() -> None:
    checkout = load("checkout", "checkout_engine")

    class Runtime:
        store_id = "test-store"

    engine = checkout.CheckoutEngine(Runtime())
    engine._mode = "memory"

    def claim(key: str) -> str:
        try:
            engine._claim(key, "cart-one", "subject-one-0001", key[0] * 64)
            return "claimed"
        except checkout.CheckoutError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(claim, ("a-key", "b-key")))
    assert sorted(outcomes) == ["blocked", "claimed"]
    assert len(engine._placements) == 1

    first_key = next(iter(engine._placements))
    engine._placements[first_key]["state"] = "completed"
    assert engine._claim("next-purchase", "cart-one", "subject-one-0001", "c" * 64) is None


def test_checkout_releases_claim_after_safe_pre_effect_failure() -> None:
    checkout = load("checkout", "checkout_engine")

    class Runtime:
        store_id = "test-store"

    engine = checkout.CheckoutEngine(Runtime())
    engine._mode = "memory"
    engine._quote_cart = lambda _cart_id: (_ for _ in ()).throw(checkout.CheckoutError("cart is empty"))
    payload = {
        "cart_id": "cart-safe",
        "shipping_method_id": "manual",
        "idempotency_key": "safe-key",
        "_public_subject": "subject-safe-0001",
        "_public_fingerprint": "e" * 64,
    }
    with pytest.raises(checkout.CheckoutError, match="cart is empty"):
        engine.place(payload)
    assert engine._placements == {}
    assert engine._claim("corrected-key", "cart-safe", "subject-safe-0001", "f" * 64) is None


def test_auto_parts_composes_every_projected_listing_route() -> None:
    manifest = json.loads((ROOT / "catalog" / "manifest.json").read_text(encoding="utf-8"))
    slots = {entry["slot"] for entry in manifest["web"]["slots"]}
    assert {"storefront.collection.products", "storefront.home.featured", "storefront.search.results"} <= slots
    theme = ROOT.parent / "themes" / "auto-parts"
    assert "catalog" in json.loads((theme / "manifest.json").read_text(encoding="utf-8"))["page_templates"]
    assert (theme / "templates" / "pages" / "catalog.json").is_file()
