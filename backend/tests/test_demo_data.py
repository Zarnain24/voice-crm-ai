"""Checks on the CIS Infinity demo data and on voice name matching against it."""

import pytest

import seed
from app.services.common import today


@pytest.fixture
def demo(client):
    seed.main()
    return client


def _resolve(client, spoken):
    return client.get("/api/contacts/resolve", params={"name": spoken}).json()


def test_demo_pipeline_matches_spec(demo):
    columns = {c["stage"]: c for c in demo.get("/api/pipeline").json()}
    assert {o["title"] for o in columns["New"]["opportunities"]} == {
        "CIS Infinity billing migration",
        "Customer self-service portal",
        "Smart meter data integration",
    }
    assert columns["Contacted"]["count"] == 1
    assert columns["Qualified"]["count"] == 2
    assert columns["Proposal"]["count"] == 1
    assert [o["title"] for o in columns["Won"]["opportunities"]] == ["Full CIS Infinity suite"]
    assert sum(c["total_value"] for c in columns.values()) == 534000


def test_every_contact_has_title_and_company_email(demo):
    for contact in demo.get("/api/contacts").json():
        assert contact["title"], contact["name"]
        local, domain = contact["email"].split("@")
        assert local == contact["name"].lower().replace(" ", ".")
        assert domain.split(".")[0][:6] in contact["company"].lower().replace(" ", "").replace("&", "")


def test_open_tasks_are_spread_around_today(demo):
    due = {t["due_date"] for t in demo.get("/api/tasks?status=open").json()}
    now = today().isoformat()
    assert any(d < now for d in due) and now in due and any(d > now for d in due)


def test_headline_demo_command_moves_john_and_leaves_one_follow_up(demo):
    john = _resolve(demo, "John Smith")["matches"][0]["contact"]
    deal = demo.get(f"/api/contacts/{john['id']}").json()["opportunities"][0]
    assert deal["stage"] == "New"

    voice = {"X-Source": "voice"}
    demo.patch(f"/api/opportunities/{deal['id']}/stage", json={"stage": "Qualified"}, headers=voice)
    demo.post(
        "/api/tasks",
        json={
            "contact_id": john["id"],
            "opportunity_id": deal["id"],
            "title": "Follow up with John Smith",
            "due_date": "2030-01-02",
        },
        headers=voice,
    )
    follow_ups = [t for t in demo.get(f"/api/contacts/{john['id']}").json()["open_tasks"] if t["kind"] == "follow_up"]
    assert [(t["title"], t["source"]) for t in follow_ups] == [("Follow up with John Smith", "voice")]


@pytest.mark.parametrize(
    "spoken",
    [
        "Zarnain Khalique",
        "zarnain khalique",
        "Zarnayn",
        "Zarnain Khaleeq",
        "Zarnayn Khaleek",
        "Sarnain Khalique",
        "Zarnain Kaleek",
        "Khalique",
        "Zar Nain Khalique",
    ],
)
def test_zarnain_khalique_speech_variants(demo, spoken):
    result = _resolve(demo, spoken)
    assert result["confident"], (spoken, result["matches"][:2])
    assert result["matches"][0]["contact"]["name"] == "Zarnain Khalique"


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("jon smyth", "John Smith"),
        ("Aysha Kahn", "Aisha Khan"),
        ("Robert Jonson", "Robert Johnson"),
        ("David Chen", "David Chen"),
    ],
)
def test_other_demo_names_still_resolve(demo, spoken, expected):
    result = _resolve(demo, spoken)
    assert result["confident"] and result["matches"][0]["contact"]["name"] == expected
