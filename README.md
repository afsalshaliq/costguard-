# CostGuard

CostGuard is a command-line Terraform plan cost guardrail for a focused set of Azure virtual machines and managed disks. It reads Terraform `show -json` output, fetches current prices from the public Azure Retail Prices API, caches successful prices in SQLite, and exits with code 1 when the net monthly increase exceeds the selected budget. Unknown prices and unavailable network access are warnings; they are treated as zero rather than stopping the plan review.

## Install

Requires Python 3.11 or newer.

```powershell
python -m pip install -e ".[terminal,test]"
```

The Rich terminal styling is optional. Core pricing, cache, parsing, and reporting use the Python standard library. If the `costguard` executable is not on `PATH`, use `python -m costguard`.

## Desktop GUI

Launch the Tkinter interface from the project folder:

```powershell
python -m costguard.gui
```

Or, after reinstalling the editable package, use `costguard-gui`. Choose a plan JSON, set optional policy and output options, then select **Run review**. The window remains responsive during pricing lookups. **Clear cache** uses the same cache location as the CLI.

## Run

Read Terraform plan JSON from a file:

```powershell
costguard --plan test-plans/plan_b_upgrade_delete.json --max-increase 25
```

Or pipe the output of Terraform:

```powershell
terraform show -json tfplan.binary | costguard --max-increase 50
```

Machine-readable output and offline operation:

```powershell
costguard --plan test-plans/plan_a_small_add.json --json
costguard --plan test-plans/plan_a_small_add.json --offline
costguard --plan test-plans/plan_a_small_add.json --currency EUR
costguard --plan test-plans/plan_a_small_add.json --markdown --group-by-tag Environment
```

Prices are cached at `./pricing_cache.db` by default. Set `COSTGUARD_CACHE` or pass `--cache-path PATH` to choose another database. `--clear-cache` deletes cached rows; when supplied with `--plan`, CostGuard clears the cache and continues with that plan. `--offline` makes cache misses warnings without network requests.

Supported cost models are Linux and Windows Azure VM hourly consumption meters, plus managed disk capacity tiers. VM updates compare before and after hourly rates; disk monthly prices are normalized to hourly equivalents in the cache. The calculator uses 730 hours per month and sums cent-rounded rows so printed totals reconcile. All other resource types are counted as non-billable and skipped.

## Tests

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
```

The normal test run uses mocked Azure responses and makes no network requests. To run the optional live Standard_B2s check:

```powershell
$env:COSTGUARD_RUN_NETWORK = "1"
python -m pytest -q -m network
Remove-Item Env:COSTGUARD_RUN_NETWORK
```
