#!/usr/bin/env python3
"""
Coco Router Key Farm — Orchestrator
One-click command to run farmers (in sequence — they share one browser fingerprint)
and inject harvested keys into OmniRoute.

Usage:
    # Farm all easy providers (no captcha)
    python3 -m keyfarm.orchestrator farm --providers groq,cerebras,siliconflow,github-models

    # Farm a specific provider
    python3 -m keyfarm.orchestrator farm --providers groq

    # Inject harvested keys into OmniRoute
    python3 -m keyfarm.orchestrator inject

    # Do everything: farm + inject
    python3 -m keyfarm.orchestrator all --providers groq,cerebras,siliconflow,github-models
"""

import argparse
import importlib
import sys
import traceback
from pathlib import Path


FARMERS = {
    "groq": "keyfarm.providers.groq.GroqFarmer",
    "cerebras": "keyfarm.providers.cerebras.CerebrasFarmer",
    "siliconflow": "keyfarm.providers.siliconflow.SiliconFlowFarmer",
    "github-models": "keyfarm.providers.github_models.GitHubModelsFarmer",
    "puter": "keyfarm.providers.puter.PuterFarmer",
}

DEFAULT_PROVIDERS = "groq,cerebras,siliconflow,github-models"


def dynamically_import(dotted_path: str):
    """Import 'pkg.module.Class' and return the class object."""
    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid farmer path: {dotted_path!r}")
    module = importlib.import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError(
            f"{class_name} not found in {module_path} ({e})"
        ) from e


def parse_providers(raw: str | None) -> list[str]:
    if not raw:
        return [p for p in DEFAULT_PROVIDERS.split(",") if p]
    names = [p.strip() for p in raw.split(",") if p.strip()]
    unknown = [n for n in names if n not in FARMERS]
    if unknown:
        print(f"ERROR: Unknown provider(s): {', '.join(unknown)}")
        print(f"  Available: {', '.join(FARMERS.keys())}")
        sys.exit(1)
    return names


def run_farm(providers: list[str], headless: bool = True) -> list[dict]:
    """Run each farmer in sequence. Returns a per-provider result list."""
    print("=" * 70)
    print("  Coco Router — Key Farm Orchestrator")
    print("=" * 70)
    print(f"  Providers: {', '.join(providers)}")
    print(f"  Browser : {'headless' if headless else 'visible'}")
    print("=" * 70)

    results: list[dict] = []
    for idx, name in enumerate(providers, 1):
        entry = {"provider": name, "status": "pending", "key": None, "error": None}
        print(f"\n[{idx}/{len(providers)}] 🚜 {name}")
        try:
            farmer_class = dynamically_import(FARMERS[name])
        except ImportError as e:
            print(f"  ❌ Could not import farmer: {e}")
            entry["status"] = "no-farmer"
            entry["error"] = str(e)
            results.append(entry)
            continue

        try:
            with farmer_class(headless=headless) as farmer:
                key = farmer.farm()
            if key:
                print(f"  ✅ {name}: harvested key {key[:12]}...")
                entry["status"] = "ok"
                entry["key"] = key
            else:
                print(f"  ⚠️  {name}: farmer returned no key")
                entry["status"] = "no-key"
                entry["error"] = "farm() returned None"
        except Exception as e:
            print(f"  ❌ {name}: farmer crashed — {e}")
            traceback.print_exc()
            entry["status"] = "error"
            entry["error"] = str(e)

        results.append(entry)

    print("\n" + "=" * 70)
    print("  Farm Summary")
    print("=" * 70)
    ok = sum(1 for r in results if r["status"] == "ok")
    nokey = sum(1 for r in results if r["status"] == "no-key")
    nofarmer = sum(1 for r in results if r["status"] == "no-farmer")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"  Harvested : {ok}")
    print(f"  No key    : {nokey}")
    print(f"  No farmer : {nofarmer}")
    print(f"  Errored   : {err}")
    print("=" * 70)

    # Per-provider breakdown
    print(f"  {'Provider':<15} {'Status':<11} Detail")
    print(f"  {'-'*15} {'-'*11} {'-'*30}")
    for r in results:
        detail = r["error"] or (r["key"][:12] + "..." if r["key"] else "-")
        print(f"  {r['provider']:<15} {r['status']:<11} {detail}")
    print("=" * 70)

    return results


def run_inject(db_path: str | None = None, keys_file: str | None = None, dry_run: bool = False) -> dict:
    """Defer to keyfarm.inject for the actual injection."""
    from keyfarm import inject

    kf = Path(keys_file).expanduser() if keys_file else inject.KEYS_FILE
    dbp = inject.get_db_path(db_path)
    print("\n💉 Injecting harvested keys into OmniRoute...\n")
    return inject.run(kf, dbp, dry_run=dry_run)


def cmd_farm(args):
    providers = parse_providers(args.providers)
    run_farm(providers, headless=not args.show_browser)


def cmd_inject(args):
    run_inject(args.db, args.keys_file, dry_run=args.dry_run)


def cmd_all(args):
    providers = parse_providers(args.providers)
    farm_results = run_farm(providers, headless=not args.show_browser)

    ok = sum(1 for r in farm_results if r["status"] == "ok")
    if ok == 0:
        print("\n⚠️  No keys were harvested — skipping injection.")
        return

    run_inject(args.db, args.keys_file, dry_run=args.dry_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m keyfarm.orchestrator",
        description="Coco Router Key Farm orchestrator — farm keys + inject into OmniRoute",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_farm = sub.add_parser("farm", help="Run one or more farmers in sequence")
    p_farm.add_argument(
        "--providers",
        default=DEFAULT_PROVIDERS,
        help=f"Comma-separated provider names (default: {DEFAULT_PROVIDERS})",
    )
    p_farm.add_argument(
        "--show-browser",
        action="store_true",
        help="Show the Camoufox browser while farming (default: headless)",
    )
    p_farm.set_defaults(func=cmd_farm)

    p_inject = sub.add_parser("inject", help="Inject harvested keys into OmniRoute DB")
    p_inject.add_argument("--db", default=None, help="Path to storage.sqlite")
    p_inject.add_argument("--keys-file", default=None, help="Path to harvested_keys.json")
    p_inject.add_argument("--dry-run", action="store_true", help="Show what would be injected")
    p_inject.set_defaults(func=cmd_inject)

    p_all = sub.add_parser("all", help="Farm all listed providers then inject")
    p_all.add_argument(
        "--providers",
        default=DEFAULT_PROVIDERS,
        help=f"Comma-separated provider names (default: {DEFAULT_PROVIDERS})",
    )
    p_all.add_argument(
        "--show-browser",
        action="store_true",
        help="Show the Camoufox browser while farming (default: headless)",
    )
    p_all.add_argument("--db", default=None, help="Path to storage.sqlite")
    p_all.add_argument("--keys-file", default=None, help="Path to harvested_keys.json")
    p_all.add_argument("--dry-run", action="store_true", help="Show what would be injected")
    p_all.set_defaults(func=cmd_all)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
