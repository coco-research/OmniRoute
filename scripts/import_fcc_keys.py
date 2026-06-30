#!/usr/bin/env python3
"""
Coco Router — Import API keys from FCC .env
Reads ~/.fcc/.env and imports all API keys into Coco Router.
"""

import os
import re
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4
import json

# Map FCC env var names to OmniRoute provider IDs
FCC_TO_OMNIROUTE = {
    "NVIDIA_NIM_API_KEY": "nvidia",
    "OPENROUTER_API_KEY": "openrouter",
    "GEMINI_API_KEY": "gemini",
    "DEEPSEEK_API_KEY": "deepseek",
    "MISTRAL_API_KEY": "mistral",
    "CODESTRAL_API_KEY": "mistral_codestral",
    "OPENCODE_API_KEY": "opencode",  # Already keyless, skip
    "WAFER_API_KEY": "wafer",
    "KIMI_API_KEY": "kimi",
    "CEREBRAS_API_KEY": "cerebras",
    "GROQ_API_KEY": "groq",
    "FIREWORKS_API_KEY": "fireworks",
    "ZAI_API_KEY": "zai",
    "CLOUDFLARE_API_TOKEN": "cloudflare-ai",
    "HF_TOKEN": "huggingface",
    "PUTER_API_TOKEN": "puter",
    "SILICONFLOW_API_KEY": "siliconflow",
    "COHERE_API_KEY": "cohere",
}

SKIP_PROVIDERS = {"opencode"}  # Already keyless, no need to add API key

def parse_env_file(path):
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value:
                env[key.strip()] = value
    return env

def get_db():
    data_dir = os.environ.get("DATA_DIR", str(Path.home() / ".omniroute"))
    db_path = str(Path(data_dir) / "storage.sqlite")
    if not Path(db_path).exists():
        print(f"ERROR: DB not found at {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    return conn

def provider_exists(db, provider):
    row = db.execute("SELECT id FROM provider_connections WHERE provider = ?", (provider,)).fetchone()
    return row is not None

def insert_apikey_connection(db, provider, name, api_key, account_id=None):
    conn_id = str(uuid4())
    now = "2026-06-29T12:00:00.000Z"
    psd = json.dumps({"accountId": account_id}) if account_id else None
    db.execute(
        """INSERT OR REPLACE INTO provider_connections
           (id, provider, auth_type, name, is_active, test_status,
            api_key, provider_specific_data,
            backoff_level, consecutive_use_count, rate_limit_protection,
            proxy_enabled, per_key_proxy_enabled,
            created_at, updated_at)
           VALUES (?, ?, 'apikey', ?, 1, NULL, ?, ?, 0, 0, 0, 1, 0, ?, ?)""",
        (conn_id, provider, name, api_key, psd, now, now),
    )
    db.commit()
    return conn_id

def main():
    fcc_env_path = Path.home() / ".fcc" / ".env"
    if not fcc_env_path.exists():
        print("ERROR: ~/.fcc/.env not found")
        sys.exit(1)

    env = parse_env_file(fcc_env_path)
    db = get_db()

    print("=" * 70)
    print("  Coco Router — Import API Keys from FCC")
    print("=" * 70)
    print()

    imported = 0
    skipped = 0
    already = 0

    for fcc_var, provider in sorted(FCC_TO_OMNIROUTE.items()):
        if provider in SKIP_PROVIDERS:
            continue

        api_key = env.get(fcc_var, "")
        if not api_key:
            print(f"  ⏭️  {provider:20} — no key in FCC env ({fcc_var})")
            skipped += 1
            continue

        if provider_exists(db, provider):
            print(f"  ⏭️  {provider:20} — already connected")
            already += 1
            continue

        account_id = None
        if provider == "cloudflare-ai":
            account_id = env.get("CLOUDFLARE_ACCOUNT_ID", "")

        name = f"Imported from FCC"
        insert_apikey_connection(db, provider, name, api_key, account_id)
        print(f"  ✅ {provider:20} — imported ({fcc_var})")
        imported += 1

    db.close()

    print()
    print("=" * 70)
    print(f"  Imported: {imported} | Already connected: {already} | Skipped: {skipped}")
    print("=" * 70)
    print()
    print("  Restart OmniRoute for model sync to pick up new providers.")
    print("  Dashboard: http://127.0.0.1:20128/home")
    print()

if __name__ == "__main__":
    main()
