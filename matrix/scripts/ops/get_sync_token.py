#!/usr/bin/env python3
"""Print the current Matrix sync token for the assistant account.

The token represents the server's current stream position. Set it as
ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN in your .env when you want the assistant
to start from a specific point rather than letting the automatic priming sync
determine the position on startup (e.g. after restoring from backup).

Usage
-----
Print the token to stdout:

    python matrix/scripts/ops/get_sync_token.py

Write it directly into matrix/.env:

    python matrix/scripts/ops/get_sync_token.py --write-env
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path("matrix/.env"), override=False)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the current Matrix sync token for the assistant account "
            "and optionally write it to the env file."
        ),
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help=(
            "Write the token into ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN inside "
            "matrix/.env. Creates the key if absent, updates it if present."
        ),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification for HTTPS homeservers",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Env file helpers
# ---------------------------------------------------------------------------


def write_env_key(path: Path, key: str, value: str) -> None:
    """Set *key* to *value* in *path*, preserving all other content."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(rf"^({re.escape(key)}\s*=).*$", re.MULTILINE)
    replacement = f"{key}={value}"
    if pattern.search(text):
        updated = pattern.sub(replacement, text)
    else:
        # Key absent — append it
        updated = text.rstrip("\n") + f"\n{replacement}\n"
    path.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Matrix API
# ---------------------------------------------------------------------------


def _make_ssl_context(insecure: bool, url: str) -> ssl.SSLContext | None:
    if url.startswith("https://") and insecure:
        return ssl._create_unverified_context()
    return None


def _get(url: str, access_token: str, ssl_context: ssl.SSLContext | None) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(url=url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, context=ssl_context, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc}") from exc


def _login_password(
    base_url: str,
    user_id: str,
    password: str,
    ssl_context: ssl.SSLContext | None,
) -> str:
    url = f"{base_url.rstrip('/')}/_matrix/client/v3/login"
    payload = json.dumps({
        "type": "m.login.password",
        "identifier": {"type": "m.id.user", "user": user_id},
        "password": password,
        "device_id": "get_sync_token_script",
        "initial_device_display_name": "get_sync_token ops script",
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url=url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, context=ssl_context, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))["access_token"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Login failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Login failed: {exc}") from exc


def fetch_sync_token(
    base_url: str,
    access_token: str,
    insecure: bool,
) -> str:
    """Return the current next_batch token without processing any events.

    Uses timeout=0 and a minimal filter (zero timeline events) so the server
    responds immediately with a tiny payload — just the stream position.
    """
    ssl_context = _make_ssl_context(insecure, base_url)
    filter_param = json.dumps(
        {"room": {"timeline": {"limit": 0}}}, separators=(",", ":")
    )
    params = urllib.parse.urlencode({"timeout": "0", "filter": filter_param})
    url = f"{base_url.rstrip('/')}/_matrix/client/v3/sync?{params}"
    response = _get(url, access_token, ssl_context)
    token = response.get("next_batch")
    if not token:
        raise RuntimeError(
            f"Server response did not contain next_batch. Full response:\n"
            f"{json.dumps(response, indent=2)}"
        )
    return str(token)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()
    env_path = Path("matrix/.env")

    matrix_domain = os.getenv("MATRIX_DOMAIN", "").strip()
    base_url = (os.getenv("MATRIX_PUBLIC_BASEURL", "").strip() or f"https://{matrix_domain}").rstrip("/")
    if not base_url:
        print("ERROR: MATRIX_PUBLIC_BASEURL or MATRIX_DOMAIN is not set.", file=sys.stderr)
        sys.exit(1)

    assistant_localpart = os.getenv("MATRIX_ASSISTANT_LOCALPART", "assistant").strip()
    assistant_password = os.getenv("MATRIX_ASSISTANT_PASSWORD", "").strip()
    if not matrix_domain:
        print("ERROR: MATRIX_DOMAIN is not set.", file=sys.stderr)
        sys.exit(1)
    if not assistant_password:
        print("ERROR: MATRIX_ASSISTANT_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)

    ssl_context = _make_ssl_context(args.insecure, base_url)
    user_id = f"@{assistant_localpart}:{matrix_domain}"
    print(f"Logging in as {user_id}…", file=sys.stderr)
    try:
        access_token = _login_password(base_url, user_id, assistant_password, ssl_context)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        token = fetch_sync_token(base_url, access_token, args.insecure)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.write_env:
        write_env_key(env_path, "ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN", token)
        print(f"Wrote ASSISTANT_MATRIX_INITIAL_SYNC_TOKEN={token} to {env_path}")
    else:
        print(token)


if __name__ == "__main__":
    main()
