"""Auth, request provenance, webhook signatures and rate limiting."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request, status

from .config import Settings, get_settings
from .models import Source

SIGNATURE_TOLERANCE_SECONDS = 300


def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    # Constant-time comparison avoids leaking the key through response timing.
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.crm_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


def request_source(x_source: str | None = Header(default=None)) -> Source:
    """Callers tag their origin (the voice agent sends `X-Source: voice`). Defaults to UI.

    Only already-authenticated callers reach this, and only ui/voice may be claimed;
    automation and webhook sources are reserved for server-side code paths.
    """
    if x_source == Source.VOICE:
        return Source.VOICE
    return Source.UI


def sign_payload(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


async def verify_signed_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> bytes:
    """Validate `X-Signature: sha256=HMAC(secret, "{timestamp}.{body}")`.

    The timestamp is bound into the signature and must be recent, which blocks replays.
    Returns the raw body so the handler parses exactly the bytes that were verified.
    """
    if not settings.inbound_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Inbound webhooks are not configured")
    if not x_signature or not x_timestamp or not x_timestamp.isdigit():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing signature headers")
    if abs(time.time() - int(x_timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Stale webhook timestamp")

    body = await request.body()
    expected = sign_payload(settings.inbound_webhook_secret, x_timestamp, body)
    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    return body


class RateLimiter:
    """Small in-memory sliding-window limiter keyed by client IP. Fine for a single process."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down")
        hits.append(now)
