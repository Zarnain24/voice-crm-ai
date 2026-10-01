"""Send a correctly signed lead to the inbound webhook, the same way n8n, Zapier or a
website form would.  Usage:  python send_test_lead.py "Jane Doe" "Maple Grove Water Authority"
"""

import json
import sys
import time
import urllib.request

from app.config import get_settings
from app.security import sign_payload

settings = get_settings()
name = sys.argv[1] if len(sys.argv) > 1 else "Jane Doe"
company = sys.argv[2] if len(sys.argv) > 2 else "Maple Grove Water Authority"

body = json.dumps(
    {
        "name": name,
        "company": company,
        "title": "Customer Billing Supervisor",
        "email": "jane.doe@maplegrovewater.org",
        "interest": "CIS Infinity billing upgrade",
        "estimated_value": 45000,
    }
).encode()
timestamp = str(int(time.time()))

request = urllib.request.Request(
    "http://localhost:8000/api/webhooks/leads",
    data=body,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Signature": sign_payload(settings.inbound_webhook_secret, timestamp, body),
    },
)
with urllib.request.urlopen(request) as response:
    print(response.status, response.read().decode())
