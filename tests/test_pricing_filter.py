from costguard.cache import PricingCache
from costguard.pricing import AzurePricingClient, select_disk_meter, select_vm_meter
from urllib.error import URLError


def test_vm_decoys_excluded(vm_items):
    chosen = select_vm_meter(vm_items, "Linux")
    assert chosen["retailPrice"] == 0.0416
    assert select_vm_meter(vm_items, "Windows")["retailPrice"] == 0.0496


    def test_real_azure_type_field_is_supported():
        item = {"type": "Consumption", "unitOfMeasure": "1 Hour", "productName": "Virtual Machines",
            "meterName": "B2s", "retailPrice": 0.0416}
        assert select_vm_meter([item]) == item


def test_pagination_and_cache_miss(tmp_path, vm_items):
    cache = PricingCache(tmp_path / "prices.db")
    first = "https://prices.azure.com/page1"
    seen = []

    def fetch(url):
        seen.append(url)
        if len(seen) == 1:
            return {"Items": vm_items[:-1], "NextPageLink": first + "?next=2"}
        return {"Items": vm_items[-1:], "NextPageLink": None}

    client = AzurePricingClient(cache, fetcher=fetch)
    assert str(client.vm_hourly_rate("Standard_B2s", "eastus")) == "0.0416"
    assert len(seen) == 2
    assert cache.api_lookups == 2
    cache.close()


def test_not_found_warns_and_is_not_cached(tmp_path):
    cache = PricingCache(tmp_path / "prices.db")
    warnings = []
    client = AzurePricingClient(cache, warnings=warnings, fetcher=lambda url: {"Items": [], "NextPageLink": None})
    assert client.vm_hourly_rate("Custom_Unknown_SKU", "eastus") == 0
    assert "[WARN] SKU 'Custom_Unknown_SKU' not found in Azure Retail API. Skipping." in warnings
    assert cache.get("Custom_Unknown_SKU", "eastus", "USD") is None
    cache.close()


def test_disk_filter_matches_managed_disk_product(disk_items):
    selected = select_disk_meter(disk_items, "P10", "LRS", "Premium SSD Managed Disks")
    assert selected["retailPrice"] == 19.71


def test_offline_miss_warns_without_network(tmp_path):
    cache = PricingCache(tmp_path / "prices.db")
    warnings = []
    client = AzurePricingClient(cache, offline=True, warnings=warnings, fetcher=lambda url: (_ for _ in ()).throw(AssertionError("network called")))
    assert client.vm_hourly_rate("SKU", "eastus") == 0
    assert "[WARN] Network unavailable; defaulting SKU to $0.00." in warnings[0]
    assert cache.api_lookups == 0
    cache.close()


def test_network_retries_then_warns_without_caching(tmp_path, monkeypatch):
    cache = PricingCache(tmp_path / "prices.db")
    warnings = []
    calls = []

    def fail(url):
        calls.append(url)
        raise URLError("unavailable")

    monkeypatch.setattr("costguard.pricing.time.sleep", lambda delay: None)
    client = AzurePricingClient(cache, warnings=warnings, fetcher=fail)
    assert client.vm_hourly_rate("OfflineSKU", "eastus") == 0
    assert len(calls) == 3
    assert cache.api_lookups == 1
    assert "[WARN] Network unavailable; defaulting SKU to $0.00." in warnings[0]
    assert cache.get("OfflineSKU", "eastus", "USD") is None
    cache.close()