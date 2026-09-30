import json
import logging
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .disk_tiers import disk_redundancy, disk_tier

API_ROOT = "https://prices.azure.com/api/retail/prices"
HOURS_PER_MONTH = Decimal("730")
LOGGER = logging.getLogger("costguard")


def fetch_url(url):
    request = Request(url, headers={"User-Agent": "costguard/0.1 (+Terraform cost estimation)"})
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _contains_excluded(item):
    text = " ".join(str(item.get(key, "")) for key in ("meterName", "skuName", "productName")).lower()
    return any(term in text for term in ("spot", "low priority", "dedicated", "reservation"))


def select_vm_meter(items, os_name="Linux"):
    candidates = []
    nonzero = []
    for item in items:
        if (item.get("priceType") or item.get("type")) != "Consumption" or item.get("unitOfMeasure") != "1 Hour":
            continue
        if _contains_excluded(item):
            continue
        product = str(item.get("productName", "")).lower()
        is_windows = "windows" in product
        if os_name.lower() == "windows" and not is_windows:
            continue
        if os_name.lower() != "windows" and is_windows:
            continue
        try:
            price = Decimal(str(item.get("retailPrice", 0)))
        except Exception:
            continue
        if price > 0:
            nonzero.append((price, str(item.get("meterName", "")), item))
        else:
            candidates.append((price, str(item.get("meterName", "")), item))
    ranked = nonzero or candidates
    return min(ranked, key=lambda entry: (entry[0], entry[1]))[2] if ranked else None


def select_disk_meter(items, tier, redundancy, product_hint):
    excluded = ("mount", "operation", "burst", "snapshot", "reservation")
    for item in items:
        meter = str(item.get("meterName", "")).lower()
        sku_name = str(item.get("skuName", "")).lower()
        product = str(item.get("productName", "")).lower()
        unit = str(item.get("unitOfMeasure", "")).lower()
        if (item.get("priceType") or item.get("type")) != "Consumption" or unit != "1/month":
            continue
        if any(term in meter for term in excluded):
            continue
        if product_hint.lower() not in product:
            continue
        if tier.lower() not in meter and tier.lower() not in sku_name:
            continue
        if redundancy.lower() not in meter and redundancy.lower() not in sku_name:
            continue
        try:
            if Decimal(str(item.get("retailPrice", 0))) >= 0:
                return item
        except Exception:
            continue
    return None


class AzurePricingClient:
    def __init__(self, cache, currency="USD", offline=False, warnings=None, verbose=False, fetcher=None):
        self.cache = cache
        self.currency = currency.upper()
        self.offline = offline
        self.warnings = warnings if warnings is not None else cache.warnings
        self.verbose = verbose
        self.fetcher = fetcher or fetch_url
        self.resolved = {}
        self._negative = set()

    def _warn(self, message):
        self.warnings.append(message)

    def _fetch_pages(self, service_filter, region, sku_filter):
        expression = f"serviceName eq '{service_filter}' and armRegionName eq '{region}' and {sku_filter} and priceType eq 'Consumption'"
        query = urlencode({"currencyCode": f"'{self.currency}'", "$filter": expression}, quote_via=quote, safe="'()$")
        url = f"{API_ROOT}?{query}"
        items = []
        for _ in range(10):
            if self.verbose:
                LOGGER.warning("Azure pricing URL: %s", url)
            self.cache.api_lookups += 1
            for attempt in range(3):
                try:
                    payload = self.fetcher(url)
                    break
                except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                    if attempt < 2:
                        time.sleep(0.5 * (2 ** attempt))
                        continue
                    raise ConnectionError(str(exc)) from exc
            items.extend(payload.get("Items", []))
            url = payload.get("NextPageLink")
            if not url:
                return items
        return items

    def _resolve(self, key, region, lookup, sku_label):
        cache_key = (key, region, self.currency)
        if cache_key in self.resolved:
            return self.resolved[cache_key]
        cached = self.cache.get(*cache_key)
        if cached is not None:
            if self.verbose:
                LOGGER.warning("Cache hit: %s / %s / %s", key, region, self.currency)
            result = Decimal(str(cached))
            self.resolved[cache_key] = result
            return result
        if self.verbose:
            LOGGER.warning("Cache miss: %s / %s / %s", key, region, self.currency)
        if self.offline:
            self._warn(f"[WARN] Network unavailable; defaulting SKU to $0.00. SKU: '{sku_label}'")
            self.resolved[cache_key] = Decimal("0")
            return Decimal("0")
        try:
            value, meter_name = lookup()
        except ConnectionError:
            self._warn(f"[WARN] Network unavailable; defaulting SKU to $0.00. SKU: '{sku_label}'")
            self.resolved[cache_key] = Decimal("0")
            return Decimal("0")
        if value is None:
            self._negative.add(cache_key)
            self._warn(f"[WARN] SKU '{sku_label}' not found in Azure Retail API. Skipping.")
            self.resolved[cache_key] = Decimal("0")
            return Decimal("0")
        self.cache.put(*cache_key, value)
        if self.verbose:
            LOGGER.warning("Selected meter for %s: %s (%s)", sku_label, meter_name, value)
        result = Decimal(str(value))
        self.resolved[cache_key] = result
        return result

    def vm_hourly_rate(self, sku, region, os_name="Linux"):
        cache_sku = f"{sku}|windows" if os_name.lower() == "windows" else sku

        def lookup():
            items = self._fetch_pages("Virtual Machines", region, f"armSkuName eq '{sku}'")
            item = select_vm_meter(items, os_name)
            return (Decimal(str(item["retailPrice"])), item.get("meterName", "")) if item else (None, "")

        return self._resolve(cache_sku, region, lookup, sku)

    def disk_hourly_rate(self, storage_type, disk_size_gb, region):
        tier = disk_tier(storage_type, disk_size_gb)
        if tier is None:
            label = f"disk:{storage_type}:{disk_size_gb}GB"
            self._warn(f"[WARN] SKU '{label}' not found in Azure Retail API. Skipping.")
            return Decimal("0"), label
        redundancy = disk_redundancy(storage_type)
        key = f"disk:{tier}:{redundancy}"
        normalized_type = (storage_type or "").lower()
        product = "Premium SSD Managed Disks" if normalized_type.startswith("premium") else (
            "Standard SSD Managed Disks" if normalized_type.startswith("standardssd") else "Standard HDD Managed Disks"
        )

        def lookup():
            items = self._fetch_pages("Storage", region, f"skuName eq '{tier} {redundancy}' and productName eq '{product}'")
            item = select_disk_meter(items, tier, redundancy, product)
            if not item:
                return None, ""
            # Store monthly disk cost as an hourly equivalent for the shared cache schema.
            return Decimal(str(item["retailPrice"])) / HOURS_PER_MONTH, item.get("meterName", "")

        return self._resolve(key, region, lookup, key), key
