"""Matrix transport client for the assistant runtime."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urlencode
from uuid import uuid4

from assistant.config import MatrixSettings
from assistant.http_client import JsonHttpClient

logger = logging.getLogger(__name__)


class MatrixClient:
    """Poll Matrix events and send assistant replies."""

    def __init__(self, settings: MatrixSettings):
        self._settings = settings
        self._http = JsonHttpClient(timeout_seconds=settings.request_timeout_seconds)
        self._access_token = settings.access_token
        self._next_batch = settings.initial_sync_token or None
        self._user_id = settings.user_id

    async def start(self) -> None:
        """Authenticate and advance the sync position to the current head.

        When no initial_sync_token is configured, a fast priming sync (timeout=0)
        is performed so that sync_forever only receives messages sent after
        the assistant starts, not historical room messages.
        """
        if not self._access_token:
            await asyncio.to_thread(self._login)
        if not self._next_batch:
            await asyncio.to_thread(self._prime_sync_token)

    async def sync_forever(
        self,
        event_handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Poll Matrix forever and forward new message events."""
        while True:
            try:
                response = await asyncio.to_thread(self._sync_once)
                for event in self._iter_room_messages(response):
                    await event_handler(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("matrix sync failed")
                await asyncio.sleep(5)

    async def send_text(
        self,
        room_id: str,
        text: str,
        reply_to_event_id: str | None = None,
        thread_root_event_id: str | None = None,
    ) -> None:
        """Send a plain-text message to a Matrix room."""
        await asyncio.to_thread(
            self._send_text,
            room_id,
            text,
            reply_to_event_id,
            thread_root_event_id,
        )

    def _login(self) -> None:
        response = self._http.request_json(
            "POST",
            self._url("/_matrix/client/v3/login"),
            payload={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": self._settings.user_id},
                "password": self._settings.password,
                "device_id": self._settings.device_id,
                "initial_device_display_name": "assistant",
            },
        )
        self._access_token = str(response["access_token"])
        self._user_id = str(response.get("user_id", self._user_id))

    def _prime_sync_token(self) -> None:
        """Advance _next_batch to the current head without processing any events.

        Uses timeout=0 and a server-side filter that requests zero timeline
        events so the response payload is minimal — just enough for the server
        to return next_batch. This follows the Matrix spec pattern for a fast
        initial sync used by production clients to skip historical messages.
        """
        # filter={"room":{"timeline":{"limit":0}}} keeps the response tiny.
        # The Matrix spec accepts a literal JSON object as the filter query
        # parameter in addition to a stored filter id.
        filter_param = json.dumps({"room": {"timeline": {"limit": 0}}}, separators=(",", ":"))
        params = {"timeout": "0", "filter": filter_param}
        prime_http = JsonHttpClient(timeout_seconds=self._settings.request_timeout_seconds)
        response = prime_http.request_json(
            "GET",
            f"{self._url('/_matrix/client/v3/sync')}?{urlencode(params)}",
            headers=self._auth_headers(),
        )
        self._next_batch = response.get("next_batch", self._next_batch)
        logger.debug("primed sync token to %s", self._next_batch)

    def _sync_once(self) -> dict[str, Any]:
        params = {"timeout": str(self._settings.sync_timeout_ms)}
        if self._next_batch:
            params["since"] = self._next_batch
        sync_timeout_seconds = max(
            self._settings.request_timeout_seconds,
            (self._settings.sync_timeout_ms / 1000.0) + 5.0,
        )
        sync_http = JsonHttpClient(timeout_seconds=sync_timeout_seconds)
        response = sync_http.request_json(
            "GET",
            f"{self._url('/_matrix/client/v3/sync')}?{urlencode(params)}",
            headers=self._auth_headers(),
        )
        self._next_batch = response.get("next_batch", self._next_batch)
        return response

    def _send_text(
        self,
        room_id: str,
        text: str,
        reply_to_event_id: str | None = None,
        thread_root_event_id: str | None = None,
    ) -> None:
        txn_id = uuid4().hex
        payload = self._build_text_payload(text, reply_to_event_id, thread_root_event_id)
        self._http.request_json(
            "PUT",
            self._url(
                f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/send/m.room.message/{txn_id}"
            ),
            headers=self._auth_headers(),
            payload=payload,
        )

    def _build_text_payload(
        self,
        text: str,
        reply_to_event_id: str | None,
        thread_root_event_id: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"msgtype": "m.text", "body": text}

        if thread_root_event_id:
            payload["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": thread_root_event_id,
                "is_falling_back": True,
                "m.in_reply_to": {
                    "event_id": reply_to_event_id or thread_root_event_id,
                },
            }
            return payload

        if reply_to_event_id:
            payload["m.relates_to"] = {
                "m.in_reply_to": {
                    "event_id": reply_to_event_id,
                }
            }

        return payload

    def _iter_room_messages(self, sync_response: dict[str, Any]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        joined_rooms = sync_response.get("rooms", {}).get("join", {})
        for room_id, room_data in joined_rooms.items():
            events = room_data.get("timeline", {}).get("events", [])
            for event in events:
                if event.get("type") != "m.room.message":
                    continue
                if event.get("sender") == self._user_id:
                    continue
                body = str(event.get("content", {}).get("body", "")).strip()
                if not body:
                    continue
                messages.append({**event, "room_id": room_id})
        return messages

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _url(self, path: str) -> str:
        return f"{self._settings.homeserver_url.rstrip('/')}{path}"
