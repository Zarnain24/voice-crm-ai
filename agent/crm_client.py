"""Thin async client for the CRM API.

The agent never touches the database. It can only do what these endpoints allow, and
every call is tagged `X-Source: voice` so actions show up as voice-initiated in the audit log.
"""

from typing import Any

import httpx
from livekit.agents import ToolError


class CRMClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-Key": api_key, "X-Source": "voice"},
            timeout=10,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ToolError("The CRM is unreachable right now.") from exc
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ToolError(f"The CRM rejected that request: {detail}")
        return response.json() if response.content else None

    # ---- lookups ----
    async def resolve_contact(self, name: str) -> dict:
        """Return the single contact matching a spoken name, or raise a ToolError the LLM can
        relay to the user ("Did you mean John Smith or Joan Smyth?")."""
        result = await self._request("GET", "/api/contacts/resolve", params={"name": name})
        matches = result["matches"]
        if not matches:
            raise ToolError(f"No contact found matching '{name}'.")
        if not result["confident"]:
            options = ", ".join(m["contact"]["name"] for m in matches[:3])
            raise ToolError(f"'{name}' is ambiguous. Ask the user which one they mean: {options}.")
        return matches[0]["contact"]

    async def contact_detail(self, contact_id: int) -> dict:
        return await self._request("GET", f"/api/contacts/{contact_id}")

    async def contact_names(self) -> list[str]:
        return [c["name"] for c in await self._request("GET", "/api/contacts")]

    async def pipeline(self) -> list[dict]:
        return await self._request("GET", "/api/pipeline")

    async def open_tasks_due(self, on_or_before: str) -> list[dict]:
        return await self._request("GET", "/api/tasks", params={"status": "open", "due_on_or_before": on_or_before})

    # ---- writes ----
    async def change_stage(self, opportunity_id: int, stage: str) -> dict:
        return await self._request("PATCH", f"/api/opportunities/{opportunity_id}/stage", json={"stage": stage})

    async def create_opportunity(self, **payload: Any) -> dict:
        return await self._request("POST", "/api/opportunities", json=payload)

    async def update_opportunity(self, opportunity_id: int, **changes: Any) -> dict:
        return await self._request("PATCH", f"/api/opportunities/{opportunity_id}", json=changes)

    async def create_task(self, **payload: Any) -> dict:
        return await self._request("POST", "/api/tasks", json=payload)

    async def complete_task(self, task_id: int) -> dict:
        return await self._request("POST", f"/api/tasks/{task_id}/complete")

    async def add_note(self, contact_id: int, text: str) -> None:
        await self._request("POST", f"/api/contacts/{contact_id}/notes", json={"text": text})

    async def create_contact(self, **payload: Any) -> dict:
        return await self._request("POST", "/api/contacts", json=payload)
