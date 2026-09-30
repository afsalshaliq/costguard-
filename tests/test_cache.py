import sqlite3

from costguard.cache import PricingCache
from costguard.pricing import AzurePricingClient


def test_cache_hit_avoids_http(tmp_path, vm_items):
    path = tmp_path / "pricing.db"
    cache = PricingCache(path)
    cache.put("Standard_B2s", "eastus", "USD", 0.0416)
    calls = []
    client = AzurePricingClient(cache, fetcher=lambda url: calls.append(url))
    assert str(client.vm_hourly_rate("Standard_B2s", "eastus")) == "0.0416"
    assert cache.cache_hits == 1
    assert not calls
    cache.close()


def test_currency_keys_and_clear(tmp_path):
    cache = PricingCache(tmp_path / "pricing.db")
    cache.put("sku", "eastus", "USD", 1)
    cache.put("sku", "eastus", "EUR", 2)
    assert cache.get("sku", "eastus", "USD") == 1
    assert cache.get("sku", "eastus", "EUR") == 2
    cache.clear()
    assert cache.get("sku", "eastus", "USD") is None
    cache.close()


def test_corrupt_database_recreated(tmp_path):
    path = tmp_path / "bad.db"
    path.write_bytes(b"not a sqlite database")
    warnings = []
    cache = PricingCache(path, warnings=warnings)
    assert cache.connection.execute("SELECT name FROM sqlite_master WHERE name='pricing_cache'").fetchone()
    assert warnings
    cache.close()


def test_schema_and_parameterized_roundtrip(tmp_path):
    cache = PricingCache(tmp_path / "pricing.db")
    cache.put("sku' OR 1=1", "eastus", "USD", 0.5)
    assert cache.get("sku' OR 1=1", "eastus", "USD") == 0.5
    columns = [row[1] for row in cache.connection.execute("PRAGMA table_info(pricing_cache)")]
    assert columns == ["sku", "region", "currency", "hourly_rate", "cached_at"]
    cache.close()


def test_api_miss_writes_through_and_next_client_hits(tmp_path, vm_items):
    cache = PricingCache(tmp_path / "pricing.db")
    first = AzurePricingClient(cache, fetcher=lambda url: {"Items": vm_items, "NextPageLink": None})
    assert str(first.vm_hourly_rate("Standard_B2s", "eastus")) == "0.0416"
    calls = []
    second = AzurePricingClient(cache, fetcher=lambda url: calls.append(url))
    assert str(second.vm_hourly_rate("Standard_B2s", "eastus")) == "0.0416"
    assert cache.cache_hits == 1
    assert not calls
    cache.close()