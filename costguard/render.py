import json
from decimal import Decimal

from .calculator import money
from .disk_tiers import disk_tier

SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
RULE = "=" * 99
SEPARATOR = "-" * 99


def currency_symbol(currency):
    return SYMBOLS.get(currency.upper(), f"{currency.upper()} ")


def format_amount(value, currency="USD", signed=False):
    rounded = money(Decimal(str(value)))
    symbol = currency_symbol(currency)
    if rounded == 0:
        return f"{symbol}0.00"
    if signed:
        sign = "+" if rounded > 0 else "-"
        return f"{sign}{symbol}{abs(rounded):.2f}"
    return f"-{symbol}{abs(rounded):.2f}" if rounded < 0 else f"{symbol}{rounded:.2f}"


def sku_label(change):
    if change.type == "azurerm_managed_disk":
        sku = change.storage_type_after or change.storage_type_before or "Disk"
        size = change.disk_gb_after or change.disk_gb_before or "?"
        tier = disk_tier(sku, size) or "Unknown"
        media = "Premium SSD" if sku.lower().startswith("premium") else ("Standard SSD" if sku.lower().startswith("standardssd") else "Standard HDD")
        return f"{tier} {media} ({size}GB)"
    before, after = change.sku_before, change.sku_after
    if before and after and before != after:
        return f"{before} -> {after.removeprefix('Standard_')}"
    return after or before or "Unknown"


def _row(change, currency):
    region = change.region_after or change.region_before or "unknown"
    return [change.address, change.action_label, region, sku_label(change),
            format_amount(change.old_monthly, currency), format_amount(change.new_monthly, currency),
            format_amount(change.delta, currency, signed=True)]


def render_text(resources, totals, threshold, status, overage, currency, cache_hits, api_lookups, nonbillable, group_by_tag=None):
    title = "COSTGUARD: Azure Infrastructure Cost Impact Report"
    headers = ["Resource Address", "Action", "Region", "SKU / Meter", "Old ($/mo)", "New ($/mo)", "Delta ($/mo)"]
    rows = [_row(resource, currency) for resource in resources]
    widths = [42, 8, 12, 32, 13, 13, 14]
    line = "  ".join(header.ljust(width) for header, width in zip(headers, widths))
    output = [RULE, title, RULE, line, SEPARATOR]
    if group_by_tag and resources:
        grouped = {}
        for resource, row in zip(resources, rows):
            grouped.setdefault(str(resource.tags.get(group_by_tag, "(untagged)")), []).append((resource, row))
        for tag, entries in sorted(grouped.items()):
            output.append(f"[{group_by_tag}: {tag}]")
            output.extend("  ".join(value.ljust(width) for value, width in zip(row, widths)) for _, row in entries)
            prior = sum((money(item.old_monthly) for item, _ in entries), Decimal("0"))
            projected = sum((money(item.new_monthly) for item, _ in entries), Decimal("0"))
            output.append(f"  Subtotal: {format_amount(projected - prior, currency, True)}")
    elif resources:
        output.extend("  ".join(value.ljust(width) for value, width in zip(row, widths)) for row in rows)
    else:
        output.append(f"{nonbillable} non-billable resources skipped; no billable changes")
    output.extend([SEPARATOR, "FINANCIAL SUMMARY:", f"  Prior Monthly Total:     {format_amount(totals['prior_total'], currency)}/mo",
                   f"  Projected Monthly Total: {format_amount(totals['projected_total'], currency)}/mo",
                   f"  Net Monthly Impact:      {format_amount(totals['net'], currency, True)}/mo   [Cache: {cache_hits} hits, {api_lookups} API lookups]",
                   f"  {nonbillable} non-billable resources skipped", SEPARATOR, "POLICY VERDICT:"])
    budget = "none" if threshold is None else f"{format_amount(Decimal(str(threshold)), currency, True)}/mo"
    output.append(f"  Budget Threshold: {budget}")
    if status == "FAILED":
        output.append(f"  Status: FAILED (Exceeds budget allowance by {format_amount(overage, currency, True)}/mo)")
    else:
        output.append("  Status: PASSED (Within budget allowance)")
    output.append(RULE)
    if status == "FAILED":
        output.append("[CIRCUIT BREAKER] CostGuard: Budget threshold breached. Deployment blocked.")
    return "\n".join(output)


def render_markdown(resources, totals, threshold, status, overage, currency, cache_hits, api_lookups, nonbillable, group_by_tag=None):
    headers = ["Resource Address", "Action", "Region", "SKU / Meter", "Old ($/mo)", "New ($/mo)", "Delta ($/mo)"]
    rows = [_row(resource, currency) for resource in resources]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    if group_by_tag and resources:
        grouped = {}
        for resource, row in zip(resources, rows):
            grouped.setdefault(str(resource.tags.get(group_by_tag, "(untagged)")), []).append((resource, row))
        for tag, entries in sorted(grouped.items()):
            lines.append(f"| **{group_by_tag}: {tag}** |  |  |  |  |  |  |")
            lines.extend("| " + " | ".join(row) + " |" for _, row in entries)
            prior = sum((money(item.old_monthly) for item, _ in entries), Decimal("0"))
            projected = sum((money(item.new_monthly) for item, _ in entries), Decimal("0"))
            lines.append(f"| **Subtotal** |  |  |  |  |  | {format_amount(projected - prior, currency, True)} |")
    else:
        lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.extend(["", f"{nonbillable} non-billable resources skipped", "",
                  f"Prior: {format_amount(totals['prior_total'], currency)}/mo  ",
                  f"Projected: {format_amount(totals['projected_total'], currency)}/mo  ",
                  f"Net: {format_amount(totals['net'], currency, True)}/mo  ",
                  f"Cache: {cache_hits} hits, {api_lookups} API lookups  "])
    lines.append("Budget threshold: none" if threshold is None else f"Budget threshold: {format_amount(Decimal(str(threshold)), currency, True)}/mo")
    lines.append("✅ PASSED" if status == "PASSED" else f"❌ FAILED (over by {format_amount(overage, currency, True)}/mo)")
    return "\n".join(lines)


def render_json(resources, totals, threshold, status, cache_hits, api_lookups, warnings, currency, group_by_tag=None):
    body = {
        "resources": [{"address": item.address, "type": item.type, "action": item.action_label,
                      "region": item.region_after or item.region_before, "sku": sku_label(item),
                      "old_monthly": float(money(item.old_monthly)), "new_monthly": float(money(item.new_monthly)),
                      "delta": float(money(item.delta)), "tags": item.tags} for item in resources],
        "prior_total": float(totals["prior_total"]), "projected_total": float(totals["projected_total"]),
        "net": float(totals["net"]), "threshold": threshold, "status": status,
        "cache": {"hits": cache_hits, "api_lookups": api_lookups}, "warnings": warnings, "currency": currency,
    }
    if group_by_tag:
        groups = {}
        for item in resources:
            tag = str(item.tags.get(group_by_tag, "(untagged)"))
            values = groups.setdefault(tag, {"prior_total": Decimal("0"), "projected_total": Decimal("0")})
            values["prior_total"] += money(item.old_monthly)
            values["projected_total"] += money(item.new_monthly)
        body["groups"] = {tag: {"prior_total": float(value["prior_total"]),
                                "projected_total": float(value["projected_total"]),
                                "net": float(value["projected_total"] - value["prior_total"])}
                          for tag, value in groups.items()}
    return json.dumps(body, indent=2, ensure_ascii=False)


def render_report(resources, totals, threshold, status, overage, currency, cache_hits, api_lookups, warnings, nonbillable, mode="text", group_by_tag=None):
    if mode == "json":
        return render_json(resources, totals, threshold, status, cache_hits, api_lookups, warnings, currency, group_by_tag)
    if mode == "markdown":
        return render_markdown(resources, totals, threshold, status, overage, currency, cache_hits, api_lookups, nonbillable, group_by_tag)
    return render_text(resources, totals, threshold, status, overage, currency, cache_hits, api_lookups, nonbillable, group_by_tag)
