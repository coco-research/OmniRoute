#!/usr/bin/env python3
"""
Coco Router — Free Provider Bootstrap
Auto-connects all free/keyless providers to Coco Router (OmniRoute fork).

Usage:
  python3 bootstrap_free_providers.py [--port 20128] [--api-key <key>]

Categories:
  1. True keyless (no auth needed, works immediately)
  2. Keyless but needs a connection row for model discovery
  3. API key providers (prompts for keys or reads from env)
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from uuid import uuid4

# ─── Provider definitions ───────────────────────────────────────────────────

# Tier 1: True keyless — work with synthetic credentials, no DB row needed.
# We create a connection row anyway so they show in the dashboard + model list.
KEYLESS_PROVIDERS = [
    {
        "provider": "opencode",
        "name": "OpenCode Free (keyless)",
        "auth_type": "no-auth",
        "note": "Kimi, GLM, Qwen, MiMo, MiniMax — no key needed",
    },
    {
        "provider": "theoldllm",
        "name": "The Old LLM (keyless)",
        "auth_type": "no-auth",
        "note": "GPT-5.4, Claude 4.6 Opus/Sonnet/Haiku — auto-generated tokens",
    },
    {
        "provider": "duckduckgo-web",
        "name": "DuckDuckGo AI Chat (keyless)",
        "auth_type": "no-auth",
        "note": "Anonymous — rate limited, may fail during peak hours",
    },
    {
        "provider": "mimocode",
        "name": "MiMoCode (keyless)",
        "auth_type": "no-auth",
        "note": "Xiaomi MiMo models — JWT auto-generated",
    },
    {
        "provider": "chipotle",
        "name": "Chipotle Pepper AI (keyless)",
        "auth_type": "no-auth",
        "note": "IPsoft Amelia — anonymous, rate-limited",
    },
    {
        "provider": "veoaifree-web",
        "name": "Veo AI Free (keyless)",
        "auth_type": "no-auth",
        "note": "Video generation — VEO 3.1, Seedance. 6 req/hour",
    },
]

# Tier 2: Need API key but are free. User provides keys or they get farmed later.
API_KEY_PROVIDERS = [
    {
        "provider": "puter",
        "name": "Puter (33 models — GPT, Claude, Gemini, Grok)",
        "env_var": "PUTER_API_TOKEN",
        "hint": "Get token at puter.com/dashboard → Copy Auth Token",
        "models_hint": "gpt-4o, claude-sonnet-4-6, gemini-3.5-flash, grok-3, deepseek-v3",
    },
    {
        "provider": "siliconflow",
        "name": "SiliconFlow (10 models, uncapped free)",
        "env_var": "SILICONFLOW_API_KEY",
        "hint": "Get key at siliconflow.cn → API Keys",
        "models_hint": "Qwen, DeepSeek, GLM, Llama",
    },
    {
        "provider": "groq",
        "name": "Groq (5 models, 15M tok/day)",
        "env_var": "GROQ_API_KEY",
        "hint": "Get key at console.groq.com → API Keys",
        "models_hint": "Llama, Mixtral, Gemma",
    },
    {
        "provider": "cerebras",
        "name": "Cerebras (2 models, 30M tok/day)",
        "env_var": "CEREBRAS_API_KEY",
        "hint": "Get key at cloud.cerebras.ai → API Keys",
        "models_hint": "Llama 3.3 70B, Llama 4",
    },
    {
        "provider": "github-models",
        "name": "GitHub Models (14 models, 18M tok/day)",
        "env_var": "GITHUB_TOKEN",
        "hint": "Use any GitHub PAT with read:user scope",
        "models_hint": "GPT-4o, Llama, Phi, Mistral",
    },
    {
        "provider": "mistral",
        "name": "Mistral (5 models, 1B tok/mo)",
        "env_var": "MISTRAL_API_KEY",
        "hint": "Get key at console.mistral.ai → API Keys",
        "models_hint": "Mistral Large, Codestral, Tiny",
    },
    {
        "provider": "deepseek",
        "name": "DeepSeek (2 models)",
        "env_var": "DEEPSEEK_API_KEY",
        "hint": "Get key at platform.deepseek.com → API Keys",
        "models_hint": "DeepSeek V3.2, DeepSeek R1",
    },
    {
        "provider": "gemini",
        "name": "Google AI Studio (5 models)",
        "env_var": "GEMINI_API_KEY",
        "hint": "Get key at aistudio.google.com → Get API Key",
        "models_hint": "Gemini 3 Pro, 3 Flash, 2.5 Flash",
    },
    {
        "provider": "openrouter",
        "name": "OpenRouter (1+ free models)",
        "env_var": "OPENROUTER_API_KEY",
        "hint": "Get key at openrouter.ai → Keys",
        "models_hint": "Free: Llama, Mistral, Gemma, DeepSeek R1",
    },
    {
        "provider": "cloudflare-ai",
        "name": "Cloudflare Workers AI (6 models, 10K neurons/day)",
        "env_var": "CLOUDFLARE_API_TOKEN",
        "account_id_var": "CLOUDFLARE_ACCOUNT_ID",
        "hint": "Get token at dash.cloudflare.com → API Tokens",
        "models_hint": "GLM-4.7-Flash, Llama 3.3, Mistral, Qwen",
    },
]

# Tier 3: OAuth providers — need browser auth, already connected or manual
OAUTH_PROVIDERS = [
    {
        "provider": "kiro",
        "name": "Kiro (11 models — Claude Opus, GLM-5, DeepSeek, Qwen)",
        "status": "already_connected",
        "note": "OAuth via Kiro desktop app — 25K tok/mo per model",
    },
    {
        "provider": "agy",
        "name": "Antigravity (16 models — Claude, Gemini, GPT-OSS)",
        "status": "needs_oauth",
        "note": "OAuth via Google account",
    },
    {
        "provider": "opencode-zen",
        "name": "OpenCode Zen (6 models, uncapped free)",
        "status": "needs_oauth",
        "note": "OAuth via OpenCode",
    },
    {
        "provider": "qoder",
        "name": "Qoder (14 models)",
        "status": "needs_oauth",
        "note": "OAuth via Qoder PAT",
    },
    {
        "provider": "kilo-gateway",
        "name": "Kilo Gateway (7 models, uncapped free)",
        "status": "needs_oauth",
        "note": "OAuth via Kilo Code",
    },
    {
        "provider": "huggingchat",
        "name": "HuggingChat (4 models, 500K tok/mo)",
        "status": "needs_oauth",
        "note": "OAuth via HuggingFace account",
    },
    {
        "provider": "cohere",
        "name": "Cohere (6 models, 800K tok/mo)",
        "status": "needs_apikey",
        "env_var": "COHERE_API_KEY",
        "hint": "Get key at dashboard.cohere.com → API Keys",
    },
]

# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_db_path():
    data_dir = os.environ.get("DATA_DIR", str(Path.home() / ".omniroute"))
    return str(Path(data_dir) / "storage.sqlite")

def get_db():
    db_path = get_db_path()
    if not Path(db_path).exists():
        print(f"ERROR: DB not found at {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def provider_exists(db, provider):
    row = db.execute(
        "SELECT id FROM provider_connections WHERE provider = ?", (provider,)
    ).fetchone()
    return row is not None

def insert_noauth_connection(db, provider, name):
    conn_id = str(uuid4())
    now = "2026-06-29T12:00:00.000Z"
    db.execute(
        """INSERT OR REPLACE INTO provider_connections
           (id, provider, auth_type, name, is_active, test_status,
            backoff_level, consecutive_use_count, rate_limit_protection,
            proxy_enabled, per_key_proxy_enabled,
            created_at, updated_at)
           VALUES (?, ?, 'no-auth', ?, 1, NULL, 0, 0, 0, 1, 0, ?, ?)""",
        (conn_id, provider, name, now, now),
    )
    db.commit()
    return conn_id

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

# ─── API test helper ─────────────────────────────────────────────────────────

def test_model(base_url, model_id, timeout=15):
    try:
        data = json.dumps({
            "model": model_id,
            "messages": [{"role": "user", "content": "say ok"}],
            "max_tokens": 5,
        }).encode()
        req = urllib.request.Request(
            f"{base_url}/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            if "error" in body:
                return False, body[:100]
            return True, "OK"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, str(e)[:100]

def get_models(base_url, timeout=10):
    try:
        req = urllib.request.Request(f"{base_url}/v1/models")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return [m["id"] for m in data.get("data", [])]
    except:
        return []

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bootstrap free providers for Coco Router")
    parser.add_argument("--port", type=int, default=20128, help="OmniRoute port (default: 20128)")
    parser.add_argument("--db-only", action="store_true", help="Skip API tests, just insert DB rows")
    parser.add_argument("--add-keys", action="store_true", help="Prompt for API keys interactively")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    db = get_db()

    print("=" * 70)
    print("  Coco Router — Free Provider Bootstrap")
    print("=" * 70)

    # ── Phase 1: Keyless providers ──
    print("\n📋 Phase 1: Keyless providers (no auth needed)\n")
    keyless_added = 0
    keyless_existing = 0
    for p in KEYLESS_PROVIDERS:
        exists = provider_exists(db, p["provider"])
        if exists:
            print(f"  ⏭️  {p['provider']:20} already connected — {p['note']}")
            keyless_existing += 1
        else:
            conn_id = insert_noauth_connection(db, p["provider"], p["name"])
            print(f"  ✅ {p['provider']:20} connected — {p['note']}")
            keyless_added += 1

    # ── Phase 2: API key providers ──
    print(f"\n📋 Phase 2: API key providers (free tiers)\n")
    apikey_added = 0
    apikey_skipped = 0
    for p in API_KEY_PROVIDERS:
        exists = provider_exists(db, p["provider"])
        if exists:
            print(f"  ⏭️  {p['provider']:20} already connected")
            continue

        # Try to get key from env
        env_var = p.get("env_var", "")
        api_key = os.environ.get(env_var, "")

        # Also check ~/.fcc/.env for existing keys
        if not api_key:
            fcc_env = Path.home() / ".fcc" / ".env"
            if fcc_env.exists():
                for line in fcc_env.read_text().splitlines():
                    if line.startswith(f"{env_var}="):
                        api_key = line.split("=", 1)[1].strip().strip('"')
                        break

        if not api_key and args.add_keys:
            print(f"\n  🔑 {p['name']}")
            print(f"     {p['hint']}")
            api_key = input(f"     Enter {env_var} (or press Enter to skip): ").strip()

        if not api_key:
            print(f"  ⏭️  {p['provider']:20} skipped (no key) — {p.get('models_hint', '')}")
            apikey_skipped += 1
            continue

        account_id = None
        if p.get("account_id_var"):
            account_id = os.environ.get(p["account_id_var"], "")
            if not account_id:
                fcc_env = Path.home() / ".fcc" / ".env"
                if fcc_env.exists():
                    for line in fcc_env.read_text().splitlines():
                        if line.startswith(f"{p['account_id_var']}="):
                            account_id = line.split("=", 1)[1].strip().strip('"')
                            break

        conn_id = insert_apikey_connection(db, p["provider"], p["name"], api_key, account_id)
        print(f"  ✅ {p['provider']:20} connected — {p.get('models_hint', '')}")
        apikey_added += 1

    # ── Phase 3: OAuth providers (report only) ──
    print(f"\n📋 Phase 3: OAuth providers (need manual browser auth)\n")
    for p in OAUTH_PROVIDERS:
        exists = provider_exists(db, p["provider"])
        status = "✅ connected" if exists else f"⚠️  {p['status']}"
        print(f"  {status:16} {p['provider']:20} — {p.get('note', '')}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print(f"  Summary: +{keyless_added} keyless, +{apikey_added} API key, {apikey_skipped} skipped")
    print("=" * 70)

    # ── Test ──
    if not args.db_only:
        print("\n🧪 Testing providers...\n")
        all_models = get_models(base_url)
        if not all_models:
            print("  ⚠️  Could not fetch model list. Is OmniRoute running on port", args.port, "?")
        else:
            print(f"  📦 {len(all_models)} models available\n")

            # Test a few key models
            test_models = []
            for m in all_models:
                if any(m.startswith(prefix) for prefix in ["oc/", "tllm/", "kiro/", "cloudflare-ai/"]):
                    test_models.append(m)
            test_models = test_models[:8]

            for model in test_models:
                ok, msg = test_model(base_url, model)
                icon = "✅" if ok else "❌"
                print(f"  {icon} {model:50} {msg[:40]}")
                time.sleep(0.5)

    print("\n✨ Done! Open the dashboard at http://127.0.0.1:" + str(args.port) + "/home")
    print("   Claude Code: claude -p 'hello' --model auto/best-coding\n")

    db.close()

if __name__ == "__main__":
    main()
