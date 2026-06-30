# Coco Router — Master Plan & Status

## What is Coco Router?

A fork of OmniRoute that auto-connects free AI providers and auto-routes requests across them.
Goal: Use Claude Code (or any AI CLI) with frontier models at zero cost.

## Architecture

```
Claude Code CLI → Coco Router (port 20128) → auto-routing across free providers
                                                    ↓
                    Kiro (11 models) | NVIDIA NIM (13) | Cloudflare (6) |
                    OpenCode (7) | TheOldLLM (12) | Gemini (5) | GitHub Models (14) |
                    Puter (33) | Groq (5) | Cerebras (2) | SiliconFlow (10) | ...
```

## Current Status

### ✅ Done
- **Phase 1: Fork & Strip** — OmniRoute forked to `coco-research/OmniRoute`, auth disabled, sidebar stripped, CLI simplified. 495+ models available.
- **Phase 2: Auto-connect** — `bootstrap_free_providers.py` auto-connects 6 keyless providers. `import_fcc_keys.py` imports keys from FCC. Cloudflare account ID fixed.
- **Phase 3A: Camoufox + temp email** — Camoufox installed and working. Temp email via mail.tm API working.
- **Phase 3B: Puter farmer** — Built but BLOCKED by CAPTCHA on signup.
- **Phase 3C: GitHub Models farmer** — ✅ WORKING. Uses `gh` CLI token, no browser needed. 1 key harvested.
- **Phase 3D: Cerebras farmer** — Built, needs selector debugging against live page.
- **Phase 3E: SiliconFlow farmer** — Built, BLOCKED by phone verification requirement.
- **Phase 3F: Key injector + orchestrator** — Built. `keyfarm/inject.py` + `keyfarm/orchestrator.py`.
- **OpenCode config** — `~/.config/opencode/opencode.json` configured to use Coco Router with `auto/best-coding`.

### ❌ Blocked
- **Groq farmer** — Stytch B2B magic link authentication blocked. Details below.
- **Puter farmer** — CAPTCHA on signup. Needs 2captcha integration.
- **SiliconFlow farmer** — Phone verification required. Needs 5sim integration.

### 📋 TODO
- Phase 3G: Fix Groq farmer (see blocker details below)
- Phase 3H: 2captcha integration (unblocks Puter)
- Phase 3I: 5sim integration (unblocks SiliconFlow + Gmail creator)
- Phase 3J: Gmail creator (for providers needing Gmail)
- Phase 4: One-click installer (`install.sh`)
- Phase 5: Switch Claude Code from FCC to Coco Router (last step)

## Manual Setup Required (Minimal User Ask)

Some providers cannot be fully automated. For these, Coco Router asks the user for the **minimum** needed and then handles everything else (key rotation, pooling, health checks). The user should only need to do each step **once** — after that, Coco Router manages the keys.

### Tier 1: Just need an API key (paste once, pool forever)

These providers need the user to create **one account manually** and paste the API key. Coco Router then pools and rotates it. For multi-account rotation, the user repeats the signup manually on the provider's site and pastes additional keys — Coco Router handles the rest.

| Provider | What the user does | Time | Why automated? |
|---|---|---|---|
| **Groq** | 1. Go to console.groq.com → sign in with email → create API key → paste it | 2 min | Stytch DFP blocks automated signup |
| **Puter** | 1. Go to puter.com → create account → dashboard → copy auth token → paste it | 2 min | CAPTCHA on signup |
| **Cerebras** | 1. Go to cloud.cerebras.ai → sign up → create API key → paste it | 2 min | SPA needs interactive debugging |
| **Mistral** | 1. Go to console.mistral.ai → sign up → create API key → paste it | 2 min | No farmer built yet |
| **DeepSeek** | 1. Go to platform.deepseek.com → sign up → create API key → paste it | 2 min | No farmer built yet |

**How Coco Router handles these:** `python3 -m keyfarm.orchestrator add-key --provider groq` prompts for the key, validates it, injects it into the pool, and starts using it immediately. Adding a second key later just appends to the pool — rotation is automatic.

### Tier 2: Need OAuth login (browser session, one-time)

| Provider | What the user does | Time |
|---|---|---|
| **Kiro** | ✅ Already connected — nothing needed | 0 min |
| **Antigravity (AGY)** | Click "Connect" in Coco Router dashboard → Google login | 30 sec |
| **OpenCode Zen** | Click "Connect" → OpenCode login | 30 sec |
| **Qoder** | Get PAT from Qoder settings → paste it | 1 min |
| **HuggingChat** | Click "Connect" → HuggingFace login | 30 sec |

### Tier 3: Need external service (one-time setup, then automated)

| Service | What it unblocks | Cost | Setup |
|---|---|---|---|
| **2captcha** | Puter (33 models), any CAPTCHA-protected provider | ~$3/1000 solves | Sign up at 2captcha.com → add $5 → paste API key into `~/.coco-router/2captcha.key` |
| **5sim** | SiliconFlow, Gmail creator, any phone-verified provider | ~$0.50/number | Sign up at 5sim.net → add $5 → paste API key into `~/.coco-router/5sim.key` |
| **Residential proxy** | Multiple account creation without IP bans | $50+/mo | Sign up at any proxy provider → paste proxy URL into `~/.coco-router/proxy.txt` |

**Once these services are configured, Coco Router's key farm runs fully automated:**
```
python3 -m keyfarm.orchestrator farm-all
→ Creates Gmail accounts (using 5sim + proxy)
→ Signs up at each provider (using Camoufox + proxy)
→ Harvests API keys
→ Injects into pool
→ Starts rotating
```

### Design Principle: Minimum Repetition

The user should never have to do the same manual step more than **once per provider**. After that:
- Coco Router pools the key
- Health checks run every 6 hours
- Dead keys are removed automatically
- If a key is banned, Coco Router alerts the user and asks for a replacement (one paste)
- Multi-key rotation means one banned key doesn't stop work — it falls back to the next

## Groq Farmer Blocker — Technical Details

Groq uses Stytch B2B for auth. The flow:
1. User enters email → Stytch sends magic link
2. User clicks magic link → Stytch redirect page authenticates
3. Session established → user creates API key

**Problem:** Stytch's redirect page (`stytch.com/v1/magic_links/redirect`) runs Device Fingerprinting Protection (DFP). Camoufox fails the DFP check → redirected to `stytch.com/redirect-error`.

**Attempted bypass:** Call Stytch B2B API directly (bypassing the browser redirect):
- Endpoint: `POST https://api.stytchb2b.groq.com/sdk/v1/b2b/magic_links/discovery/authenticate`
- Headers needed: `X-SDK-Client` (base64-encoded JSON with event_id, app_session_id, persistent_id, etc.)
- Auth: Basic auth with `public_token` as both user and password
- Body: `{"magic_link_token": "TOKEN", "code_verifier": "VERIFIER"}`

**PKCE required:** Bootstrap config shows `pkce_required_for_email_magic_links: true`. We send the magic link via API with a PKCE code_challenge, then authenticate with the code_verifier. The magic link is sent successfully, the email is received, the token is extracted (44 chars, correct format), but authentication returns `{"error_type":"invalid_token","error_message":"Token format is invalid."}`.

**What's been tried:**
- Various field names: `magic_link_token`, `token`, `discovery_magic_link_token`
- Various endpoints: `/sdk/v1/b2b/magic_links/authenticate`, `/sdk/v1/b2b/magic_links/discovery/authenticate`
- With and without PKCE (code_verifier + code_challenge)
- 32-byte and 64-byte code verifiers
- Correct `X-SDK-Client` header matching Stytch.js v5.43.0 format

**Next steps for this blocker:**
1. Read the Stytch B2B SDK source code (npm: `@stytch/vanilla-js`) to find the exact API call format
2. Or intercept the actual authenticate call from a real browser session that passes DFP
3. Or try using a non-Camoufox browser (regular Playwright Firefox) that might pass DFP
4. Or use Groq's Google/GitHub OAuth flow instead of email magic link

## Files

### Fork Changes (committed to `coco-research/OmniRoute`)
- `src/lib/db/settings.ts` — Auth disabled by default (`requireLogin: false`, `setupComplete: true`)
- `src/shared/constants/sidebarVisibility.ts` — Sidebar stripped to 5 sections
- `bin/cli/commands/registry.mjs` — CLI reduced from 81 to 16 commands
- `scripts/bootstrap_free_providers.py` — Auto-connect keyless + API key providers
- `scripts/import_fcc_keys.py` — Import keys from FCC `.env`

### Key Farm (in `keyfarm/` directory)
- `keyfarm/base.py` — ProviderFarmer base class with Camoufox
- `keyfarm/utils/temp_email.py` — mail.tm temp email helper
- `keyfarm/providers/groq.py` — Groq farmer (BLOCKED by Stytch PKCE/DFP)
- `keyfarm/providers/puter.py` — Puter farmer (BLOCKED by CAPTCHA)
- `keyfarm/providers/cerebras.py` — Cerebras farmer (needs selector debugging)
- `keyfarm/providers/siliconflow.py` — SiliconFlow farmer (BLOCKED by phone verify)
- `keyfarm/providers/github_models.py` — ✅ Working (PAT-based, no browser)
- `keyfarm/inject.py` — Inject harvested keys into OmniRoute DB
- `keyfarm/orchestrator.py` — One-command farm + inject
- `keyfarm/harvested_keys.json` — 1 key harvested (GitHub Models)

## How to Run

```bash
# Start Coco Router (OmniRoute fork on port 20128)
cd ~/OmniRoute && npm run dev  # or: omniroute serve --port 20128

# Auto-connect free providers
python3 scripts/bootstrap_free_providers.py --port 20128

# Import FCC keys
python3 scripts/import_fcc_keys.py

# Farm GitHub Models key (works now)
python3 -m keyfarm.providers.github_models

# Inject harvested keys
python3 -m keyfarm.inject

# Use with Claude Code
ANTHROPIC_BASE_URL=http://127.0.0.1:20128 ANTHROPIC_API_KEY=test claude -p "hello" --model auto/best-coding

# Or with OpenCode
opencode --model coco-router/auto/best-coding
```

## Free Provider Tiers (Farmable)

| Provider | Auth | Models | Free Allowance | Status |
|---|---|---|---|---|
| Kiro | OAuth | 11 | 25K tok/mo per model | ✅ Connected |
| NVIDIA NIM | API key | 13 | Free tier | ✅ Connected |
| Cloudflare AI | API key | 6 | 10K neurons/day | ✅ Connected |
| OpenCode | Keyless | 7 | Unlimited | ✅ Connected |
| TheOldLLM | Keyless | 12 | Unlimited | ✅ Connected |
| Gemini | API key | 5 | Free tier | ✅ Connected |
| OpenRouter | API key | 1+ | Free models | ✅ Connected |
| GitHub Models | PAT | 14 | 18M tok/day | ✅ Farmed |
| Puter | Auth token | 33 | Unlimited | ❌ CAPTCHA |
| Groq | Magic link | 5 | 15M tok/day | ❌ Stytch DFP |
| Cerebras | API key | 2 | 30M tok/day | ⚠️ Needs debugging |
| SiliconFlow | API key | 10 | Uncapped | ❌ Phone verify |
| Mistral | API key | 5 | 1B tok/mo | ❌ No key |
| DeepSeek | API key | 2 | Pay-per-use | ❌ No key |

## Repos

- **OmniRoute fork:** `https://github.com/coco-research/OmniRoute` (code + key farm)
- **Coco-Router repo:** `https://github.com/coco-research/Coco-Router` (this plan + docs)
