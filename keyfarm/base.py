"""
Coco Router Key Farm — Base Provider Module
Provides Camoufox browser session management + common signup helpers.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional
from camoufox.sync_api import Camoufox


KEYS_FILE = Path(__file__).parent / "harvested_keys.json"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"


class ProviderFarmer:
    """Base class for provider account farmers."""

    def __init__(self, provider_id: str, headless: bool = False):
        self.provider_id = provider_id
        self.headless = headless
        self.browser = None
        self.page = None
        self.email = None
        self.email_token = None
        self.api_key = None

    def __enter__(self):
        SCREENSHOTS_DIR.mkdir(exist_ok=True)
        self.browser = Camoufox(headless=self.headless)
        self._ctx = self.browser.__enter__()
        return self

    def __exit__(self, *args):
        if self.browser:
            self.browser.__exit__(*args)

    def new_page(self):
        self.page = self._ctx.new_page()
        return self.page

    def screenshot(self, name: str):
        if self.page:
            path = SCREENSHOTS_DIR / f"{self.provider_id}_{name}_{int(time.time())}.png"
            self.page.screenshot(path=str(path))
            print(f"  📸 Screenshot: {path}")
            return path
        return None

    def goto(self, url: str, wait: float = 2.0):
        self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(wait)

    def click(self, selector: str, wait: float = 1.0):
        self.page.click(selector)
        time.sleep(wait)

    def fill(self, selector: str, value: str, wait: float = 0.5):
        self.page.fill(selector, value)
        time.sleep(wait)

    def text(self, selector: str) -> str:
        return self.page.inner_text(selector)

    def wait_for_selector(self, selector: str, timeout: int = 10000):
        self.page.wait_for_selector(selector, timeout=timeout)

    def wait_for_url(self, url_fragment: str, timeout: int = 30000):
        start = time.time()
        while time.time() - start < timeout / 1000:
            if url_fragment in self.page.url:
                return True
            time.sleep(0.5)
        return False

    def save_key(self, api_key: str, account_email: str = "", extra: dict = None):
        self.api_key = api_key
        entry = {
            "provider": self.provider_id,
            "api_key": api_key,
            "email": account_email or self.email or "",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "extra": extra or {},
        }

        keys = []
        if KEYS_FILE.exists():
            keys = json.loads(KEYS_FILE.read_text())
        keys.append(entry)
        KEYS_FILE.write_text(json.dumps(keys, indent=2))
        print(f"  💾 Key saved: {api_key[:20]}... → {KEYS_FILE}")
        return entry

    def farm(self) -> Optional[str]:
        """Override in subclass. Returns API key or None."""
        raise NotImplementedError("Subclass must implement farm()")
