"""ElevenLabs voice-agent demo: widget page + live data + Custom LLM endpoint, in one small app.

Run:  uvicorn app:app --port 8080      then open http://localhost:8080
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

import events  # noqa: E402
import store  # noqa: E402
import voice  # noqa: E402

app = FastAPI(title="ElevenLabs voice demo")
app.include_router(voice.router)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
store.ensure_db()


@app.get("/", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(request, "index.html", {"agent_id": os.environ.get("ELEVENLABS_AGENT_ID", "")})


@app.get("/api/state")
def state(since: int = 0):
    return {"cases": store.all_cases(), "audit": store.recent_audit(), "events": events.since(since)}


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": voice.MODEL, "auth": bool(voice.SECRET)}
