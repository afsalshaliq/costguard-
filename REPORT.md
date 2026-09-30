# CostGuard Implementation Report

## What We Built

CostGuard is a standalone Python CLI that reads Terraform plan JSON and estimates monthly Azure VM and managed-disk cost changes. It retrieves consumption prices from the public Azure Retail Prices API and stores successful hourly-equivalent rates in a SQLite cache. It applies a budget threshold to the net monthly change and returns a blocking exit code when the threshold is exceeded. It supports text, Markdown, and JSON output, tag grouping, currency selection, cache clearing, and offline cache-only operation. It does not estimate resource types outside the implemented VM and managed-disk set, and missing prices are reported as warnings with a zero estimate.

## Detection & Extraction Logic

`resource_changes` is authoritative; `planned_values` and `prior_state` are ignored. Create, delete, update, and replacement actions select the appropriate before/after resource attributes, while no-op/read actions are ignored. Region names are normalized to lowercase alphanumeric values. Unknown locations warn and skip; unsupported resource types are counted in the report without per-resource warnings. Tags come from `after.tags`, falling back to `before.tags`.

Linux VMs use `size`, Windows VMs use the same SKU with a distinct Windows cache key, and legacy `azurerm_virtual_machine` uses `vm_size`. Managed disks use `storage_account_type` plus `disk_size_gb` to find a tier name; the tier map is only a SKU-name lookup and contains no prices. Unchanged billing attributes are looked up once and produce an exact zero delta. Rows are rounded to cents before totals are summed.

## Methods

| Area | Implementation |
|---|---|
| Live API vs static pricing | Live Azure Retail Prices API queries; no production price constants. Development curl returned Standard_B2s East US at `$0.0416/hour` and P10 LRS at `$19.71/month`. |
| Cache | SQLite `pricing_cache(sku, region, currency, hourly_rate, cached_at)` with the specified composite primary key. Successful lookups write through; cache hits bypass HTTP. VM keys are ARM SKU names, Windows keys append `|windows`, and disk keys use `disk:<tier>:<redundancy>`. Currency is part of every key. |
| Disk normalization | Monthly disk retail prices are divided by 730 before storage, so downstream monthly cost remains `hourly_rate * 730`. |
| Meter filtering | Consumption only; VM meters must be `1 Hour`. Spot, Low Priority, Windows-on-Linux, Dedicated, and Reservation candidates are excluded as appropriate. The real API uses response field `type` for Consumption; the client also accepts `priceType`. Disk meters require the requested managed-disk product family, tier, redundancy, and `1/Month`, and exclude mount/operation/burst/snapshot/reservation meters. |
| Fallbacks | Unknown SKUs and network failures warn and estimate `$0.00`; failures are not persisted. Same-run values are deduplicated. |

## Results Matrix

Live runs used a fresh `report-run.db`, except the warm-run check. Amounts and counters below are copied from observed CostGuard output.

| Command | Net monthly delta | Exit | Cache hits / API lookups |
|---|---:|---:|---:|
| `python -m costguard --plan test-plans/plan_a_small_add.json --max-increase 50 --cache-path report-run.db` | `+$27.30` | 0 | 0 / 2 |
| `python -m costguard --plan test-plans/plan_i_vm_delete.json --cache-path report-run.db` | `-$30.37` | 0 | 1 / 0 |
| `python -m costguard --plan test-plans/plan_j_vm_upgrade.json --cache-path report-run.db` | `+$22.78` | 0 | 2 / 0 |
| `python -m costguard --plan test-plans/plan_c_hostile_noise.json --cache-path report-run.db` | `$0.00` | 0 | 0 / 0 |
| `python -m costguard --plan test-plans/plan_b_upgrade_delete.json --max-increase 25 --cache-path report-run.db` | `+$32.12` | 1 | 1 / 2 |

The cold Plan A stdin run reported 0 cache hits and 2 API lookups; an immediate repeat reported 2 hits and 0 lookups. The repeated full process took 398.4 ms in this Windows environment, including Python startup; pricing made no network requests on the repeat. Plan E (tags-only) reported `$0.00`; Plan G emitted the expected unknown-SKU warning and exited 0; Plan F exited 2 with a clean invalid-JSON message. All 10 fixture plans were run: A 0, B 1 at the `$25` threshold, C 0, D 0, E 0, F 2, G 0, H 0, I 0, J 0.

Plan B exceeded the threshold by `$7.12` and printed the circuit-breaker line. The real B2s API rate of `$0.0416/hour` corresponds to `$30.37/month`; the live delete fixture showed that monthly amount as its prior cost. The live P10 meter was `$19.71/month`.

## Limitations & Next Steps

- Disk IOPS, bursting, snapshots, and other performance features are not modeled.
- Bandwidth/egress, load balancers, public IPs, App Service, SQL, and non-Azure clouds are outside the supported billable set.
- Reserved instances, savings plans, tiered pricing, and negotiated discounts are not modeled.
- Terraform values unknown until apply, including unknown regions, are warned and skipped.
- A missing or unavailable price is treated as zero for reporting; users should review warnings before relying on a budget decision.
- Prices are public retail rates and may vary by offer, agreement, effective date, or Azure meter taxonomy.

## How to Run It

Install the CLI and test dependencies:

```powershell
python -m pip install -e ".[terminal,test]"
```

Run each fixture:

```powershell
python -m costguard --plan test-plans/plan_a_small_add.json --max-increase 50
python -m costguard --plan test-plans/plan_b_upgrade_delete.json --max-increase 25
python -m costguard --plan test-plans/plan_c_hostile_noise.json
python -m costguard --plan test-plans/plan_d_replace.json
python -m costguard --plan test-plans/plan_e_tags_only.json
python -m costguard --plan test-plans/plan_f_corrupt.json
python -m costguard --plan test-plans/plan_g_unknown_sku.json
python -m costguard --plan test-plans/plan_h_windows_vm.json
python -m costguard --plan test-plans/plan_i_vm_delete.json
python -m costguard --plan test-plans/plan_j_vm_upgrade.json
```

Run twice with a dedicated cache to see the warm-cache counters:

```powershell
Get-Content -Raw test-plans/plan_a_small_add.json | python -m costguard --max-increase 50 --cache-path .\pricing_cache.db
Get-Content -Raw test-plans/plan_a_small_add.json | python -m costguard --max-increase 50 --cache-path .\pricing_cache.db
```

Run the default unit/CLI suite with `python -m pytest -q`. The optional live test is marked `network` and can be run using the environment-variable instructions in `README.md`.
