"""
Coco Router Key Farm — Puter Provider
Puter gives access to 33+ models: GPT-5.4, Claude Opus/Sonnet, Gemini, Grok, DeepSeek.
Signup flow: username + password only (no email verification).
Token: extracted from puter.com dashboard after login.
"""

import time
import json
import re
from keyfarm.base import ProviderFarmer
from keyfarm.utils.temp_email import create_email, wait_for_email, extract_verification_link


class PuterFarmer(ProviderFarmer):
    def __init__(self, headless=False):
        super().__init__("puter", headless=headless)

    def farm(self) -> str | None:
        print("\n  🚜 Farming Puter account...")

        # Create temp email (Puter may ask for email)
        email_account = create_email()
        if "error" in email_account:
            print(f"  ❌ Temp email failed: {email_account}")
            return None
        self.email = email_account["email"]
        self.email_token = email_account["token"]
        print(f"  📧 Email: {self.email}")

        page = self.new_page()

        # Go to Puter — it shows a login page first, we need to click "Create an account"
        print("  🌐 Navigating to puter.com...")
        page.goto("https://puter.com", timeout=30000)
        time.sleep(3)
        self._debug_page("initial")

        # Click "Create an account" / "Create Free Account" link
        clicked = False
        for selector in [
            'text="Create an account"',
            'text="Create Free Account"',
            'text="Sign Up"',
        ]:
            try:
                el = page.get_by_text(selector.replace('text="', '').replace('"', ''), exact=False).first
                if el.is_visible(timeout=2000):
                    el.click()
                    print(f"  ✅ Clicked '{selector}'")
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            print("  ⚠️  No 'Create account' link found")
            self._debug_page("no_create_link")
            return None

        time.sleep(3)
        self._debug_page("signup_form")

        # The signup page shows OAuth buttons + "Sign up using email" link
        # Click "Sign up using email" to get the email form
        clicked_email = False
        for selector in [
            'text="Sign up using email"',
            'text="Sign up with email"',
            'text="email"',
        ]:
            try:
                el = page.get_by_text(selector.replace('text="', '').replace('"', ''), exact=False).first
                if el.is_visible(timeout=2000):
                    el.click()
                    print(f"  ✅ Clicked '{selector}'")
                    clicked_email = True
                    break
            except:
                continue

        if not clicked_email:
            print("  ⚠️  No 'Sign up using email' link — checking page state")
            self._debug_page("no_email_link")

        time.sleep(2)
        self._debug_page("email_form")

        # Fill signup form
        import secrets, string
        username = "coco" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        password = "Co" + "".join(secrets.choice(string.ascii_letters + string.digits + "!@#") for _ in range(14))

        try:
            inputs = page.locator("input:visible").all()
            print(f"  📝 Found {len(inputs)} visible input fields")

            for i, inp in enumerate(inputs):
                inp_type = inp.get_attribute("type") or "text"
                inp_placeholder = inp.get_attribute("placeholder") or ""
                inp_name = inp.get_attribute("name") or ""
                inp_id = inp.get_attribute("id") or ""
                print(f"    input[{i}] type={inp_type} name={inp_name} id={inp_id} placeholder={inp_placeholder}")

                # Skip captcha inputs — they need special handling
                if "captcha" in inp_name.lower() or "captcha" in inp_id.lower():
                    print(f"    ⏭️  Skipping captcha field")
                    continue

                if inp_type == "password":
                    inp.fill(password)
                    print(f"  ✅ Filled password in input[{i}]")
                elif inp_type in ("text", "email"):
                    if "email" in inp_name.lower() or "email" in inp_id.lower() or "email" in inp_placeholder.lower():
                        inp.fill(self.email)
                        print(f"  ✅ Filled email in input[{i}]")
                    elif "user" in inp_name.lower() or "user" in inp_id.lower():
                        inp.fill(username)
                        print(f"  ✅ Filled username in input[{i}]")
                    else:
                        # Fill first text field with email (Puter uses email for signup)
                        inp.fill(self.email)
                        print(f"  ✅ Filled email in input[{i}]")

            time.sleep(1)

            # Check for captcha — if present, we can't solve it without 2captcha
            captcha_el = page.locator("#phl-captcha-answer, [name='captcha_answer'], .captcha").first
            try:
                if captcha_el.is_visible(timeout=1000):
                    print("  ⚠️  CAPTCHA detected — cannot solve without 2captcha integration")
                    print("  💡 Puter may show captcha for suspicious IPs. Try with a proxy.")
                    self._debug_page("captcha")
                    return None
            except:
                pass  # No captcha, proceed

            # Submit
            for selector in [
                'button:has-text("Create")',
                'button:has-text("Sign Up")',
                'button:has-text("Continue")',
                'button:has-text("Get Started")',
                'button:has-text("Submit")',
                'button[type="submit"]',
                'input[type="submit"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f"  ✅ Clicked submit ({selector})")
                        break
                except:
                    continue

        except Exception as e:
            print(f"  ⚠️  Form fill error: {e}")
            self._debug_page("form_error")

        time.sleep(5)
        self._debug_page("after_submit")

        # Check if we're logged in (URL change or dashboard elements)
        page_text = page.inner_text("body")
        print(f"  📄 Page text snippet: {page_text[:200]}")

        # Check if email verification is needed
        if "verif" in page_text.lower() or "code" in page_text.lower() or "otp" in page_text.lower():
            print("  📧 Email verification needed — checking temp email...")
            msg = wait_for_email(self.email_token, timeout=60)
            if msg:
                content = msg.get("text", "") or str(msg.get("html", ""))
                otp = extract_otp_code(content)
                if otp:
                    print(f"  ✅ Got OTP: {otp}")
                    otp_input = page.locator("input").first
                    otp_input.fill(otp)
                    time.sleep(2)
                    page.keyboard.press("Enter")
                    time.sleep(3)

        # Extract auth token
        print("  🔑 Extracting auth token...")
        token = self._extract_token(page)
        if token:
            print(f"  ✅ Got token: {token[:30]}...")
            self.save_key(token, self.email, {"username": username, "password": password})
            return token

        # Try settings page
        print("  🔑 Trying settings page...")
        try:
            page.goto("https://puter.com/settings", timeout=15000)
            time.sleep(3)
            token = self._extract_token(page)
            if token:
                print(f"  ✅ Got token from settings: {token[:30]}...")
                self.save_key(token, self.email)
                return token
        except:
            pass

        self._debug_page("final")
        print("  ❌ Could not extract Puter auth token")
        return None

    def _debug_page(self, name: str):
        """Print page URL, title, and visible text for debugging."""
        if not self.page:
            return
        try:
            url = self.page.url
            title = self.page.title()
            text = self.page.inner_text("body")[:300].replace("\n", " ")
            print(f"  📍 [{name}] URL: {url}")
            print(f"  📍 [{name}] Title: {title}")
            print(f"  📍 [{name}] Text: {text}")
        except:
            pass

    def _extract_token(self, page) -> str | None:
        """Extract Puter auth token from the browser."""
        try:
            token = page.evaluate("""() => {
                // Direct globals
                if (window.auth_token) return window.auth_token;
                if (window.puter && window.puter.authToken) return window.puter.authToken;

                // localStorage scan
                const keys = [
                    'auth_token',
                    'puter.auth.token',
                    'puter.authToken',
                    'token',
                ];
                for (const key of keys) {
                    const val = localStorage.getItem(key);
                    if (val && val.length > 20) return val;
                }

                // Scan all localStorage for JWT-like values
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const val = localStorage.getItem(key);
                    if (!val) continue;
                    // JWT or long token
                    if (val.startsWith('eyJ') && val.length > 50) return val;
                    // Try parsing as JSON
                    try {
                        const parsed = JSON.parse(val);
                        if (parsed && typeof parsed === 'object') {
                            if (parsed.token) return parsed.token;
                            if (parsed.auth_token) return parsed.auth_token;
                            if (parsed.authToken) return parsed.authToken;
                        }
                    } catch(e) {}
                }
                return null;
            }""")
            return token
        except Exception as e:
            print(f"  ⚠️  Token extraction error: {e}")
            return None


if __name__ == "__main__":
    with PuterFarmer(headless=False) as farmer:
        key = farmer.farm()
        if key:
            print(f"\n✅ Success! Puter token: {key[:30]}...")
        else:
            print("\n❌ Failed to farm Puter account")
