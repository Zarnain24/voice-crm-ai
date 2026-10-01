"""Integration endpoints: voice session tokens, live event stream, inbound webhooks."""

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from livekit import api as livekit_api
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import schemas
from ..config import Settings, get_settings
from ..database import get_db
from ..events import bus
from ..models import Source
from ..security import RateLimiter, require_api_key, verify_signed_webhook
from ..services import crm

router = APIRouter(prefix="/api")

VOICE_TOKEN_TTL = timedelta(minutes=15)


@router.post(
    "/voice/token",
    response_model=schemas.VoiceTokenOut,
    dependencies=[Depends(require_api_key), Depends(RateLimiter(limit=10, window_seconds=60))],
    tags=["voice"],
)
def create_voice_token(settings: Settings = Depends(get_settings)):
    """Mint a short-lived LiveKit token for a fresh room and dispatch the CRM agent into it.

    The LiveKit API secret never leaves the server; the browser only gets a scoped JWT.
    """
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LiveKit is not configured")

    room = f"crm-{secrets.token_hex(6)}"
    identity = f"user-{secrets.token_hex(4)}"
    token = (
        livekit_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name("CRM User")
        .with_ttl(VOICE_TOKEN_TTL)
        .with_grants(livekit_api.VideoGrants(room_join=True, room=room, can_publish=True, can_subscribe=True))
        .with_room_config(
            livekit_api.RoomConfiguration(
                agents=[livekit_api.RoomAgentDispatch(agent_name=settings.livekit_agent_name)]
            )
        )
        .to_jwt()
    )
    return schemas.VoiceTokenOut(server_url=settings.livekit_url, token=token, room=room, identity=identity)


@router.get("/events", dependencies=[Depends(require_api_key)], tags=["events"])
async def stream_events(request: Request):
    """Server-Sent Events stream of every CRM change, so the UI updates the moment the
    voice agent (or anyone else) acts."""

    async def generator() -> AsyncIterator[str]:
        queue = bus.subscribe()
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {message}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/webhooks/leads",
    response_model=schemas.ContactOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(limit=30, window_seconds=60))],
    tags=["webhooks"],
)
def inbound_lead(body: bytes = Depends(verify_signed_webhook), db: Session = Depends(get_db)):
    """Create a lead from an external system (n8n form, Zapier, website, Apify scrape...).

    Authenticated by HMAC signature rather than the API key, so the sender never holds a
    credential that could read CRM data.
    """
    try:
        lead = schemas.InboundLead.model_validate(json.loads(body))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid lead payload: {exc}") from exc

    data = schemas.ContactCreate(
        name=lead.name,
        title=lead.title,
        email=lead.email,
        phone=lead.phone,
        company=lead.company,
        opportunity_title=lead.interest or f"{lead.company or lead.name} opportunity",
        opportunity_value=lead.estimated_value,
    )
    return crm.create_contact(db, data, Source.WEBHOOK)
