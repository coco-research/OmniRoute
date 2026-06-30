"""
Coco Router Key Farm — Temp Email Helper
Uses mail.tm free API for disposable email addresses.
No signup, no API key needed. Emails are received and parsed for verification links.
"""

import re
import ssl
import time
import json
import urllib.request
import urllib.error
import certifi
from typing import Optional

MAIL_TM_API = "https://api.mail.tm"

def _create_ssl_context():
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(certifi.where())
    return ctx

_SSL_CONTEXT = _create_ssl_context()


def _request(method, path, token=None, body=None):
    url = f"{MAIL_TM_API}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": f"HTTP {e.code}", "body": body[:200]}
    except Exception as e:
        return {"error": str(e)}


def _get_domains():
    result = _request("GET", "/domains")
    if "hydra:member" in result:
        return [d["domain"] for d in result["hydra:member"]]
    if isinstance(result, list):
        return [d["domain"] for d in result]
    return ["mail.tm"]


def create_email() -> dict:
    """Create a new temp email account. Returns {email, password, token}."""
    domains = _get_domains()
    if not domains:
        return {"error": "No mail domains available"}

    domain = domains[0]
    import secrets
    import string

    username = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    email = f"{username}@{domain}"
    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    result = _request("POST", "/accounts", body={"address": email, "password": password})
    if "error" in result:
        return result

    token_result = _request("POST", "/token", body={"address": email, "password": password})
    if "error" in token_result:
        return token_result

    return {
        "email": email,
        "password": password,
        "token": token_result.get("token", ""),
    }


def get_messages(token: str) -> list:
    """Get list of messages in the inbox."""
    result = _request("GET", "/messages", token=token)
    if "hydra:member" in result:
        return result["hydra:member"]
    if isinstance(result, list):
        return result
    return []


def get_message(token: str, message_id: str) -> dict:
    """Get full message content."""
    return _request("GET", f"/messages/{message_id}", token=token)


def wait_for_email(token: str, timeout: int = 120, subject_filter: str = None) -> Optional[dict]:
    """Poll inbox until an email arrives. Returns the message or None on timeout."""
    start = time.time()
    while time.time() - start < timeout:
        messages = get_messages(token)
        for msg in messages:
            if subject_filter and subject_filter.lower() not in msg.get("subject", "").lower():
                continue
            full_msg = get_message(token, msg["id"])
            return full_msg
        time.sleep(3)
    return None


def extract_verification_link(html: str) -> Optional[str]:
    """Extract verification link from email HTML."""
    patterns = [
        r'href="(https?://[^"]*verify[^"]*)"',
        r'href="(https?://[^"]*confirm[^"]*)"',
        r'href="(https?://[^"]*activate[^"]*)"',
        r'href="(https?://[^"]*token[^"]*)"',
        r'href="(https?://[^"]*click[^"]*)"',
        r'href="(https?://[^"]*magic[^"]*)"',
        r'href="(https?://[^"]*redirect[^"]*)"',
        r'href="(https?://[^"]*login[^"]*)"',
        r'(https?://[^\s"<>]*magic_link[^\s"<>]*)',
        r'(https?://stytch\.com[^\s"<>]*)',
        r'(https?://[^\s"<>]*log[^\s"<>]*in[^\s"<>]*)',
        r'(https?://[^\s"<>]*auth[^\s"<>]*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    # Fallback: find any https URL that looks like a verification link
    all_urls = re.findall(r'(https?://[^\s"<>]+)', html)
    for url in all_urls:
        if any(kw in url.lower() for kw in ['magic', 'verify', 'confirm', 'auth', 'token', 'redirect', 'login', 'stytch']):
            return url
    # Last resort: return the longest URL (often the magic link)
    if all_urls:
        return max(all_urls, key=len)
    return None


def extract_otp_code(text: str, length: int = 6) -> Optional[str]:
    """Extract OTP/verification code from email text."""
    patterns = [
        rf'\b(\d{{{length}}})\b',
        r'(?:code|otp|pin)\s*[:\-]?\s*(\d{4,8})',
        r'>(\d{4,8})<',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


if __name__ == "__main__":
    print("Creating temp email...")
    account = create_email()
    if "error" in account:
        print(f"Error: {account}")
    else:
        print(f"Email: {account['email']}")
        print(f"Password: {account['password']}")
        print(f"Token: {account['token'][:30]}...")
        print(f"\nInbox is ready. Waiting for emails...")
