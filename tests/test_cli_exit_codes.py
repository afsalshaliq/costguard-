import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from decimal import Decimal

import pytest

from costguard.cli import main

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, input_text=None):
    return subprocess.run([sys.executable, "-m", "costguard", *map(str, args)], cwd=ROOT,
                          input=input_text, text=True, capture_output=True)


def test_plan_and_stdin_modes(tmp_path):
    plan = ROOT / "test-plans" / "plan_c_hostile_noise.json"
    first = run_cli("--plan", plan, "--offline", "--cache-path", tmp_path / "cache.db")
    second = run_cli("--offline", "--cache-path", tmp_path / "cache.db", input_text=plan.read_text())
    assert first.returncode == second.returncode == 0
    assert "15 non-billable resources skipped" in first.stdout
    assert "$0.00/mo" in second.stdout


def test_budget_and_render_modes(tmp_path, monkeypatch, capsys):
    plan = ROOT / "test-plans" / "plan_a_small_add.json"
    class KnownRates:
        def __init__(self, *args, **kwargs):
            pass

        def vm_hourly_rate(self, sku, region, os_name="Linux"):
            return Decimal("0.10")

        def disk_hourly_rate(self, storage, size, region):
            return Decimal("0.10"), "disk:P10:LRS"

    import costguard.cli as cli
    monkeypatch.setattr(cli, "AzurePricingClient", KnownRates)
    code = main(["--plan", str(plan), "--cache-path", str(tmp_path / "breach.db"), "--max-increase", "1"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Status: FAILED" in captured.out
    assert "[CIRCUIT BREAKER]" in captured.out

    markdown = run_cli("--plan", plan, "--offline", "--cache-path", tmp_path / "db", "--markdown", "--group-by-tag", "Environment")
    assert "| Resource Address |" in markdown.stdout
    machine = run_cli("--plan", plan, "--offline", "--cache-path", tmp_path / "db", "--json")
    assert json.loads(machine.stdout)["status"] == "PASSED"


def test_bad_json_and_missing_file_exit_two(tmp_path):
    corrupt = run_cli("--plan", ROOT / "test-plans" / "plan_f_corrupt.json", "--cache-path", tmp_path / "db")
    missing = run_cli("--plan", tmp_path / "missing.json", "--cache-path", tmp_path / "db")
    empty = run_cli("--cache-path", tmp_path / "db", input_text="")
    assert corrupt.returncode == missing.returncode == empty.returncode == 2
    assert "Traceback" not in corrupt.stderr + missing.stderr + empty.stderr


def test_unknown_sku_and_cache_clear(tmp_path):
    path = tmp_path / "cache.db"
    unknown = run_cli("--plan", ROOT / "test-plans" / "plan_g_unknown_sku.json", "--offline", "--cache-path", path)
    assert unknown.returncode == 0
    assert "Network unavailable" in unknown.stderr
    cleared = run_cli("--clear-cache", "--cache-path", path)
    assert cleared.returncode == 0


def test_missing_input_tty(monkeypatch, capsys, tmp_path):
    class TTY:
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", TTY())
    assert main(["--cache-path", str(tmp_path / "cache.db")]) == 2
    assert "No plan supplied" in capsys.readouterr().err


@pytest.mark.network
def test_network_integration():
    from costguard.cache import PricingCache
    from costguard.pricing import AzurePricingClient
    if os.environ.get("COSTGUARD_RUN_NETWORK") != "1":
        pytest.skip("Set COSTGUARD_RUN_NETWORK=1 to run the live Azure API check")
    with tempfile.TemporaryDirectory() as directory:
        cache = PricingCache(Path(directory) / "cache.db")
        rate = AzurePricingClient(cache).vm_hourly_rate("Standard_B2s", "eastus")
        cache.close()
    assert 0.01 <= float(rate) <= 0.10
