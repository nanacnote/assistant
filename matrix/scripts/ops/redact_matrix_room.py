#!/usr/bin/env python3
"""Operator utility — redact Matrix room messages. See matrix/scripts/ops/README.md."""

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
class MatrixRoomCleanupSettings:
    homeserver_url: str
    access_token: str
    room_id: str
    admin_localpart: str = ""
    user_agent: str = "assistant-room-cleanup/0.1.0"
    request_timeout_seconds: float = 30.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Redact all Matrix messages in a room using the account access token.",
        epilog=(
            "Dry-run first:\n"
            "  python matrix/scripts/ops/redact_matrix_room.py --room-id '!<id>:<domain>'\n"
            "Then confirm:\n"
            "  python matrix/scripts/ops/redact_matrix_room.py --room-id '!<id>:<domain>' --confirm"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--room-id", default=os.getenv("ASSISTANT_MATRIX_ROOM_ID", ""))
    parser.add_argument("--confirm", action="store_true", help="Actually perform redactions")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=0, help="0 means no limit")
    return parser


def load_settings(room_id: str, timeout_seconds: float) -> MatrixRoomCleanupSettings:
    homeserver_url = os.getenv("MATRIX_PUBLIC_BASEURL", "").strip() or f"https://{os.getenv('MATRIX_DOMAIN', '').strip()}"
    matrix_domain = os.getenv("MATRIX_DOMAIN", "").strip()
    assistant_password = os.getenv("MATRIX_ASSISTANT_PASSWORD", "").strip()
    if not homeserver_url:
        raise SystemExit("Missing MATRIX_PUBLIC_BASEURL or MATRIX_DOMAIN in matrix/.env")
    if not assistant_password:
        raise SystemExit("Missing MATRIX_ASSISTANT_PASSWORD in matrix/.env")
    if not room_id:
        raise SystemExit("Missing room id. Pass --room-id")

    assistant_localpart = os.getenv("MATRIX_ASSISTANT_LOCALPART", "assistant").strip()
    assistant_user_id = f"@{assistant_localpart}:{matrix_domain}"

    client = JsonHttpClient(
        timeout_seconds=timeout_seconds,
        user_agent="assistant-room-cleanup/0.1.0",
    )
    response = client.request_json(
        "POST",
        f"{homeserver_url.rstrip('/')}/_matrix/client/v3/login",
        payload={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": assistant_user_id},
            "password": assistant_password,
            "device_id": "assistant_room_cleanup",
            "initial_device_display_name": "assistant room cleanup ops",
        },
    )
    access_token = str(response.get("access_token", "")).strip()
    if not access_token:
        raise SystemExit("Assistant login succeeded but no access token was returned")

    return MatrixRoomCleanupSettings(
        homeserver_url=homeserver_url,
        access_token=access_token,
        room_id=room_id,
        admin_localpart=f"@admin:{matrix_domain}" if matrix_domain else "",
    )


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings(args.room_id, 30.0)
    http = JsonHttpClient(
        timeout_seconds=settings.request_timeout_seconds,
        user_agent=settings.user_agent,
    )

    room_id = settings.room_id
    print(f"room: {room_id}")
    print(f"mode: {'redact' if args.confirm else 'dry-run'}")

    sync_token = None
    page_count = 0
    redacted = 0
    total = 0

    while True:
        if args.max_pages and page_count >= args.max_pages:
            break

        params = [f"limit={args.batch_size}"]
        if sync_token:
            params.append(f"from={quote(sync_token, safe='')}")
        params.append("dir=b")
        params.append("recurse=false")
        params.append("org.matrix.msc2716.batch_token=")
        url = (
            f"{settings.homeserver_url.rstrip('/')}"
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/messages?{'&'.join(params)}"
        )
        response = http.request_json(
            "GET",
            url,
            headers={"Authorization": f"Bearer {settings.access_token}"},
        )
        time.sleep(REQUEST_DELAY)

        chunk = response.get("chunk", [])
        if not chunk:
            break

        page_count += 1
        sync_token = response.get("end", sync_token)

        message_events = [
            event
            for event in chunk
            if event.get("type") == "m.room.message"
            and (
                not settings.admin_localpart
                or event.get("sender") != settings.admin_localpart
            )
        ]
        total += len(message_events)
        print(f"page {page_count}: {len(message_events)} message events")

        if not args.confirm:
            continue

        for event in message_events:
            event_id = event.get("event_id")
            if not event_id:
                continue
            redact_url = (
                f"{settings.homeserver_url.rstrip('/')}"
                f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/redact/"
                f"{quote(event_id, safe='')}"
                f"/{int(time.time() * 1000)}"
            )
            http.request_json(
                "PUT",
                redact_url,
                headers={"Authorization": f"Bearer {settings.access_token}"},
                payload={"reason": "room cleanup"},
            )
            time.sleep(REQUEST_DELAY)
            redacted += 1

    print(f"messages_seen: {total}")
    print(f"messages_redacted: {redacted}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HttpRequestError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
