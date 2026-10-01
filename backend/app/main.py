import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .events import bus
from .routers import crm, integrations
from .services.notifier import run_dispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    init_db()
    outbox = bus.bind(asyncio.get_running_loop())
    dispatcher = asyncio.create_task(run_dispatcher(outbox, settings))
    yield
    dispatcher.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await dispatcher


app = FastAPI(title="Voice CRM API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.include_router(crm.router)
app.include_router(integrations.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}
