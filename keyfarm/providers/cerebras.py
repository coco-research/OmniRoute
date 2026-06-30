"""
Coco Router Key Farm — Cerebras Provider
Cerebras offers 2 models (Llama 3.3 70B, Llama 4) at 30M tok/day free.
Signup: https://cloud.cerebras.ai — email signup (magic link or OTP, may have captcha).
API keys are prefixed with `csk-`.
Flow: enter email → receive verification (magic link or OTP) → verify → create API key.
"""

import re
import time
from keyfarm.base import ProviderFarmer
from keyfarm.utils.temp_email import create_email, wait_for_email, extract_verification_link, extract_otp_code


class CerebrasFarmer(ProviderFarmer):
    def __init__(self, headless=False):
        super().__init__("cerebras", headless=headless)

    def _detect_captcha(self, page) -> bool:
        """Check for common captcha providers on the page."""
        try:
            html = page.content()
        except Exception:
            return False
        captcha_markers = [
            "cf-turnstile",
            "g-recaptcha",
            "h-captcha",
            "arkoselabs",
            "funcaptcha",
            "recaptcha/api",
            "challenges.cloudflare.com",
        ]
        for marker in captcha_markers:
            if marker in html.lower():
                print(f"  ⚠️ Captcha detected: {marker}")
                return True
        return False

    def farm(self) -> str | None:
        print("\n  🚜 Farming Cerebras account...")

        # Step 1: Create temp email
        email_account = create_email()
        if "error" in email_account:
            print(f"  ❌ Temp email failed: {email_account}")
            return None
        self.email = email_account["email"]
        self.email_token = email_account["token"]
        print(f"  📧 Email: {self.email}")

        page = self.new_page()

        # Step 2: Navigate to Cerebras cloud
        print("  🌐 Navigating to cloud.cerebras.ai...")
        page.goto("https://cloud.cerebras.ai", timeout=30000, wait_until="domcontentloaded")
        time.sleep(3)

        url = page.url
        title = page.title()
        try:
            text_snippet = page.inner_text("body")[:400]
        except Exception:
            text_snippet = ""
        print(f"  📍 URL: {url}")
        print(f"  📍 Title: {title}")
        print(f"  📍 Page text: {text_snippet}")

        # Detect captcha early
        if self._detect_captcha(page):
            print("  ⚠️ Captcha detected on landing page — cannot proceed autonomously")
            self.screenshot("captcha_detected")
            return None

        # Step 3: Debug input fields
        print("  🔍 Scanning input fields...")
        try:
            inputs = page.locator("input").all()
            for i, inp in enumerate(inputs):
                try:
                    attrs = {
                        "type": inp.get_attribute("type"),
                        "name": inp.get_attribute("name"),
                        "id": inp.get_attribute("id"),
                        "placeholder": inp.get_attribute("placeholder"),
                    }
                    print(f"     input[{i}]: {attrs}")
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Could not scan inputs: {e}")

        # Step 4: Fill signup form (email)
        print("  📝 Entering email...")
        try:
            email_input = None
            for sel in ['input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]', 'input[placeholder*="email" i]']:
                try:
                    cand = page.locator(sel).first
                    if cand.is_visible(timeout=1500):
                        email_input = cand
                        break
                except Exception:
                    continue

            if not email_input:
                # Fallback: first text input
                email_input = page.locator('input[type="text"], input:not([type])').first

            email_input.fill(self.email)
            time.sleep(1)
            print("  ✅ Filled email field")

            # Click continue/signup button
            clicked = False
            for selector in [
                'button:has-text("Continue with email")',
                'button:has-text("Continue")',
                'button:has-text("Sign up")',
                'button:has-text("Sign Up")',
                'button:has-text("Sign in")',
                'button:has-text("Get started")',
                'button:has-text("Register")',
                'button[type="submit"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1500):
                        el.click()
                        print(f"  ✅ Clicked '{selector}'")
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                # Try pressing Enter
                email_input.press("Enter")
                print("  ✅ Pressed Enter on email field")

        except Exception as e:
            print(f"  ❌ Email submit failed: {e}")
            self.screenshot("email_submit_failed")
            return None

        time.sleep(3)

        # Re-check for captcha after submit
        if self._detect_captcha(page):
            print("  ⚠️ Captcha detected after email submit — cannot proceed autonomously")
            self.screenshot("captcha_after_submit")
            return None

        url = page.url
        try:
            text_snippet = page.inner_text("body")[:400]
        except Exception:
            text_snippet = ""
        print(f"  📍 After email submit — URL: {url}")
        print(f"  📍 After email submit — text: {text_snippet}")

        # Check if a password is required (some flows ask for password)
        try:
            pwd_input = page.locator('input[type="password"]').first
            if pwd_input.is_visible(timeout=2000):
                print("  🔒 Password field detected — filling password...")
                import secrets
                import string
                password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
                pwd_input.fill(password)
                time.sleep(0.5)
                # Confirm password if there's a second field
                pwd_inputs = page.locator('input[type="password"]').all()
                if len(pwd_inputs) > 1:
                    pwd_inputs[1].fill(password)
                    time.sleep(0.5)
                # Submit
                for selector in [
                    'button:has-text("Continue")',
                    'button:has-text("Sign up")',
                    'button:has-text("Sign Up")',
                    'button[type="submit"]',
                ]:
                    try:
                        el = page.locator(selector).first
                        if el.is_visible(timeout=1500):
                            el.click()
                            print(f"  ✅ Clicked '{selector}' after password")
                            break
                    except Exception:
                        continue
                time.sleep(3)
        except Exception:
            pass

        # Step 5: Wait for verification email (magic link or OTP)
        print("  📧 Waiting for verification email...")
        msg = wait_for_email(self.email_token, timeout=120)
        if not msg:
            print("  ❌ No verification email received within 120s")
            self.screenshot("no_verification_email")
            return None

        print(f"  ✅ Got email: {msg.get('subject', '')}")

        text = msg.get("text", "")
        html = msg.get("html", "")
        if isinstance(html, list):
            html = html[0] if html else ""
        content = text or html

        # Try OTP first, then magic link
        otp = extract_otp_code(content)
        link = extract_verification_link(content)

        if otp:
            print(f"  ✅ Found OTP code: {otp}")
            # Enter OTP into the page
            try:
                otp_inputs = page.locator('input[type="text"], input[type="tel"], input[inputmode="numeric"]').all()
                if otp_inputs:
                    # If single input, fill whole code
                    if len(otp_inputs) == 1:
                        otp_inputs[0].fill(otp)
                    else:
                        # Multiple inputs — one digit each
                        for i, digit in enumerate(otp):
                            if i < len(otp_inputs):
                                otp_inputs[i].fill(digit)
                                time.sleep(0.1)
                    time.sleep(1)

                    # Submit
                    for selector in [
                        'button:has-text("Verify")',
                        'button:has-text("Continue")',
                        'button:has-text("Submit")',
                        'button:has-text("Confirm")',
                        'button[type="submit"]',
                    ]:
                        try:
                            el = page.locator(selector).first
                            if el.is_visible(timeout=1500):
                                el.click()
                                print(f"  ✅ Clicked '{selector}' after OTP")
                                break
                        except Exception:
                            continue
                else:
                    print("  ⚠️ No OTP input fields found on page")
            except Exception as e:
                print(f"  ❌ OTP entry failed: {e}")
                self.screenshot("otp_entry_failed")

            time.sleep(3)

        elif link:
            print(f"  ✅ Found magic link: {link[:60]}...")
            # Visit magic link in the same browser (keeps session)
            print("  🔗 Clicking magic link...")
            page.goto(link, timeout=30000, wait_until="domcontentloaded")
            time.sleep(3)

            # Wait for redirect chain to settle
            current = page.url
            print(f"  📍 After magic link (3s): {current}")
            for _ in range(10):
                time.sleep(2)
                new_url = page.url
                if new_url != current:
                    print(f"  📍 Redirected to: {new_url}")
                    current = new_url
                elif "cerebras.ai" in current:
                    break
            time.sleep(2)

        else:
            print("  ❌ Could not find verification link or OTP in email")
            print(f"     Content: {content[:300]}")
            self.screenshot("no_verification_token")
            return None

        url = page.url
        try:
            text_snippet = page.inner_text("body")[:400]
        except Exception:
            text_snippet = ""
        print(f"  📍 After verification — URL: {url}")
        print(f"  📍 After verification — text: {text_snippet}")

        # Handle any consent / terms / onboarding steps
        try:
            for _ in range(3):
                clicked = False
                for selector in [
                    'button:has-text("Accept")',
                    'button:has-text("Agree")',
                    'button:has-text("Continue")',
                    'button:has-text("Got it")',
                    'button:has-text("Get Started")',
                    'button:has-text("OK")',
                    'button:has-text("Create")',
                ]:
                    try:
                        el = page.locator(selector).first
                        if el.is_visible(timeout=1000):
                            el.click()
                            print(f"  ✅ Clicked onboarding '{selector}'")
                            clicked = True
                            time.sleep(2)
                            break
                    except Exception:
                        continue
                if not clicked:
                    break
        except Exception:
            pass

        # Step 6: Navigate to API Keys page
        print("  🔑 Navigating to API Keys page...")
        page.goto("https://cloud.cerebras.ai/keys", timeout=30000, wait_until="domcontentloaded")
        time.sleep(3)

        url = page.url
        try:
            text_snippet = page.inner_text("body")[:400]
        except Exception:
            text_snippet = ""
        print(f"  📍 Keys page URL: {url}")
        print(f"  📍 Keys page text: {text_snippet}")

        # Check if we're actually logged in
        if "log in" in text_snippet.lower() or "login" in url.lower() or "sign in" in text_snippet.lower():
            print("  ❌ Not logged in — verification may have failed")
            self.screenshot("not_logged_in")
            return None

        # Step 7: Create API key
        print("  🔑 Creating API key...")
        try:
            # Click the create-key button
            for selector in [
                'button:has-text("Create API Key")',
                'button:has-text("Create Key")',
                'button:has-text("New Key")',
                'button:has-text("New API Key")',
                'button:has-text("Generate")',
                'button:has-text("Generate Key")',
                'button:has-text("Create")',
                'button:has-text("Add Key")',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=2000):
                        el.click()
                        print(f"  ✅ Clicked '{selector}'")
                        break
                except Exception:
                    continue

            time.sleep(2)

            # Name the key if a name field appears
            try:
                name_input = page.locator('input[type="text"]').first
                if name_input.is_visible(timeout=2000):
                    name_input.fill("coco-router")
                    time.sleep(0.5)
            except Exception:
                pass

            # Confirm creation
            for selector in [
                'button:has-text("Create")',
                'button:has-text("Confirm")',
                'button:has-text("Save")',
                'button:has-text("Submit")',
                'button:has-text("Generate")',
                'button[type="submit"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1500):
                        el.click()
                        print(f"  ✅ Confirmed key creation")
                        break
                except Exception:
                    continue

            time.sleep(3)

            # Step 8: Extract the API key
            print("  🔍 Extracting API key...")
            try:
                text_snippet = page.inner_text("body")
            except Exception:
                text_snippet = ""
            print(f"  📍 Page text: {text_snippet[:500]}")

            api_key = None

            # Try input fields first
            try:
                inputs = page.locator("input").all()
                for inp in inputs:
                    val = inp.get_attribute("value") or ""
                    if val.startswith("csk-") or val.startswith("csk_"):
                        api_key = val
                        break
            except Exception:
                pass

            # Try page text
            if not api_key:
                match = re.search(r'(csk[-_][A-Za-z0-9]{20,})', text_snippet)
                if match:
                    api_key = match.group(1)

            # Try clipboard
            if not api_key:
                try:
                    clip = page.evaluate("() => navigator.clipboard.readText()")
                    if clip and (clip.startswith("csk-") or clip.startswith("csk_")):
                        api_key = clip
                except Exception:
                    pass

            # Broader fallback: any long token-like string
            if not api_key:
                match = re.search(r'\b([A-Za-z0-9_-]{32,})\b', text_snippet)
                if match:
                    candidate = match.group(1)
                    print(f"  ℹ️ Found candidate key (no csk prefix): {candidate[:20]}...")
                    api_key = candidate

            if api_key:
                print(f"  ✅ Got API key: {api_key[:20]}...")
                self.save_key(api_key, self.email)
                return api_key
            else:
                print("  ❌ Could not extract API key from page")
                self.screenshot("no_key_found")

        except Exception as e:
            print(f"  ❌ API key creation failed: {e}")
            self.screenshot("key_creation_error")

        return None


if __name__ == "__main__":
    with CerebrasFarmer(headless=False) as farmer:
        key = farmer.farm()
        if key:
            print(f"\n✅ Success! Cerebras API key: {key[:20]}...")
        else:
            print("\n❌ Failed to farm Cerebras account")
