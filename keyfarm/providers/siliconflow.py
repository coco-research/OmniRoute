"""
Coco Router Key Farm — SiliconFlow Provider
SiliconFlow (siliconflow.cn) offers a free tier with 10 models (Qwen, DeepSeek, GLM, Llama)
at uncapped free usage. API keys are prefixed with `sk-`.
Signup: email + password (may require phone verification on Chinese sites).
Flow: navigate to console → register → email verification → create API key.
"""

import re
import time
from keyfarm.base import ProviderFarmer
from keyfarm.utils.temp_email import (
    create_email,
    wait_for_email,
    extract_verification_link,
    extract_otp_code,
)


SILICONFLOW_HOME = "https://siliconflow.cn"
SILICONFLOW_CONSOLE = "https://cloud.siliconflow.cn"
SILICONFLOW_KEYS_PAGE = "https://cloud.siliconflow.cn/account/ak"


class SiliconFlowFarmer(ProviderFarmer):
    def __init__(self, headless=False):
        super().__init__("siliconflow", headless=headless)

    def farm(self) -> str | None:
        print("\n  🚜 Farming SiliconFlow account...")

        # Step 1: Create temp email
        email_account = create_email()
        if "error" in email_account:
            print(f"  ❌ Temp email failed: {email_account}")
            return None
        self.email = email_account["email"]
        self.email_token = email_account["token"]
        print(f"  📧 Email: {self.email}")

        page = self.new_page()

        # Step 2: Open Camoufox, go to SiliconFlow console
        print(f"  🌐 Navigating to {SILICONFLOW_CONSOLE}...")
        try:
            page.goto(SILICONFLOW_CONSOLE, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  ⚠️  Console URL failed ({e}), trying home page...")
            try:
                page.goto(SILICONFLOW_HOME, timeout=30000, wait_until="domcontentloaded")
            except Exception as e2:
                print(f"  ❌ Could not open SiliconFlow: {e2}")
                return None
        time.sleep(3)
        self._debug_page("landing")

        # Step 3: Look for signup/register link
        print("  🔍 Looking for signup/register link...")
        clicked_signup = False
        for label in [
            "Sign Up",
            "Sign up",
            "Register",
            "注册",
            "Create account",
            "Create Account",
            "Get Started",
            "Free Sign Up",
        ]:
            try:
                el = page.get_by_text(label, exact=False).first
                if el.is_visible(timeout=1500):
                    el.click()
                    print(f"  ✅ Clicked signup link: '{label}'")
                    clicked_signup = True
                    break
            except Exception:
                continue

        # Try anchor-based selectors as a fallback
        if not clicked_signup:
            for selector in [
                'a[href*="register"]',
                'a[href*="signup"]',
                'a[href*="sign-up"]',
                'a[href*="account/register"]',
                'button:has-text("注册")',
                'button:has-text("Sign Up")',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f"  ✅ Clicked signup selector: {selector}")
                        clicked_signup = True
                        break
                except Exception:
                    continue

        if not clicked_signup:
            print("  ⚠️  No signup link found — maybe already on the register page")
            self._debug_page("no_signup_link")

        time.sleep(3)
        self._debug_page("signup_form")

        # Step 4: Detect captcha early (Chinese sites often use slider/click captcha)
        if self._detect_captcha(page):
            print("  ⚠️  CAPTCHA detected — cannot solve without a captcha service")
            print("  💡 SiliconFlow may require captcha for suspicious traffic. Try a proxy.")
            self.screenshot("captcha_detected")
            return None

        # Step 5: Fill form (email + password)
        print("  📝 Filling signup form...")
        import secrets
        import string

        password = (
            "Co"
            + "".join(secrets.choice(string.ascii_letters + string.digits + "!@#") for _ in range(14))
        )

        try:
            inputs = page.locator("input:visible").all()
            print(f"  📝 Found {len(inputs)} visible input fields")
            for i, inp in enumerate(inputs):
                inp_type = inp.get_attribute("type") or "text"
                inp_name = inp.get_attribute("name") or ""
                inp_id = inp.get_attribute("id") or ""
                inp_placeholder = inp.get_attribute("placeholder") or ""
                print(
                    f"    input[{i}] type={inp_type} name={inp_name} "
                    f"id={inp_id} placeholder={inp_placeholder}"
                )

                if "captcha" in inp_name.lower() or "captcha" in inp_id.lower():
                    print("    ⏭️  Skipping captcha field")
                    continue

                if inp_type == "password":
                    inp.fill(password)
                    print(f"  ✅ Filled password in input[{i}]")
                elif inp_type == "email" or "email" in (inp_name + inp_id + inp_placeholder).lower():
                    inp.fill(self.email)
                    print(f"  ✅ Filled email in input[{i}]")
                elif inp_type in ("text", "tel"):
                    # Skip phone fields — phone verification is a blocker
                    field_blob = (inp_name + inp_id + inp_placeholder).lower()
                    if "phone" in field_blob or "手机" in inp_placeholder:
                        print(f"    ⏭️  Skipping phone field input[{i}]")
                        continue
                    # Skip SMS / OTP / verification-code fields — they get filled later
                    if any(k in field_blob for k in ("code", "验证码", "otp", "sms")):
                        print(f"    ⏭️  Skipping code field input[{i}]")
                        continue
                    # Skip optional invite/referral fields
                    if any(k in field_blob for k in ("invite", "referral", "share", "邀请")):
                        print(f"    ⏭️  Skipping invite field input[{i}]")
                        continue
                    # Skip search inputs
                    if inp_type == "search":
                        continue
                    # Fill first generic text field with email if it looks like the email/username slot
                    if not any(
                        k in field_blob
                        for k in ("username", "user", "name")
                    ):
                        inp.fill(self.email)
                        print(f"  ✅ Filled email in input[{i}]")

            time.sleep(1)
        except Exception as e:
            print(f"  ❌ Form fill error: {e}")
            self._debug_page("form_error")
            self.screenshot("form_error")
            return None

        # Check for phone verification requirement before submitting
        page_text = page.inner_text("body")
        if any(kw in page_text.lower() for kw in ["phone", "手机号", "mobile", "短信", "sms"]):
            print("  ⚠️  Phone verification is required by SiliconFlow signup form")
            print("  ⚠️  Cannot complete without a Chinese phone number — aborting")
            self._debug_page("phone_required")
            self.screenshot("phone_required")
            return None

        # Submit
        print("  🚀 Submitting signup form...")
        submitted = False
        for selector in [
            'button:has-text("Sign Up")',
            'button:has-text("Sign up")',
            'button:has-text("Register")',
            'button:has-text("注册")',
            'button:has-text("Create")',
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
                    submitted = True
                    break
            except Exception:
                continue

        if not submitted:
            try:
                page.keyboard.press("Enter")
                print("  ✅ Pressed Enter to submit")
                submitted = True
            except Exception:
                pass

        if not submitted:
            print("  ❌ Could not submit signup form")
            self._debug_page("no_submit")
            self.screenshot("no_submit")
            return None

        time.sleep(5)
        self._debug_page("after_submit")

        # Re-check captcha after submit (slider captcha often appears post-submit)
        if self._detect_captcha(page):
            print("  ⚠️  CAPTCHA appeared after submit — cannot solve")
            self.screenshot("captcha_after_submit")
            return None

        # Step 6: Handle email verification
        page_text = page.inner_text("body")
        if any(
            kw in page_text.lower()
            for kw in ["verif", "code", "otp", "验证码", "邮箱", "email"]
        ):
            print("  📧 Email verification requested — checking temp email...")
            msg = wait_for_email(self.email_token, timeout=90)
            if not msg:
                print("  ❌ No verification email received within 90s")
                self._debug_page("no_verify_email")
                self.screenshot("no_verify_email")
                return None

            print(f"  ✅ Got email: {msg.get('subject', '')}")
            content = msg.get("text", "") or ""
            if not content:
                html = msg.get("html", "")
                if isinstance(html, list):
                    html = html[0] if html else ""
                content = html

            # Try OTP first (SiliconFlow likely sends a numeric code)
            otp = extract_otp_code(content)
            if otp:
                print(f"  ✅ Got OTP code: {otp}")
                otp_filled = False
                for sel in ['input[type="text"]', 'input[type="tel"]', 'input[inputmode="numeric"]', "input"]:
                    try:
                        otp_input = page.locator(sel).first
                        if otp_input.is_visible(timeout=1500):
                            otp_input.fill(otp)
                            otp_filled = True
                            print(f"  ✅ Filled OTP via {sel}")
                            break
                    except Exception:
                        continue
                if not otp_filled:
                    try:
                        page.keyboard.type(otp)
                        print("  ✅ Typed OTP via keyboard")
                        otp_filled = True
                    except Exception:
                        pass

                time.sleep(1)
                # Confirm OTP
                for selector in [
                    'button:has-text("Verify")',
                    'button:has-text("Confirm")',
                    'button:has-text("Continue")',
                    'button:has-text("Submit")',
                    'button[type="submit"]',
                ]:
                    try:
                        el = page.locator(selector).first
                        if el.is_visible(timeout=1000):
                            el.click()
                            print(f"  ✅ Confirmed OTP ({selector})")
                            break
                    except Exception:
                        continue
                time.sleep(3)
                self._debug_page("after_otp")
            else:
                # Fall back to magic link
                link = extract_verification_link(content)
                if link:
                    print(f"  ✅ Verification link: {link[:60]}...")
                    page.goto(link, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(3)
                    self._debug_page("after_verify_link")
                else:
                    print("  ❌ Could not find OTP or verification link in email")
                    print(f"     Content: {content[:300]}")
                    self.screenshot("no_otp_in_email")
                    return None

        # Re-check phone verification post-verify
        page_text = page.inner_text("body")
        if any(kw in page_text.lower() for kw in ["phone", "手机号", "mobile", "短信验证", "sms"]):
            print("  ⚠️  Phone verification required after email verification — aborting")
            self._debug_page("phone_required_post_verify")
            self.screenshot("phone_required_post_verify")
            return None

        # Step 7: Navigate to API keys page
        print(f"  🔑 Navigating to API keys page: {SILICONFLOW_KEYS_PAGE}...")
        try:
            page.goto(SILICONFLOW_KEYS_PAGE, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  ⚠️  Keys page nav failed ({e}), trying console root...")
            try:
                page.goto(SILICONFLOW_CONSOLE, timeout=30000, wait_until="domcontentloaded")
            except Exception as e2:
                print(f"  ❌ Could not reach console: {e2}")
                return None
        time.sleep(3)
        self._debug_page("keys_page")

        # Verify we are logged in
        url = page.url
        page_text = page.inner_text("body")[:400]
        if any(kw in page_text.lower() for kw in ["log in", "sign in", "登录", "login"]) and "ak" not in url.lower():
            print("  ❌ Not logged in — signup/verification may have failed")
            self.screenshot("not_logged_in")
            return None

        # Step 8: Create API key
        print("  🔑 Creating API key...")
        try:
            created = False
            for selector in [
                'button:has-text("新建 API 密钥")',
                'button:has-text("新建API")',
                'button:has-text("Create API Key")',
                'button:has-text("New API Key")',
                'button:has-text("Create Key")',
                'button:has-text("Generate")',
                'button:has-text("新建")',
                'button:has-text("添加")',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1500):
                        el.click()
                        print(f"  ✅ Clicked create-key ({selector})")
                        created = True
                        break
                except Exception:
                    continue

            if not created:
                print("  ❌ Could not find 'Create API key' button")
                self.screenshot("no_create_button")
                return None

            time.sleep(2)
            self._debug_page("create_key_form")

            # Optional: name the key
            try:
                name_input = page.locator('input[type="text"]').first
                if name_input.is_visible(timeout=1500):
                    name_input.fill("coco-router")
                    time.sleep(0.5)
            except Exception:
                pass

            # Confirm creation
            for selector in [
                'button:has-text("新建")',
                'button:has-text("Create")',
                'button:has-text("Confirm")',
                'button:has-text("Save")',
                'button:has-text("Submit")',
                'button:has-text("确定")',
                'button[type="submit"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f"  ✅ Confirmed key creation ({selector})")
                        break
                except Exception:
                    continue

            time.sleep(3)
            self._debug_page("key_created")
        except Exception as e:
            print(f"  ❌ API key creation failed: {e}")
            self.screenshot("key_creation_error")
            return None

        # Step 9: Extract the API key (look for sk- prefix)
        print("  🔍 Extracting API key...")
        api_key = None

        # Try input fields first
        try:
            inputs = page.locator("input").all()
            for inp in inputs:
                val = inp.get_attribute("value") or ""
                if val.startswith("sk-"):
                    api_key = val
                    break
        except Exception:
            pass

        # Try page text
        if not api_key:
            try:
                body_text = page.inner_text("body")
                match = re.search(r"(sk-[A-Za-z0-9]{20,})", body_text)
                if match:
                    api_key = match.group(1)
            except Exception:
                pass

        # Try clipboard (some UIs copy the key for you)
        if not api_key:
            try:
                clip = page.evaluate("() => navigator.clipboard.readText()")
                if isinstance(clip, str) and clip.startswith("sk-"):
                    api_key = clip
            except Exception:
                pass

        # Try clicking a "copy" button then re-reading clipboard
        if not api_key:
            for selector in [
                'button:has-text("Copy")',
                'button:has-text("复制")',
                '[aria-label="copy"]',
                '[aria-label="Copy"]',
            ]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        time.sleep(0.5)
                        clip = page.evaluate("() => navigator.clipboard.readText()")
                        if isinstance(clip, str) and clip.startswith("sk-"):
                            api_key = clip
                            break
                except Exception:
                    continue

        if api_key:
            print(f"  ✅ Got API key: {api_key[:20]}...")
            self.save_key(api_key, self.email)
            return api_key

        print("  ❌ Could not extract API key from page")
        self.screenshot("no_key_found")
        return None

    # ------------------------------------------------------------------ helpers

    def _debug_page(self, name: str):
        """Print URL, title, and visible text snippet for debugging."""
        if not self.page:
            return
        try:
            url = self.page.url
            title = self.page.title()
            text = self.page.inner_text("body")[:300].replace("\n", " ")
            print(f"  📍 [{name}] URL: {url}")
            print(f"  📍 [{name}] Title: {title}")
            print(f"  📍 [{name}] Text: {text}")
        except Exception:
            pass

    def _detect_captcha(self, page) -> bool:
        """Detect common captcha widgets (slider, click, image, hCaptcha, etc.)."""
        captcha_selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "iframe[title*='captcha' i]",
            ".captcha",
            "#captcha",
            "[class*='captcha' i]",
            "[id*='captcha' i]",
            "#nc_1_wrapper",  # Alibaba slider captcha
            ".nc_iconfont",
            "#tcaptcha_iframe",
            "div[class*='slider' i][class*='captcha' i]",
        ]
        for sel in captcha_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=400):
                    print(f"  🤖 Captcha element visible: {sel}")
                    return True
            except Exception:
                continue
        # Also scan page text for captcha prompts
        try:
            text = page.inner_text("body")[:500].lower()
            if "captcha" in text or "人机验证" in text or "滑动验证" in text:
                print("  🤖 Captcha keyword detected in page text")
                return True
        except Exception:
            pass
        return False


if __name__ == "__main__":
    with SiliconFlowFarmer(headless=False) as farmer:
        key = farmer.farm()
        if key:
            print(f"\n✅ Success! SiliconFlow API key: {key[:20]}...")
        else:
            print("\n❌ Failed to farm SiliconFlow account")
