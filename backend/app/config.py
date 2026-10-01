"""Application settings, loaded from the project-root .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Core
    crm_api_key: str = Field(min_length=16, description="Shared key for the UI proxy, voice agent and n8n")
    database_url: str = f"sqlite:///{(ROOT_DIR / 'backend' / 'crm.db').as_posix()}"
    frontend_origin: str = "http://localhost:5173"
    app_timezone: str = "America/New_York"

    # LiveKit (token minting only; the agent reads its own vars)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "crm-voice-agent"

    # Automation / notifications
    n8n_webhook_url: str = ""
    n8n_webhook_secret: str = ""
    slack_webhook_url: str = ""  # direct fallback when n8n is not configured
    inbound_webhook_secret: str = ""  # HMAC secret for POST /api/webhooks/leads


@lru_cache
def get_settings() -> Settings:
    return Settings()
