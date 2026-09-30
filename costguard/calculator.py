from decimal import Decimal, ROUND_HALF_UP

from .models import ResourceChange

HOURS_PER_MONTH = Decimal("730")
CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate(changes, pricing):
    for change in changes:
        if change.type == "azurerm_managed_disk":
            same_configuration = (
                change.storage_type_before == change.storage_type_after
                and change.disk_gb_before == change.disk_gb_after
                and change.region_before == change.region_after
            )
            old_rate = Decimal("0")
            new_rate = Decimal("0")
            if change.storage_type_before and change.disk_gb_before is not None and change.region_before:
                old_rate, _ = pricing.disk_hourly_rate(change.storage_type_before, change.disk_gb_before, change.region_before)
            if same_configuration:
                new_rate = old_rate
            elif change.storage_type_after and change.disk_gb_after is not None and change.region_after:
                new_rate, change.meter = pricing.disk_hourly_rate(change.storage_type_after, change.disk_gb_after, change.region_after)
        else:
            same_configuration = (
                change.sku_before == change.sku_after
                and change.region_before == change.region_after
            )
            old_rate = pricing.vm_hourly_rate(change.sku_before, change.region_before, change.os) if change.sku_before and change.region_before else Decimal("0")
            new_rate = old_rate if same_configuration else (
                pricing.vm_hourly_rate(change.sku_after, change.region_after, change.os)
                if change.sku_after and change.region_after else Decimal("0")
            )
            change.meter = change.sku_after or change.sku_before or ""
        change.old_monthly = old_rate * HOURS_PER_MONTH
        change.new_monthly = new_rate * HOURS_PER_MONTH
        change.delta = money(change.new_monthly) - money(change.old_monthly)

    # Round rows first, then sum those rows so the visible report reconciles exactly.
    prior = sum((money(change.old_monthly) for change in changes), Decimal("0"))
    projected = sum((money(change.new_monthly) for change in changes), Decimal("0"))
    return {"prior_total": prior, "projected_total": projected, "net": projected - prior}


def budget_status(net, threshold):
    if threshold is None or net <= Decimal(str(threshold)):
        return "PASSED", Decimal("0")
    return "FAILED", net - Decimal(str(threshold))
