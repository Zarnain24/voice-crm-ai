import os
import tempfile
from pathlib import Path

# Configure an isolated environment before the app (and its cached settings) is imported.
_db = Path(tempfile.mkdtemp()) / "test.db"
os.environ.update(
    CRM_API_KEY="test-api-key-0123456789",
    DATABASE_URL=f"sqlite:///{_db.as_posix()}",
    INBOUND_WEBHOOK_SECRET="inbound-secret",
    N8N_WEBHOOK_URL="",
    SLACK_WEBHOOK_URL="",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = os.environ["CRM_API_KEY"]


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app, headers={"X-API-Key": API_KEY}) as c:
        yield c


@pytest.fixture
def lead(client):
    """A contact with one opportunity in stage New."""
    r = client.post(
        "/api/contacts",
        json={
            "name": "John Smith",
            "title": "Billing Manager",
            "company": "Riverside Water District",
            "opportunity_title": "CIS Infinity billing migration",
            "opportunity_value": 85000,
        },
    )
    assert r.status_code == 201
    detail = client.get(f"/api/contacts/{r.json()['id']}").json()
    return detail
