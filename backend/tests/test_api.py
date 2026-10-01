import json
import time

from app.security import sign_payload
from app.services.common import next_business_day, today


def open_tasks(client, contact_id):
    return client.get(f"/api/contacts/{contact_id}").json()["open_tasks"]


# ---------- Security ----------
def test_requires_api_key(client):
    assert client.get("/api/pipeline", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/pipeline", headers={"X-API-Key": ""}).status_code == 401
    assert client.get("/api/health", headers={"X-API-Key": ""}).status_code == 200


def test_clients_cannot_claim_automation_source(client, lead):
    opp_id = lead["opportunities"][0]["id"]
    client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Contacted"}, headers={"X-Source": "automation"})
    latest = client.get("/api/activities?limit=1").json()[0]
    assert latest["source"] == "ui"


def test_rejects_invalid_stage(client, lead):
    opp_id = lead["opportunities"][0]["id"]
    assert client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Maybe"}).status_code == 422


# ---------- Automation rules ----------
def test_new_lead_gets_initial_outreach_task(lead):
    assert [t["title"] for t in lead["open_tasks"]] == ["Initial outreach to John Smith"]
    assert lead["open_tasks"][0]["source"] == "automation"


def test_qualified_creates_follow_up_once(client, lead):
    opp_id = lead["opportunities"][0]["id"]
    client.post(f"/api/tasks/{lead['open_tasks'][0]['id']}/complete")

    client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Qualified"})
    tasks = open_tasks(client, lead["id"])
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Follow up with John Smith"
    assert tasks[0]["due_date"] == next_business_day(today()).isoformat()

    # Re-entering Qualified must not duplicate the follow-up
    client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Proposal"})
    client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Qualified"})
    assert len(open_tasks(client, lead["id"])) == 1


def test_voice_follow_up_supersedes_automated_one(client, lead):
    """The headline flow: 'Move John Smith to Qualified and create a follow-up for tomorrow.'"""
    opp_id = lead["opportunities"][0]["id"]
    voice = {"X-Source": "voice"}
    client.post(f"/api/tasks/{lead['open_tasks'][0]['id']}/complete")

    client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Qualified"}, headers=voice)
    r = client.post(
        "/api/tasks",
        json={"contact_id": lead["id"], "opportunity_id": opp_id, "title": "Call John", "due_date": "2030-01-02"},
        headers=voice,
    )
    assert r.status_code == 201

    tasks = open_tasks(client, lead["id"])
    assert len(tasks) == 1
    assert (tasks[0]["title"], tasks[0]["due_date"], tasks[0]["source"]) == ("Call John", "2030-01-02", "voice")


def test_won_closes_tasks_and_starts_onboarding(client, lead):
    opp_id = lead["opportunities"][0]["id"]
    client.patch(f"/api/opportunities/{opp_id}/stage", json={"stage": "Won"})
    tasks = open_tasks(client, lead["id"])
    assert [t["title"] for t in tasks] == ["Kick off onboarding for Riverside Water District"]


def test_voice_can_add_and_update_deals(client, lead):
    voice = {"X-Source": "voice"}
    r = client.post(
        "/api/opportunities",
        json={"contact_id": lead["id"], "title": "Online payment module", "value": 10000},
        headers=voice,
    )
    assert r.status_code == 201 and r.json()["stage"] == "New"

    r = client.patch(f"/api/opportunities/{r.json()['id']}", json={"value": 12500}, headers=voice)
    assert r.json()["value"] == 12500
    latest = client.get("/api/activities?limit=1").json()[0]
    assert (latest["kind"], latest["source"]) == ("opportunity_updated", "voice")
    assert "$10,000 → $12,500" in latest["message"]

    assert client.patch(f"/api/opportunities/{r.json()['id']}", json={"value": -5}).status_code == 422


def test_pipeline_totals(client, lead):
    columns = {c["stage"]: c for c in client.get("/api/pipeline").json()}
    assert list(columns) == ["New", "Contacted", "Qualified", "Proposal", "Won", "Lost"]
    assert columns["New"]["count"] == 1 and columns["New"]["total_value"] == 85000


# ---------- Voice helpers ----------
def test_fuzzy_resolve_handles_transcription_errors(client, lead):
    client.post("/api/contacts", json={"name": "Maria Garcia"})
    result = client.get("/api/contacts/resolve", params={"name": "jon smyth"}).json()
    assert result["confident"] is True
    assert result["matches"][0]["contact"]["name"] == "John Smith"


def test_task_must_match_opportunity_contact(client, lead):
    other = client.post("/api/contacts", json={"name": "Someone Else"}).json()
    r = client.post(
        "/api/tasks",
        json={
            "contact_id": other["id"],
            "opportunity_id": lead["opportunities"][0]["id"],
            "title": "x",
            "due_date": "2030-01-01",
        },
    )
    assert r.status_code == 422


# ---------- Inbound webhook ----------
def _signed(body: dict, secret="inbound-secret", ts=None):
    raw = json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    return raw, {"X-Timestamp": ts, "X-Signature": sign_payload(secret, ts, raw), "Content-Type": "application/json"}


def test_inbound_lead_webhook(client):
    raw, headers = _signed(
        {
            "name": "Web Lead",
            "company": "Maple Grove Water Authority",
            "interest": "Online payment module",
            "estimated_value": 28000,
        }
    )
    r = client.post("/api/webhooks/leads", content=raw, headers=headers)
    assert r.status_code == 201
    detail = client.get(f"/api/contacts/{r.json()['id']}").json()
    assert detail["opportunities"][0]["title"] == "Online payment module"
    assert detail["recent_activity"][-1]["source"] == "webhook"


def test_inbound_webhook_rejects_bad_signature_and_replay(client):
    raw, headers = _signed({"name": "Evil"}, secret="wrong")
    assert client.post("/api/webhooks/leads", content=raw, headers=headers).status_code == 401

    raw, headers = _signed({"name": "Old"}, ts=int(time.time()) - 3600)
    assert client.post("/api/webhooks/leads", content=raw, headers=headers).status_code == 401
