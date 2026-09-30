"""Managed disk SKU tier mapping; this maps names, never prices."""

TIERS = {
    "premium": [(4, "P1"), (8, "P2"), (16, "P3"), (32, "P4"), (64, "P6"), (128, "P10"), (256, "P15"), (512, "P20"), (1024, "P30"), (2048, "P40"), (4096, "P50"), (8192, "P60"), (16384, "P70"), (32767, "P80")],
    "standardssd": [(4, "E1"), (8, "E2"), (16, "E3"), (32, "E4"), (64, "E6"), (128, "E10"), (256, "E15"), (512, "E20"), (1024, "E30"), (2048, "E40"), (4096, "E50"), (8192, "E60"), (16384, "E70"), (32767, "E80")],
    "standard": [(32, "S4"), (64, "S6"), (128, "S10"), (256, "S15"), (512, "S20"), (1024, "S30"), (2048, "S40"), (4096, "S50"), (8192, "S60"), (16384, "S70"), (32767, "S80")],
}


def disk_tier(storage_account_type, disk_size_gb):
    if not storage_account_type or disk_size_gb is None:
        return None
    normalized = "".join(character.lower() for character in storage_account_type if character.isalnum())
    if normalized.startswith("premium"):
        family = "premium"
    elif normalized.startswith("standardssd"):
        family = "standardssd"
    elif normalized.startswith("standard"):
        family = "standard"
    else:
        return None
    for capacity, tier in TIERS[family]:
        if int(disk_size_gb) <= capacity:
            return tier
    return None


def disk_redundancy(storage_account_type):
    return "ZRS" if "zrs" in (storage_account_type or "").lower() else "LRS"
