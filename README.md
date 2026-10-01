# Voice CRM

A small sales CRM you can control by voice. Say *"Move John Smith to Qualified and create a follow-up for tomorrow"*, and the voice agent updates the CRM, the pipeline board changes live, and Slack gets a notification.

The demo data is a sales team selling **CIS Infinity**, a utility billing system, to water, electric and gas utilities.

## How it's built

| Part | Built with | What it does |
|---|---|---|
| **Frontend** | React + Vite | The website: pipeline board (drag and drop), contacts, tasks, activity feed, voice panel |
| **Backend** | Python, FastAPI, SQLite | The REST API: stores data, runs business rules and automation, handles security |
| **Voice agent** | LiveKit Agents, Deepgram, Groq | Listens (Deepgram speech-to-text), understands and picks an action (Groq LLM), calls the backend API, answers (Deepgram text-to-speech) |
| **Automation** | n8n + Slack | Receives CRM events from the backend and posts them to Slack |

```
Browser (React) ──/api──► Vite proxy ──► Backend (FastAPI) ──► SQLite
      │                                     ▲   │
      │ voice (LiveKit Cloud)               │   ├──► live updates to the browser (SSE)
      ▼                                     │   └──► n8n ──► Slack
Voice agent ── HTTP API calls ──────────────┘
```

The AI never touches the database directly. It can only use 10 tools (move a stage, create a follow-up, add a note, update a deal, and so on), and each tool calls the backend API, which validates every request.

## Important files

| File | Purpose |
|---|---|
| `agent/agent.py` | Voice agent: AI instructions, the 10 tools, voice pipeline setup |
| `agent/crm_client.py` | Sends the agent's HTTP requests to the backend |
| `agent/dates.py` | Turns "tomorrow" or "next friday" into real dates |
| `backend/app/main.py` | Backend entry point |
| `backend/app/routers/` | API endpoints (`crm.py`: CRM data; `integrations.py`: voice token, live events, inbound webhook) |
| `backend/app/services/crm.py` | Business logic behind each endpoint |
| `backend/app/services/automation.py` | Automatic rules (for example, Qualified creates a follow-up task) |
| `backend/app/models.py` | Database tables: Contact, Opportunity, Task, Activity |
| `frontend/src/App.jsx` | Main screen of the website |
| `frontend/src/components/` | UI parts: Pipeline, TaskList, VoiceSession and more |
| `n8n/crm-automation.json` | n8n workflow to import |
| `start.cmd` | Starts everything with one command |

## Run it (Windows)

**Needs:** Python 3.12+, Node.js 24+, and free keys from [LiveKit Cloud](https://cloud.livekit.io), [Deepgram](https://console.deepgram.com) and [Groq](https://console.groq.com).

1. Copy `.env.example` to `.env` and fill in the keys. For `CRM_API_KEY` and the webhook secrets, use any long random string.
2. Run:
   ```powershell
   .\start.cmd
   ```
   The first run installs everything. After that it starts the backend, voice agent, website and n8n in one terminal.
3. Open http://localhost:5173 and click **Start voice session**.

Other commands: `.\start.cmd -Reset` reloads the demo data, `.\start.cmd -NoN8n` skips n8n, and `npm test` runs the tests.

**Slack via n8n (optional):** open http://localhost:5678 and import `n8n/crm-automation.json`. Add a Header Auth credential (`X-Webhook-Secret` set to your `N8N_WEBHOOK_SECRET`), paste your Slack webhook URL into **Post to Slack**, and activate the workflow. If n8n isn't running, the backend posts to Slack directly.

## Try saying

- "Move John Smith to Qualified and create a follow-up for tomorrow."
- "What's due today?"
- "What's the status of Zarnain Khalique's deal?"
- "Change Carlos Rivera's deal value to thirty-two thousand."
- "Move Aisha Khan to Won."

## Security

- **Secrets:** all secrets live in `.env`, which is never committed. The browser never sees an API key; the Vite proxy adds it on the server side.
- **API access:** every API call needs an API key. Voice calls get a short-lived, single-room LiveKit token.
- **Inbound webhooks:** they must be HMAC-signed, and old requests are rejected.
- **Validation and audit:** all input is validated, and every change is logged with its source (`ui`, `voice`, `automation` or `webhook`).
