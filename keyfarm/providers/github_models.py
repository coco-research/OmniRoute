"""
Coco Router Key Farm — GitHub Models Provider
GitHub Models offers 14 models (GPT-4o, Llama, Phi, Mistral) at 18M tok/day free.
Auth: GitHub Personal Access Token (PAT) — no browser signup needed.
API: https://models.inference.ai.azure.com (OpenAI-compatible).

Flow:
  1. Check env for GITHUB_TOKEN / GH_TOKEN
  2. Fall back to `gh auth token` CLI
  3. Validate PAT against https://models.inference.ai.azure.com/models
  4. Save and return the token
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from typing import Optional

from keyfarm.base import ProviderFarmer


GITHUB_MODELS_BASE = "https://models.inference.ai.azure.com"
GITHUB_MODELS_MODELS_URL = f"{GITHUB_MODELS_BASE}/models"
GITHUB_API_USER_URL = "https://api.github.com/user"


class GitHubModelsFarmer(ProviderFarmer):
    """PAT-based farmer for GitHub Models — no browser required."""

    def __init__(self, headless: bool = False):
        super().__init__("github-models", headless=headless)

    def farm(self) -> Optional[str]:
        print("\n  🚜 Farming GitHub Models account (PAT-based, no browser)...")

        token = self._discover_token()
        if not token:
            self._print_setup_instructions()
            return None

        print(f"  🔑 Found token: {token[:12]}...{token[-4:]}")

        if not self._validate_token(token):
            print("  ❌ Token is not valid for GitHub Models.")
            self._print_setup_instructions()
            return None

        github_user = self._fetch_github_user(token)
        account_email = github_user.get("email") or github_user.get("login") or ""

        self.save_key(token, account_email, {"github_user": github_user.get("login", "")})
        print(f"  ✅ GitHub Models token validated and saved.")
        return token

    def _discover_token(self) -> Optional[str]:
        """Look for a GitHub PAT in env vars, then fall back to `gh auth token`."""
        for env_var in ("GITHUB_TOKEN", "GH_TOKEN"):
            val = os.environ.get(env_var, "").strip()
            if val:
                print(f"  📥 Found token in ${env_var}")
                return val

        print("  🔍 No env token found — trying `gh auth token`...")
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            print("  ⚠️  `gh` CLI is not installed.")
            return None
        except subprocess.TimeoutExpired:
            print("  ⚠️  `gh auth token` timed out.")
            return None
        except Exception as e:
            print(f"  ⚠️  `gh auth token` failed: {e}")
            return None

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            print(f"  ⚠️  `gh auth token` exited {result.returncode}: {stderr}")
            return None

        token = result.stdout.strip()
        if not token:
            print("  ⚠️  `gh auth token` returned an empty value.")
            return None

        print("  ✅ Got token from `gh` CLI.")
        return token

    def _validate_token(self, token: str) -> bool:
        """Validate the PAT against the GitHub Models /models endpoint."""
        print(f"  🧪 Validating token against {GITHUB_MODELS_MODELS_URL} ...")

        status, body = self._http_get(GITHUB_MODELS_MODELS_URL, token)
        if status is None:
            # urllib failed (e.g. macOS SSL trust issues) — fall back to curl
            print("  ↻ urllib failed, retrying validation via curl...")
            status, body = self._curl_get(GITHUB_MODELS_MODELS_URL, token)

        if status is None or status != 200:
            print(f"  ❌ Validation failed: HTTP {status}")
            if body:
                print(f"     Response: {body[:300]}")
            return False

        model_count = self._count_models(body)
        print(f"  ✅ Token valid — {model_count} models available.")
        return True

    @staticmethod
    def _http_get(url: str, token: str):
        """GET via urllib. Returns (status, body) or (None, None) on error."""
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "coco-keyfarm-github-models",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            print(f"  ⚠️  HTTP error: {e.code} {e.reason}")
            return e.code, body
        except urllib.error.URLError as e:
            print(f"  ⚠️  Network error: {e.reason}")
            return None, None
        except Exception as e:
            print(f"  ⚠️  Request error: {e}")
            return None, None

    @staticmethod
    def _curl_get(url: str, token: str):
        """GET via curl (fallback for systems where Python's CA bundle is incomplete)."""
        try:
            result = subprocess.run(
                [
                    "curl", "-sS",
                    "--max-time", "20",
                    "-w", "\n%{http_code}",
                    "-H", f"Authorization: Bearer {token}",
                    "-H", "Accept: application/json",
                    "-H", "User-Agent: coco-keyfarm-github-models",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
        except FileNotFoundError:
            print("  ⚠️  curl is not available.")
            return None, None
        except subprocess.TimeoutExpired:
            print("  ⚠️  curl timed out.")
            return None, None
        except Exception as e:
            print(f"  ⚠️  curl failed: {e}")
            return None, None

        if result.returncode != 0:
            print(f"  ⚠️  curl exit {result.returncode}: {result.stderr.strip()}")
            return None, None

        text = result.stdout
        if "\n" not in text:
            return None, text
        body, _, status_str = text.rpartition("\n")
        try:
            status = int(status_str.strip())
        except ValueError:
            return None, text
        return status, body

    @staticmethod
    def _count_models(body: str) -> int:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return 0
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return len(data["data"])
        if isinstance(data, list):
            return len(data)
        return 0

    def _fetch_github_user(self, token: str) -> dict:
        """Best-effort fetch of the GitHub user identity behind the PAT."""
        status, body = self._http_get(GITHUB_API_USER_URL, token)
        if status is None:
            status, body = self._curl_get(GITHUB_API_USER_URL, token)
        if status == 200 and body:
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _print_setup_instructions():
        print()
        print("  ─────────────────────────────────────────────────────────")
        print("  💡 No usable GitHub token was found. Get a PAT manually:")
        print()
        print("     1. Open:  https://github.com/settings/tokens/new")
        print("     2. Scope: read:user   (also works: no scope for public read)")
        print("     3. Copy  the generated token (ghp_... or github_pat_...)")
        print("     4. Export it before re-running:")
        print()
        print("          export GITHUB_TOKEN='ghp_xxxxxxxxxxxx'")
        print()
        print("     — or log in with the GitHub CLI:")
        print()
        print("          gh auth login")
        print()
        print("  ─────────────────────────────────────────────────────────")


if __name__ == "__main__":
    farmer = GitHubModelsFarmer()
    key = farmer.farm()
    if key:
        print(f"\n✅ Success! GitHub Models token: {key[:12]}...{key[-4:]}")
    else:
        print("\n❌ Failed to obtain a GitHub Models token.")
