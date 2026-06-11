#!/usr/bin/env python3
"""Create a Matrix room and add named users (defaulting to admin + assistant)."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path("matrix/.env"), override=False)

REQUEST_DELAY = 0.2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Matrix room and add named users to it.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help=(
            "Matrix client base URL override (default: MATRIX_CLIENT_BASEURL "
            "or MATRIX_PUBLIC_BASEURL)"
        ),
    )
    parser.add_argument(
        "--room-name",
        default="Default",
        help="Name of the room to create",
    )
    parser.add_argument(
        "--topic",
        default="",
        help="Topic for the created room",
    )
    parser.add_argument(
        "--room-alias-localpart",
        default="default",
        help=(
            "Room alias localpart to create/reuse (default: default). "
            "Set to empty string to disable alias handling."
        ),
    )
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        help=(
            "Additional user localparts to invite to the room (may be repeated). "
            "Admin and assistant are always included."
        ),
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification for HTTPS homeservers",
    )
    return parser.parse_args()


class MatrixApi:
    def __init__(self, base_url: str, insecure: bool):
        self.base_url = base_url.rstrip("/")
        self.ssl_context: ssl.SSLContext | None = None
        if self.base_url.startswith("https://") and insecure:
            self.ssl_context = ssl._create_unverified_context()

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(url=url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, context=self.ssl_context, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc

        if not raw:
            return {}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected response from {method} {path}: {raw}")
        return data

    def login_password(self, user: str, password: str, device_name: str) -> tuple[str, str]:
        response = self.request_json(
            "POST",
            "/_matrix/client/v3/login",
            payload={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": user},
                "password": password,
                "initial_device_display_name": device_name,
            },
        )
        access_token = str(response.get("access_token", ""))
        user_id = str(response.get("user_id", ""))
        if not access_token or not user_id:
            raise RuntimeError("Login succeeded but token/user_id missing from response")
        return access_token, user_id


def _resolve_users(
    extra_localparts: list[str],
    matrix_server_name: str,
) -> list[tuple[str, str, str, str]]:
    """Return (user_id, access_token, password, label) for admin, assistant, and extras."""

    admin_localpart = os.getenv("MATRIX_ADMIN_LOCALPART", "admin").strip()
    assistant_localpart = os.getenv("MATRIX_ASSISTANT_LOCALPART", "assistant").strip()
    admin_password = os.getenv("MATRIX_ADMIN_PASSWORD", "").strip()
    assistant_password = os.getenv("MATRIX_ASSISTANT_PASSWORD", "").strip()
    if not admin_password:
        raise SystemExit("Missing MATRIX_ADMIN_PASSWORD in matrix/.env")
    if not assistant_password:
        raise SystemExit("Missing MATRIX_ASSISTANT_PASSWORD in matrix/.env")

    users: list[tuple[str, str, str, str]] = [
        (f"@{admin_localpart}:{matrix_server_name}", "", admin_password, "admin"),
        (f"@{assistant_localpart}:{matrix_server_name}", "", assistant_password, "assistant"),
    ]
    seen = {admin_localpart, assistant_localpart}

    for localpart in extra_localparts:
        if localpart in seen:
            continue
        pwd_key = f"MATRIX_USER_{localpart.upper()}_PASSWORD"
        password = os.getenv(pwd_key, "").strip()
        if not password:
            raise SystemExit(
                f"Password for '{localpart}' not found. "
                f"Set {pwd_key} in matrix/.env."
            )
        users.append((f"@{localpart}:{matrix_server_name}", "", password, localpart))
        seen.add(localpart)

    return users


def _room_create_payload(
    room_name: str,
    topic: str,
    invite_ids: list[str],
    room_alias_localpart: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "preset": "private_chat",
        "name": room_name,
        "topic": topic,
        "invite": invite_ids,
        "is_direct": False,
    }
    if room_alias_localpart:
        payload["room_alias_name"] = room_alias_localpart
    return payload


def _find_existing_room(
    api: MatrixApi,
    admin_token: str,
    room_alias: str,
) -> str:
    encoded_alias = urllib.parse.quote(room_alias, safe="")
    try:
        alias_lookup = api.request_json(
            "GET",
            f"/_matrix/client/v3/directory/room/{encoded_alias}",
            access_token=admin_token,
        )
        room_id = str(alias_lookup.get("room_id", ""))
        if room_id:
            print(f"Reusing existing aliased room: {room_alias} -> {room_id}")
        return room_id
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return ""
        raise


def _ensure_user_in_room(
    api: MatrixApi,
    room_id: str,
    user_id: str,
    admin_token: str,
    user_token: str,
) -> None:
    encoded_room_id = urllib.parse.quote(room_id, safe="")

    try:
        api.request_json(
            "POST",
            f"/_matrix/client/v3/rooms/{encoded_room_id}/invite",
            payload={"user_id": user_id},
            access_token=admin_token,
        )
    except RuntimeError as exc:
        message = str(exc)
        if "M_ALREADY_JOINED" not in message and "is already in the room" not in message:
            raise

    api.request_json(
        "POST",
        f"/_matrix/client/v3/join/{encoded_room_id}",
        payload={},
        access_token=user_token,
    )


def main() -> int:
    args = parse_args()

    matrix_domain = os.getenv("MATRIX_DOMAIN", "").strip()
    if not matrix_domain:
        print("Missing MATRIX_DOMAIN", file=sys.stderr)
        return 1

    matrix_server_name = os.getenv("MATRIX_SERVER_NAME", matrix_domain).strip()

    base_url = (
        args.base_url.strip()
        or os.getenv("MATRIX_CLIENT_BASEURL", "").strip()
        or os.getenv("MATRIX_PUBLIC_BASEURL", "").strip()
        or f"https://{matrix_domain}"
    )
    room_alias_localpart = args.room_alias_localpart.strip()
    room_alias = (
        f"#{room_alias_localpart}:{matrix_server_name}" if room_alias_localpart else ""
    )

    api = MatrixApi(base_url=base_url, insecure=args.insecure)

    users = _resolve_users(args.user, matrix_server_name)
    for user_id, _, _, label in users:
        print(f"User ({label}): {user_id}")

    tokens: dict[str, str] = {}
    for user_id, _, password, label in users:
        token, _ = api.login_password(user_id, password, f"ops-room-setup-{label}")
        tokens[user_id] = token
        time.sleep(REQUEST_DELAY)

    admin_id = users[0][0]
    admin_token = tokens[admin_id]

    room_id = ""
    if room_alias:
        room_id = _find_existing_room(api, admin_token, room_alias)

    if not room_id:
        invite_ids = [u[0] for u in users[1:]]
        create_payload = _room_create_payload(
            args.room_name, args.topic, invite_ids, room_alias_localpart,
        )
        create_response = api.request_json(
            "POST",
            "/_matrix/client/v3/createRoom",
            payload=create_payload,
            access_token=admin_token,
        )
        room_id = str(create_response.get("room_id", ""))

    if not room_id:
        raise RuntimeError("Room creation succeeded but room_id was not returned")

    # Admin is already in the room as creator; ensure everyone else joins.
    for user_id, _, _, label in users[1:]:
        print(f"Adding {label} ({user_id})...")
        _ensure_user_in_room(api, room_id, user_id, admin_token, tokens[user_id])
        time.sleep(REQUEST_DELAY)

    print(f"\nRoom created and {len(users)} user(s) joined.")
    print(f"Room ID: {room_id}")
    if room_alias:
        print(f"Room alias: {room_alias}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
