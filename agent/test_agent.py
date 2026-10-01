"""Offline tests for the agent's deterministic pieces (no LiveKit/LLM calls)."""

from datetime import date

import pytest
from livekit.agents import ToolError

from agent import CRMAssistant, pick_open_deal
from dates import parse_due_date

WED = date(2026, 9, 30)  # a Wednesday


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("tomorrow", date(2026, 10, 1)),
        ("Tomorrow.", date(2026, 10, 1)),
        ("today", WED),
        ("day after tomorrow", date(2026, 10, 2)),
        ("friday", date(2026, 10, 2)),
        ("next friday", date(2026, 10, 9)),
        ("monday", date(2026, 10, 5)),
        ("wednesday", date(2026, 10, 7)),
        ("next week", date(2026, 10, 5)),
        ("in 3 days", date(2026, 10, 3)),
        ("in two weeks", date(2026, 10, 14)),
        ("by end of week", date(2026, 10, 2)),
        ("2026-12-01", date(2026, 12, 1)),
    ],
)
def test_parse_due_date(phrase, expected):
    assert parse_due_date(phrase, WED) == expected


def test_parse_due_date_rejects_gibberish():
    with pytest.raises(ValueError):
        parse_due_date("whenever", WED)


def test_pick_open_deal_prefers_open_and_flags_ambiguity():
    detail = {
        "name": "John",
        "opportunities": [
            {"id": 1, "title": "Old", "stage": "Won"},
            {"id": 2, "title": "Pilot", "stage": "New"},
        ],
    }
    assert pick_open_deal(detail)["id"] == 2

    detail["opportunities"].append({"id": 3, "title": "Expansion", "stage": "Qualified"})
    with pytest.raises(ToolError):
        pick_open_deal(detail)
    assert pick_open_deal(detail, "expansion")["id"] == 3


def test_tasks_due_labels_overdue_separately(monkeypatch):
    import asyncio

    import agent

    class FakeCRM:
        async def open_tasks_due(self, _cutoff):
            return [
                {"title": "Send overview", "contact_name": "John Smith", "due_date": "2026-09-29"},
                {"title": "Walkthrough", "contact_name": "David Chen", "due_date": "2026-09-30"},
            ]

    monkeypatch.setattr(agent, "local_today", lambda: WED)
    reply = asyncio.run(agent.CRMAssistant.tasks_due(CRMAssistant(FakeCRM()), None, "today"))
    assert "Send overview for John Smith (OVERDUE since Tuesday, September 29)" in reply
    assert "Walkthrough for David Chen (due today)" in reply


def test_tools_are_registered():
    names = {t.info.name for t in CRMAssistant(crm=None).tools}
    assert {
        "move_deal_stage",
        "create_follow_up",
        "lookup_contact",
        "create_lead",
        "create_deal",
        "update_deal",
    } <= names
