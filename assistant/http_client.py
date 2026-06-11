"""Minimal JSON HTTP client shared by assistant integrations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib import error, request

logger = logging.getLogger(__name__)


class HttpRequestError(RuntimeError):
    """Raised when an HTTP request fails."""


@dataclass(slots=True)
class JsonHttpClient:
    """Send JSON requests with stdlib-only dependencies."""

    timeout_seconds: float
    user_agent: str = "assistant/0.1.0"

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request and decode the JSON response body."""
        body = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)

        logger.debug("HTTP %s %s", method.upper(), url)
        req = request.Request(url, data=body, headers=request_headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.warning("HTTP %s %s failed: %d %s", method.upper(), url, exc.code, exc.reason)
            raise HttpRequestError(
                f"HTTP {exc.code} {exc.reason} while calling {url}: {detail}"
            ) from exc
        except error.URLError as exc:
            logger.warning("HTTP %s %s network error: %s", method.upper(), url, exc.reason)
            raise HttpRequestError(f"Network error while calling {url}: {exc.reason}") from exc

        if not raw:
            return {}
        logger.debug("HTTP %s %s response: %d bytes", method.upper(), url, len(raw))
        return json.loads(raw)
