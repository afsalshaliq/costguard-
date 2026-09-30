import json
import sys
from pathlib import Path

from .models import ResourceChange

SUPPORTED = {
    "azurerm_linux_virtual_machine",
    "azurerm_windows_virtual_machine",
    "azurerm_virtual_machine",
    "azurerm_managed_disk",
}


def normalize_region(value):
    if not isinstance(value, str) or not value.strip():
        return None
    return "".join(character.lower() for character in value if character.isalnum())


def load_plan(text):
    try:
        plan = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Terraform plan JSON: {exc.msg} at line {exc.lineno} column {exc.colno}") from exc
    if not isinstance(plan, dict):
        raise ValueError("Invalid Terraform plan JSON: top-level value must be an object")
    return plan


def extract_changes(plan, warnings=None):
    warnings = warnings if warnings is not None else []
    changes = plan.get("resource_changes")
    if changes is None:
        warnings.append("[WARN] Plan has no resource_changes; treating it as empty.")
        changes = []
    if not isinstance(changes, list):
        raise ValueError("Invalid Terraform plan: resource_changes must be a list")

    result = []
    for resource in changes:
        if not isinstance(resource, dict) or resource.get("type") not in SUPPORTED:
            continue
        change = resource.get("change") or {}
        actions = change.get("actions") or []
        if actions in (["no-op"], ["read"]):
            continue
        if actions not in (["create"], ["delete"], ["update"], ["delete", "create"], ["create", "delete"]):
            continue
        before = change.get("before") or {}
        after = change.get("after") or {}
        is_create = actions == ["create"]
        is_delete = actions == ["delete"]
        old_source = {} if is_create else before
        new_source = {} if is_delete else after

        region_before = normalize_region(old_source.get("location"))
        region_after = normalize_region(new_source.get("location"))
        if (not is_create and region_before is None) or (not is_delete and region_after is None):
            warnings.append(f"[WARN] {resource.get('address', '<unknown>')}: region is unknown; skipping.")
            continue

        resource_type = resource["type"]
        disk = resource_type == "azurerm_managed_disk"
        if disk:
            sku_before = old_source.get("storage_account_type")
            sku_after = new_source.get("storage_account_type")
            disk_gb_before = old_source.get("disk_size_gb")
            disk_gb_after = new_source.get("disk_size_gb")
            storage_before, storage_after = sku_before, sku_after
        else:
            attr = "vm_size" if resource_type == "azurerm_virtual_machine" else "size"
            sku_before, sku_after = old_source.get(attr), new_source.get(attr)
            disk_gb_before = disk_gb_after = None
            storage_before = storage_after = None

        if is_create:
            label = "CREATE"
        elif is_delete:
            label = "DELETE"
        elif "create" in actions and "delete" in actions:
            label = "REPLACE"
        else:
            label = "UPDATE"

        tags = after.get("tags") or before.get("tags") or {}
        result.append(ResourceChange(
            address=resource.get("address", "<unknown>"), type=resource_type,
            action_label=label, region_before=region_before, region_after=region_after,
            sku_before=sku_before, sku_after=sku_after,
            os="Windows" if resource_type == "azurerm_windows_virtual_machine" else "Linux",
            disk_gb_before=disk_gb_before, disk_gb_after=disk_gb_after,
            storage_type_before=storage_before, storage_type_after=storage_after,
            tags=tags if isinstance(tags, dict) else {},
        ))
    return result


def read_plan(path=None):
    if path:
        try:
            return load_plan(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Plan file not found: {path}") from exc
        except OSError as exc:
            raise ValueError(f"Could not read plan file {path}: {exc}") from exc
    if sys.stdin.isatty():
        raise ValueError("No plan supplied. Use --plan PATH or pipe Terraform plan JSON on stdin.")
    return load_plan(sys.stdin.read())
