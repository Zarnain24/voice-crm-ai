"""Outbound delivery of CRM events.

- If N8N_WEBHOOK_URL is set, every event is POSTed to n8n, which owns routing (Slack etc.).
  n8n authenticates us with Header Auth (`X-Webhook-Secret`).
- If n8n is not configured, or is unreachable / rejects the event (e.g. the workflow is not
  active), notable events go straight to SLACK_WEBHOOK_URL so notifications never go dark.

Delivery runs in a background task with retries, so a slow or failing webhook never
blocks or breaks a CRM request.
"""

import asyncio
import logging
from typing import Any

import httpx

from ..config import Settings

log = logging.getLogger("crm.notifier")

MAX_ATTEMPTS = 3


async def run_dispatcher(outbox: asyncio.Queue[dict[str, Any]], settings: Settings) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            event = await outbox.get()
            try:
                await _deliver(client, event, settings)
            except Exception:  # never let one bad event kill the worker
                log.exception("Failed to deliver %s", event.get("type"))


async def _deliver(client: httpx.AsyncClient, event: dict[str, Any], settings: Settings) -> None:
    if settings.n8n_webhook_url:
        headers = {"X-Webhook-Secret": settings.n8n_webhook_secret} if settings.n8n_webhook_secret else {}
        if await _post_with_retry(client, settings.n8n_webhook_url, event, headers):
            return
        log.warning("n8n unavailable; falling back to direct Slack for %s", event["type"])
    if settings.slack_webhook_url and (text := slack_text(event)):
        await _post_with_retry(client, settings.slack_webhook_url, {"text": text}, {})


async def _post_with_retry(client: httpx.AsyncClient, url: str, body: dict, headers: dict) -> bool:
    """POST with exponential backoff on network errors and 5xx. Returns True if accepted."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.post(url, json=body, headers=headers)
            if response.is_success:
                return True
            log.warning("Webhook %s returned %s: %s", url.split("?")[0], response.status_code, response.text[:200])
            if response.status_code < 500:  # 4xx won't fix itself (e.g. n8n workflow not active)
                return False
        except httpx.ConnectError as exc:  # nothing listening (e.g. n8n container stopped): don't wait
            log.warning("Webhook %s unreachable: %r", url.split("?")[0], exc)
            return False
        except httpx.TransportError as exc:
            log.warning("Webhook attempt %d to %s failed: %r", attempt, url.split("?")[0], exc)
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(0.5 * 2**attempt)
    return False


def slack_text(event: dict[str, Any]) -> str | None:
    """Human-readable Slack message for notable events (mirrors the n8n Code node)."""
    d = event["data"]
    via = " :microphone: _via voice_" if d.get("source") == "voice" else ""
    match event["type"]:
        case "opportunity.stage_changed" if d["to_stage"] == "Won":
            return f":tada: *Deal won!* {d['title']} with {d['contact_name']} (${d['value']:,}){via}"
        case "opportunity.stage_changed" if d["to_stage"] == "Lost":
            return f":small_red_triangle_down: Deal lost: {d['title']} with {d['contact_name']}{via}"
        case "opportunity.stage_changed":
            return (
                f":arrow_right: *{d['contact_name']}* moved {d['from_stage']} → *{d['to_stage']}* "
                f"({d['title']}, ${d['value']:,}){via}"
            )
        case "lead.created":
            company = f" from {d['company']}" if d.get("company") else ""
            return f":wave: New lead: *{d['name']}*{company} (source: {d['source']})"
        case "task.created" | "task.updated" if d.get("source") == "voice":
            return f":spiral_calendar_pad: Follow-up for *{d['contact_name']}*: {d['title']} (due {d['due_date']}){via}"
    return None
