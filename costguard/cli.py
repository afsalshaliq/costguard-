import argparse
import logging
import os
import sys
from decimal import Decimal

from .cache import PricingCache
from .calculator import budget_status, calculate
from .extractor import SUPPORTED, extract_changes, read_plan
from .pricing import AzurePricingClient
from .render import format_amount, render_report


def build_parser():
    parser = argparse.ArgumentParser(prog="costguard", description="Estimate Azure cost changes in a Terraform plan.")
    parser.add_argument("--plan", metavar="PATH")
    parser.add_argument("--max-increase", type=float)
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument("--cache-path")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--group-by-tag", metavar="KEY")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--offline", action="store_true")
    return parser


def emit_report(report, resources, net, status, currency):
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ:
        print(report)
        return
    try:
        from rich.console import Console
        from rich.text import Text
    except ImportError:
        print(report)
        return
    text = Text(report)
    offset = 0
    deltas = {item.address: (item.delta, format_amount(item.delta, currency, signed=True)) for item in resources}
    for line in report.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if stripped.startswith("  Status: PASSED"):
            text.stylize("green", offset, offset + len(stripped))
        elif "Status: FAILED" in stripped or "[CIRCUIT BREAKER]" in stripped:
            text.stylize("red", offset, offset + len(stripped))
        elif "Net Monthly Impact:" in stripped:
            text.stylize("green" if net < 0 else "red" if net > 0 else "", offset, offset + len(stripped))
        else:
            for address, (delta, rendered) in deltas.items():
                if stripped.startswith(address):
                    position = stripped.rfind(rendered)
                    if position >= 0 and delta != 0:
                        text.stylize("green" if delta < 0 else "red", offset + position, offset + position + len(rendered))
                    break
        offset += len(line)
    Console(file=sys.stdout, highlight=False).print(text, end="")


def main(argv=None):
    cache = None
    try:
        args = build_parser().parse_args(argv)
        cache_path = args.cache_path or os.environ.get("COSTGUARD_CACHE", "./pricing_cache.db")
        cache = PricingCache(cache_path)
        if args.clear_cache:
            cache.clear()
            if not args.plan:
                print("Cache cleared.")
                cache.close()
                return 0
        if args.max_increase is not None and args.max_increase < 0:
            raise ValueError("--max-increase must be non-negative")
        if args.verbose:
            logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        plan = read_plan(args.plan)
        warnings = cache.warnings
        resources = extract_changes(plan, warnings)
        plan_changes = plan.get("resource_changes") or []
        nonbillable = sum(1 for item in plan_changes if isinstance(item, dict) and item.get("type") not in SUPPORTED)
        pricing = AzurePricingClient(cache, args.currency, args.offline, warnings, args.verbose)
        totals = calculate(resources, pricing)
        status, overage = budget_status(totals["net"], args.max_increase)
        mode = "json" if args.json else ("markdown" if args.markdown else "text")
        report = render_report(resources, totals, args.max_increase, status, overage, args.currency,
                               cache.cache_hits, cache.api_lookups, warnings, nonbillable, mode, args.group_by_tag)
        emit_report(report, resources, totals["net"], status, args.currency)
        for warning in warnings:
            print(warning, file=sys.stderr)
        cache.close()
        return 1 if status == "FAILED" else 0
    except SystemExit as exc:
        return int(exc.code)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
