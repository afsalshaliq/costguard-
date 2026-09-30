import json

import pytest

from costguard.extractor import extract_changes, load_plan, normalize_region


def resource(resource_type="azurerm_linux_virtual_machine", actions=None, before=None, after=None):
    return {"address": "example.vm", "type": resource_type,
            "change": {"actions": actions or ["create"], "before": before, "after": after}}


def test_action_matrix_and_regions():
    plan = {"resource_changes": [
        resource(actions=["create"], after={"location": "East US", "size": "Standard_B1s"}),
        resource(actions=["delete"], before={"location": "West Europe", "size": "Standard_B2s"}),
        resource(actions=["update"], before={"location": "eastus", "size": "Standard_B1s"}, after={"location": "East US", "size": "Standard_B2s"}),
        resource(actions=["delete", "create"], before={"location": "eastus", "size": "Standard_B1s"}, after={"location": "West Europe", "size": "Standard_B2s"}),
        resource(actions=["create", "delete"], before={"location": "eastus", "size": "Standard_B1s"}, after={"location": "West Europe", "size": "Standard_B2s"}),
    ]}
    changes = extract_changes(plan)
    assert [item.action_label for item in changes] == ["CREATE", "DELETE", "UPDATE", "REPLACE", "REPLACE"]
    assert changes[0].region_after == "eastus"
    assert changes[1].region_before == "westeurope"


def test_noop_legacy_disk_and_nonbillable():
    plan = {"resource_changes": [
        resource(actions=["no-op"], after={"location": "eastus", "size": "x"}),
        resource("azurerm_virtual_machine", ["create"], after={"location": "eastus", "vm_size": "Legacy"}),
        resource("azurerm_managed_disk", ["create"], after={"location": "eastus", "storage_account_type": "Premium_LRS", "disk_size_gb": 128}),
        resource("azurerm_resource_group", ["create"], after={"location": "eastus"}),
    ]}
    changes = extract_changes(plan)
    assert len(changes) == 2
    assert changes[0].sku_after == "Legacy"
    assert changes[1].disk_gb_after == 128


def test_unknown_location_warns_and_skips():
    warnings = []
    assert not extract_changes({"resource_changes": [resource(after={"location": None, "size": "x"})]}, warnings)
    assert "region is unknown" in warnings[0]


def test_missing_resource_changes_warns():
    warnings = []
    assert extract_changes({}, warnings) == []
    assert warnings


def test_invalid_json_and_non_object():
    with pytest.raises(ValueError, match="Invalid Terraform plan JSON"):
        load_plan("{")
    with pytest.raises(ValueError, match="top-level"):
        load_plan(json.dumps([]))


def test_region_normalization():
    assert normalize_region("East US") == "eastus"
    assert normalize_region("West_Europe") == "westeurope"