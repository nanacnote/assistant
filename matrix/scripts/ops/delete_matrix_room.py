#!/usr/bin/env python3
"""Operator utility — delete a Matrix room through Synapse admin APIs.

This tool performs a destructive room shutdown+purge operation and should be
used only by operators with admin credentials.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from urllib.parse import quote

from dotenv import load_dotenv

from assistant.http_client import HttpRequestError, JsonHttpClient

load_dotenv("matrix/.env", override=False)

REQUEST_DELAY = 0.2


@dataclass(slots=True)
class MatrixRoomDeleteSettings:
    homeserver_url: str
    access_token: str
    room_id: str
    request_timeout_seconds: float = 30.0
    user_agent: str = "assistant-room-delete/0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete a Matrix room using Synapse admin APIs. Dry-run is the default; "
            "pass --confirm to execute."
        ),
        epilog=(
            "Dry-run:\n"
            "  python matrix/scripts/ops/delete_matrix_room.py --room-id '!<id>:<domain>'\n"
            "Confirm:\n"
            "  python matrix/scripts/ops/delete_matrix_room.py --room-id '!<id>:<domain>' --confirm"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--room-id", default=os.getenv("ASSISTANT_MATRIX_ROOM_ID", ""))
    parser.add_argument("--confirm", action="store_true", help="Actually execute deletion")
    parser.add_argument(
        "--block",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Block future joins to the room alias/address after deletion",
    )
    parser.add_argument(
        "--purge",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Purge room history from Synapse storage",
    )
    parser.add_argument(
        "--force-purge",
        action="store_true",
        help="Force purge even when users are still joined",
    )
    parser.add_argument(
        "--reason",
        default="Room deleted by operator",
        help="Audit reason attached to delete request",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout for each API call",
    )
    return parser


def load_settings(room_id: str, timeout_seconds: float) -> MatrixRoomDeleteSettings:
    homeserver_url = os.getenv("MATRIX_PUBLIC_BASEURL", "").strip() or f"https://{os.getenv('MATRIX_DOMAIN', '').strip()}"
    if not room_id.strip():
        raise SystemExit("Missing room id. Pass --room-id")
    if not homeserver_url:
        raise SystemExit("Missing MATRIX_PUBLIC_BASEURL or MATRIX_DOMAIN in matrix/.env")

    admin_password = os.getenv("MATRIX_ADMIN_PASSWORD", "").strip()
    if not admin_password:
        raise SystemExit("Missing MATRIX_ADMIN_PASSWORD in matrix/.env")

    admin_localpart = os.getenv("MATRIX_ADMIN_LOCALPART", "admin").strip()
    matrix_domain = os.getenv("MATRIX_DOMAIN", "").strip()
    admin_user_id = _build_admin_user_id(admin_localpart, matrix_domain)

    client = JsonHttpClient(
        timeout_seconds=timeout_seconds,
        user_agent="assistant-room-delete/0.1.0",
    )
    response = client.request_json(
        "POST",
        f"{homeserver_url.rstrip('/')}/_matrix/client/v3/login",
        payload={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": admin_user_id},
            "password": admin_password,
            "device_id": "assistant_room_delete",
            "initial_device_display_name": "assistant room delete ops",
        },
    )
    access_token = str(response.get("access_token", "")).strip()
    if not access_token:
        raise SystemExit("Admin login succeeded but no access token was returned")

    return MatrixRoomDeleteSettings(
        homeserver_url=homeserver_url,
        access_token=access_token,
        room_id=room_id.strip(),
        request_timeout_seconds=timeout_seconds,
    )


def _build_admin_user_id(admin_localpart: str, matrix_domain: str) -> str:
    if admin_localpart.startswith("@"):
        return admin_localpart
    if not matrix_domain:
        raise SystemExit(
            "MATRIX_DOMAIN is required when MATRIX_ADMIN_LOCALPART is not a full user id"
        )
    return f"@{admin_localpart}:{matrix_domain}"


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def fetch_room_info(settings: MatrixRoomDeleteSettings, http: JsonHttpClient) -> dict[str, object]:
    room_id = quote(settings.room_id, safe="")
    return http.request_json(
        "GET",
        f"{settings.homeserver_url.rstrip('/')}/_synapse/admin/v1/rooms/{room_id}",
        headers=_auth_headers(settings.access_token),
    )


def delete_room(
    settings: MatrixRoomDeleteSettings,
    http: JsonHttpClient,
    *,
    block: bool,
    purge: bool,
    force_purge: bool,
    reason: str,
) -> dict[str, object]:
    room_id = quote(settings.room_id, safe="")
    url = f"{settings.homeserver_url.rstrip('/')}/_synapse/admin/v2/rooms/{room_id}"
    return http.request_json(
        "DELETE",
        url,
        headers=_auth_headers(settings.access_token),
        payload={
            "block": block,
            "purge": purge,
            "force_purge": force_purge,
            "message": reason,
        },
    )


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings(args.room_id, args.request_timeout_seconds)
    http = JsonHttpClient(
        timeout_seconds=settings.request_timeout_seconds,
        user_agent=settings.user_agent,
    )

    info = fetch_room_info(settings, http)
    print(f"room_id: {settings.room_id}")
    print(f"name: {info.get('name', '')}")
    print(f"joined_members: {info.get('joined_members', 0)}")
    print(f"mode: {'delete' if args.confirm else 'dry-run'}")
    print(f"block: {args.block}")
    print(f"purge: {args.purge}")
    print(f"force_purge: {args.force_purge}")

    if not args.confirm:
        return 0

    time.sleep(REQUEST_DELAY)
    response = delete_room(
        settings,
        http,
        block=args.block,
        purge=args.purge,
        force_purge=args.force_purge,
        reason=args.reason,
    )

    delete_id = str(response.get("delete_id", "")).strip()
    if delete_id:
        print(f"delete_id: {delete_id}")
    print("room_delete_requested: true")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HttpRequestError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
