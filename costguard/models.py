from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ResourceChange:
    address: str
    type: str
    action_label: str
    region_before: str | None
    region_after: str | None
    sku_before: str | None
    sku_after: str | None
    os: str = "Linux"
    disk_gb_before: int | None = None
    disk_gb_after: int | None = None
    storage_type_before: str | None = None
    storage_type_after: str | None = None
    tags: dict = field(default_factory=dict)
    old_monthly: Decimal = Decimal("0")
    new_monthly: Decimal = Decimal("0")
    delta: Decimal = Decimal("0")
    meter: str = ""
