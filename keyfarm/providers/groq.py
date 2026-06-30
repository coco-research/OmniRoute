"""
Coco Router Key Farm — Groq Provider (v2)
Uses Stytch B2B API directly with PKCE flow.
Sends magic link email via API (not browser), so we control the code_verifier.
"""

import html
import re
import time
import json
import base64
import ssl
import hashlib
import secrets
import uuid as uuid_mod
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone as tz

import certifi

from keyfarm.base import ProviderFarmer
from keyfarm.utils.temp_email import create_email, wait_for_email, extract_verification_link


PUBLIC_TOKEN = "public-token-live-58df57a9-a1f5-4066-bc0c-2ff942db684f"
STYTCH_BASE = "https://api.stytchb2b.groq.com"


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(certifi.where())
    return ctx


def _make_sdk_client_header():
    data = {
        "event_id": f"event-id-{uuid_mod.uuid4()}",
        "app_session_id": f"app-session-id-{uuid_mod.uuid4()}",
        "persistent_id": f"persistent-id-{uuid_mod.uuid4()}",
        "client_sent_at": datetime.now(tz.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "timezone": "America/Los_Angeles",
        "app": {"identifier": "console.groq.com"},
        "sdk": {"identifier": "Stytch.js Javascript SDK", "version": "5.43.0"},
    }
    return base64.b64encode(json.dumps(data).encode()).decode()


def _pkce_pair():
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


class GroqFarmer(ProviderFarmer):
    def __init__(self, headless=False):
        super().__init__("groq", headless=headless)

    def _stytch_headers(self):
        credentials = base64.b64encode(
            f"{PUBLIC_TOKEN}:{PUBLIC_TOKEN}".encode()
        ).decode()
        return {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Authorization": f"Basic {credentials}",
            "X-SDK-Client": _make_sdk_client_header(),
            "X-SDK-Parent-Host": "https://console.groq.com",
            "Origin": "https://console.groq.com",
            "Referer": "https://console.groq.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
        }

    def _send_magic_link(self, email: str, code_challenge: str) -> bool:
        """Send magic link email via Stytch B2B API."""
        url = f"{STYTCH_BASE}/sdk/v1/b2b/magic_links/email/discovery/send"
        body = json.dumps({
            "email_address": email,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }).encode()

        req = urllib.request.Request(
            url, data=body, headers=self._stytch_headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx()) as resp:
                data = json.loads(resp.read())
                # Response format: {"data": {"status_code": 200, ...}}
                inner = data.get("data", data)
                return inner.get("status_code") == 200 or "email_id" in str(data) or resp.status == 200
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"  ❌ Send magic link failed (HTTP {e.code}): {body}")
            return False
        except Exception as e:
            print(f"  ❌ Send magic link error: {e}")
            return False

    def _authenticate_magic_link(self, token: str, code_verifier: str) -> dict | None:
        """Authenticate the discovery magic link with PKCE code_verifier."""
        url = f"{STYTCH_BASE}/sdk/v1/b2b/magic_links/discovery/authenticate"
        body = json.dumps({
            "magic_link_token": token,
            "code_verifier": code_verifier,
        }).encode()

        req = urllib.request.Request(
            url, data=body, headers=self._stytch_headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx()) as resp:
                data = json.loads(resp.read())
                print(f"  ✅ Magic link authenticated!")
                return data
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            print(f"  ❌ Auth failed (HTTP {e.code}): {body}")
            return None
        except Exception as e:
            print(f"  ❌ Auth error: {e}")
            return None

    def _exchange_session(self, intermediate_session_token: str, discovered_orgs: list) -> dict | None:
        """Exchange intermediate session for a full session."""
        headers = self._stytch_headers()

        if discovered_orgs:
            org_id = discovered_orgs[0].get("organization", {}).get("organization_id", "")
            url = f"{STYTCH_BASE}/sdk/v1/b2b/discovery/organizations/exchange"
            body = json.dumps({
                "intermediate_session_token": intermediate_session_token,
                "organization_id": org_id,
            }).encode()
            print(f"  🔑 Exchanging session for org: {org_id[:20]}...")
        else:
            url = f"{STYTCH_BASE}/sdk/v1/b2b/discovery/organizations/create"
            body = json.dumps({
                "intermediate_session_token": intermediate_session_token,
                "organization_name": "Coco Router",
            }).encode()
            print(f"  🔑 Creating new org...")

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx()) as resp:
                data = json.loads(resp.read())
                session_jwt = data.get("session_jwt", "")
                if session_jwt:
                    print(f"  ✅ Session established: {session_jwt[:30]}...")
                    return data
                else:
                    print(f"  ❌ No session_jwt: {json.dumps(data)[:300]}")
                    return None
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            print(f"  ❌ Exchange failed (HTTP {e.code}): {body}")
            return None
        except Exception as e:
            print(f"  ❌ Exchange error: {e}")
            return None

    def _dismiss_consent_banner(self, page):
        """Dismiss privacy/cookie consent banners."""
        try:
            text = page.inner_text("body")[:500].lower()
        except Exception:
            return
        if not any(k in text for k in ("privacy", "consent", "cookie", "we use cookies")):
            return
        for selector in [
            'button:has-text("Accept")', 'button:has-text("Agree")',
            'button:has-text("OK")', 'button:has-text("Continue")',
            'button:has-text("Got it")', 'button:has-text("I accept")',
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    el.click()
                    print(f"  ✅ Dismissed consent banner")
                    time.sleep(2)
                    return
            except:
                continue

    def farm(self) -> str | None:
        print("\n  🚜 Farming Groq account...")

        # Create temp email
        email_account = create_email()
        if "error" in email_account:
            print(f"  ❌ Temp email failed: {email_account}")
            return None
        self.email = email_account["email"]
        self.email_token = email_account["token"]
        print(f"  📧 Email: {self.email}")

        # Step 1: Generate PKCE pair
        code_verifier, code_challenge = _pkce_pair()
        print(f"  🔐 Generated PKCE pair")

        # Step 2: Send magic link via Stytch API (we control the code_verifier)
        print("  📧 Sending magic link via Stytch API...")
        if not self._send_magic_link(self.email, code_challenge):
            return None
        print(f"  ✅ Magic link sent to {self.email}")

        # Step 3: Wait for email
        print("  ⏳ Waiting for magic link email...")
        msg = wait_for_email(self.email_token, timeout=90)
        if not msg:
            print("  ❌ No email received within 90s")
            return None
        print(f"  ✅ Got email: {msg.get('subject', '')}")

        # Step 4: Extract magic link token from email
        text = msg.get("text", "")
        html_content = msg.get("html", "")
        if isinstance(html_content, list):
            html_content = html_content[0] if html_content else ""
        content = text or html_content

        link = extract_verification_link(content)
        if not link:
            print(f"  ❌ Could not find verification link")
            print(f"     Content: {content[:300]}")
            return None
        link = html.unescape(link)
        print(f"  ✅ Magic link: {link[:60]}...")

        # Extract the token from the URL
        parsed = urllib.parse.urlparse(link)
        params = urllib.parse.parse_qs(parsed.query)
        magic_token = params.get("token", [""])[0]
        if not magic_token:
            print("  ❌ Could not extract token from magic link URL")
            return None

        # Step 5: Authenticate the magic link with PKCE
        print("  🔑 Authenticating magic link with PKCE...")
        auth_data = self._authenticate_magic_link(magic_token, code_verifier)
        if not auth_data:
            return None

        ist = auth_data.get("intermediate_session_token", "")
        discovered_orgs = auth_data.get("discovered_organizations", [])
        if not ist:
            print(f"  ❌ No intermediate_session_token: {json.dumps(auth_data)[:300]}")
            return None

        # Step 6: Exchange for full session
        session_data = self._exchange_session(ist, discovered_orgs)
        if not session_data:
            return None

        session_jwt = session_data.get("session_jwt", "")
        session_token = session_data.get("session_token", "")
        if not session_jwt:
            print("  ❌ No session_jwt in exchange response")
            return None

        # Step 7: Inject cookies into browser and navigate to Groq
        print("  🌐 Opening browser with session cookies...")
        page = self.new_page()

        cookies = [
            {
                "name": "stytch_b2b_session_jwt",
                "value": session_jwt,
                "domain": ".groq.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            },
            {
                "name": "stytch_b2b_session",
                "value": session_token,
                "domain": ".groq.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            },
        ]
        try:
            self._ctx.add_cookies(cookies)
            print("  ✅ Injected session cookies")
        except Exception as e:
            print(f"  ❌ Cookie injection failed: {e}")
            return None

        # Navigate to API keys page
        page.goto("https://console.groq.com/keys", timeout=30000, wait_until="domcontentloaded")
        time.sleep(5)
        self._dismiss_consent_banner(page)

        url = page.url
        try:
            text_snippet = page.inner_text("body")[:300]
        except:
            text_snippet = ""
        print(f"  📍 Keys page: {url}")
        print(f"  📍 Text: {text_snippet[:200]}")

        # Check if logged in
        lower = text_snippet.lower()
        if "create an account" in lower or "log in" in lower:
            # Maybe need to also authenticate the session via API
            print("  ⚠️  Session not recognized — trying session authenticate...")
            self._stytch_session_authenticate(session_jwt)
            time.sleep(2)
            page.goto("https://console.groq.com/keys", timeout=30000, wait_until="domcontentloaded")
            time.sleep(5)
            try:
                text_snippet = page.inner_text("body")[:300]
            except:
                text_snippet = ""
            if "create an account" in text_snippet.lower() or "log in" in text_snippet.lower():
                print("  ❌ Still not logged in after session authenticate")
                return None

        # Step 8: Create API key
        print("  🔑 Creating API key...")
        try:
            for selector in [
                'button:has-text("Create API Key")',
                'button:has-text("Create")',
                'button:has-text("New Key")',
                'button:has-text("Generate")',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=2000):
                        el.click()
                        print(f"  ✅ Clicked '{selector}'")
                        break
                except:
                    continue

            time.sleep(2)

            # Name the key
            try:
                name_input = page.locator('input[type="text"]').first
                if name_input.is_visible(timeout=2000):
                    name_input.fill("coco-router")
                    time.sleep(0.5)
            except:
                pass

            # Confirm
            for selector in [
                'button:has-text("Create")', 'button:has-text("Confirm")',
                'button:has-text("Save")', 'button[type="submit"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f"  ✅ Confirmed key creation")
                        break
                except:
                    continue

            time.sleep(3)

            # Extract API key
            print("  🔍 Extracting API key...")
            api_key = None
            for attempt in range(6):
                for inp in page.locator("input").all():
                    try:
                        val = inp.input_value() or ""
                    except:
                        val = inp.get_attribute("value") or ""
                    if val.startswith("gsk_"):
                        api_key = val
                        break
                if api_key:
                    break
                try:
                    body_text = page.inner_text("body")
                    match = re.search(r'(gsk_[A-Za-z0-9]{40,})', body_text)
                    if match:
                        api_key = match.group(1)
                        break
                except:
                    pass
                time.sleep(1)

            if api_key:
                print(f"  ✅ Got API key: {api_key[:20]}...")
                self.save_key(api_key, self.email)
                return api_key
            else:
                print("  ❌ Could not extract API key")
                self.screenshot("no_key_found")

        except Exception as e:
            print(f"  ❌ API key creation failed: {e}")
            self.screenshot("key_error")

        return None

    def _stytch_session_authenticate(self, session_jwt: str):
        """Authenticate the session via Stytch API to make it valid."""
        url = f"{STYTCH_BASE}/sdk/v1/b2b/sessions/authenticate"
        body = json.dumps({"session_jwt": session_jwt}).encode()
        req = urllib.request.Request(
            url, data=body, headers=self._stytch_headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx()) as resp:
                data = json.loads(resp.read())
                print(f"  ✅ Session authenticated via API")
                # Update cookies with refreshed JWT
                new_jwt = data.get("session_jwt", "")
                if new_jwt:
                    self._ctx.add_cookies([{
                        "name": "stytch_b2b_session_jwt",
                        "value": new_jwt,
                        "domain": ".groq.com",
                        "path": "/",
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "Lax",
                    }])
        except Exception as e:
            print(f"  ⚠️  Session authenticate failed: {e}")


if __name__ == "__main__":
    with GroqFarmer(headless=False) as farmer:
        key = farmer.farm()
        if key:
            print(f"\n✅ Success! Groq API key: {key[:20]}...")
        else:
            print("\n❌ Failed to farm Groq account")
