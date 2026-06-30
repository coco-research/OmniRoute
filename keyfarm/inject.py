#!/usr/bin/env python3
"""
Coco Router Key Farm — Key Injector
Reads harvested keys from keyfarm/harvested_keys.json and injects them into
the OmniRoute SQLite database (provider_connections table).

Usage:
    python3 -m keyfarm.inject
    python3 -m keyfarm.inject --db /custom/path/storage.sqlite
    python3 keyfarm/inject.py --db ~/.omniroute/storage.sqlite
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from uuid import uuid4

# Reuse the canonical KEYS_FILE path from base.py so we never drift.
from keyfarm.base import KEYS_FILE


def get_db_path(override: str | None = None) -> str:
    if override:
        return str(Path(override).expanduser())
    data_dir = os.environ.get("DATA_DIR", str(Path.home() / ".omniroute"))
    return str(Path(data_dir) / "storage.sqlite")


def get_db(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        print(f"ERROR: DB not found at {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def provider_has_connection(db: sqlite3.Connection, provider: str) -> bool:
    row = db.execute(
        "SELECT id FROM provider_connections WHERE provider = ?", (provider,)
    ).fetchone()
    return row is not None


def insert_apikey_connection(
    db: sqlite3.Connection,
    provider: str,
    name: str,
    api_key: str,
    email: str | None = None,
    extra: dict | None = None,
) -> str:
    """INSERT a new provider_connections row for an apikey provider.

    Mirrors the schema used by scripts/bootstrap_free_providers.py::insert_apikey_connection
    and src/lib/db/providers.ts::_insertConnectionRow (auth_type='apikey').
    """
    conn_id = str(uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    # Mirror bootstrap_free_providers.py: only emit provider_specific_data when an
    # account_id is available (cloudflare-ai, etc.). Stored as {"accountId": ...}.
    account_id = None
    if extra and isinstance(extra, dict):
        account_id = extra.get("account_id") or extra.get("accountId")
    psd = json.dumps({"accountId": account_id}) if account_id else None

    db.execute(
        """INSERT OR REPLACE INTO provider_connections
           (id, provider, auth_type, name, email, is_active, test_status,
            api_key, provider_specific_data,
            backoff_level, consecutive_use_count, rate_limit_protection,
            proxy_enabled, per_key_proxy_enabled,
            created_at, updated_at)
           VALUES (?, ?, 'apikey', ?, ?, 1, NULL, ?, ?, 0, 0, 0, 1, 0, ?, ?)""",
        (conn_id, provider, name, email or None, api_key, psd, now, now),
    )
    db.commit()
    return conn_id


def provider_display_name(provider: str, email: str | None = None) -> str:
    base = provider.replace("-", " ").title()
    if email:
        return f"{base} ({email})"
    return base


def load_harvested_keys(keys_file: Path) -> list[dict]:
    if not keys_file.exists():
        print(f"ERROR: No harvested keys file at {keys_file}")
        sys.exit(1)
    try:
        data = json.loads(keys_file.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse {keys_file}: {e}")
        sys.exit(1)
    if not isinstance(data, list):
        print(f"ERROR: Expected a list in {keys_file}, got {type(data).__name__}")
        sys.exit(1)
    return data


def run(keys_file: Path, db_path: str, dry_run: bool = False) -> dict:
    keys = load_harvested_keys(keys_file)
    db = get_db(db_path)

    injected = 0
    skipped_exists = 0
    skipped_nokey = 0
    failed = 0
    seen_providers: set[str] = set()

    print("=" * 70)
    print("  Coco Router — Key Injector")
    print("=" * 70)
    print(f"  Keys file : {keys_file}")
    print(f"  DB path   : {db_path}")
    print(f"  Candidates: {len(keys)} key(s)")
    print("=" * 70)

    for i, entry in enumerate(keys, 1):
        provider = entry.get("provider")
        api_key = entry.get("api_key")
        email = entry.get("email") or None
        extra = entry.get("extra") or {}

        if not provider:
            print(f"  [{i}] ⚠️  Entry missing 'provider' — skipping")
            failed += 1
            continue
        if not api_key:
            print(f"  [{i}] ⚠️  {provider}: entry missing 'api_key' — skipping")
            skipped_nokey += 1
            continue

        # Only inject the first key per provider — duplicates are pointless.
        if provider in seen_providers:
            print(f"  [{i}] ⏭️  {provider}: already injected earlier this run — skipping")
            skipped_exists += 1
            continue

        if provider_has_connection(db, provider):
            print(f"  [{i}] ⏭️  {provider}: connection already exists in DB — skipping")
            skipped_exists += 1
            seen_providers.add(provider)
            continue

        name = provider_display_name(provider, email)
        if dry_run:
            print(f"  [{i}] 🟡 DRY-RUN {provider}: would insert key {api_key[:12]}...")
            seen_providers.add(provider)
            injected += 1
            continue

        try:
            conn_id = insert_apikey_connection(
                db, provider, name, api_key, email=email, extra=extra
            )
            masked = api_key[:12] + "..." if len(api_key) > 12 else "***"
            print(f"  [{i}] ✅ {provider}: inserted ({masked}) id={conn_id[:8]}")
            seen_providers.add(provider)
            injected += 1
        except sqlite3.Error as e:
            print(f"  [{i}] ❌ {provider}: DB error — {e}")
            failed += 1

    db.close()

    summary = {
        "injected": injected,
        "skipped_exists": skipped_exists,
        "skipped_nokey": skipped_nokey,
        "failed": failed,
        "total": len(keys),
    }

    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    print(f"  Injected (new)     : {summary['injected']}")
    print(f"  Skipped (exists)   : {summary['skipped_exists']}")
    print(f"  Skipped (no key)   : {summary['skipped_nokey']}")
    print(f"  Failed             : {summary['failed']}")
    print(f"  Total candidates   : {summary['total']}")
    if dry_run:
        print("  (dry-run — no changes written)")
    print("=" * 70)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Inject harvested keys into OmniRoute provider_connections"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to storage.sqlite (default: $DATA_DIR/storage.sqlite or ~/.omniroute/storage.sqlite)",
    )
    parser.add_argument(
        "--keys-file",
        default=None,
        help=f"Path to harvested_keys.json (default: {KEYS_FILE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be injected without writing to DB",
    )
    args = parser.parse_args()

    keys_file = Path(args.keys_file).expanduser() if args.keys_file else KEYS_FILE
    db_path = get_db_path(args.db)
    run(keys_file, db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
