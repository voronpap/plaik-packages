"""Regression coverage for package-owned Storefront safety invariants."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


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
