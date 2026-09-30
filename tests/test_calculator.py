from decimal import Decimal

from costguard.calculator import budget_status, calculate
from costguard.extractor import extract_changes
from costguard.render import format_amount


class Rates:
    def __init__(self, values):
        self.values = values

    def vm_hourly_rate(self, sku, region, os_name="Linux"):
        return Decimal(str(self.values.get(sku, 0)))

    def disk_hourly_rate(self, storage, size, region):
        return Decimal("0.027") / Decimal("730"), "disk:P10:LRS"


def test_create_delete_update_and_zero_metadata():
    plan = {"resource_changes": [
        {"type":"azurerm_linux_virtual_machine","address":"create","change":{"actions":["create"],"before":None,"after":{"location":"eastus","size":"new"}}},
        {"type":"azurerm_linux_virtual_machine","address":"delete","change":{"actions":["delete"],"before":{"location":"eastus","size":"old"},"after":None}},
        {"type":"azurerm_linux_virtual_machine","address":"down","change":{"actions":["update"],"before":{"location":"eastus","size":"new"},"after":{"location":"eastus","size":"old"}}},
        {"type":"azurerm_linux_virtual_machine","address":"tags","change":{"actions":["update"],"before":{"location":"eastus","size":"new","tags":{"a":"b"}},"after":{"location":"eastus","size":"new","tags":{"a":"c"}}}},
    ]}
    changes = extract_changes(plan)
    totals = calculate(changes, Rates({"new": 0.05, "old": 0.02}))
    assert changes[0].delta > 0
    assert changes[1].delta < 0
    assert changes[2].delta < 0
    assert changes[3].delta == Decimal("0")
    assert totals["net"] == Decimal("0.00")


def test_rounding_and_signed_zero():
    assert format_amount(Decimal("-0.001"), "USD", signed=True) == "$0.00"
    assert format_amount(Decimal("1.005"), "USD") == "$1.01"
    assert format_amount(Decimal("-7.59"), "USD", signed=True) == "-$7.59"


def test_budget_threshold_inclusive():
    assert budget_status(Decimal("50"), 50)[0] == "PASSED"
    assert budget_status(Decimal("50.01"), 50)[0] == "FAILED"
    assert budget_status(Decimal("-10"), 0)[0] == "PASSED"