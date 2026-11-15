# ElevenLabs voice agent demo — VerifyHub operations assistant

A standalone demo of an **ElevenLabs web widget** talking to **your own Python "Custom LLM" endpoint**,
which calls **Azure AI Foundry** (`gpt-6-sol`) and runs database tools **in-process**. One small app serves:

- the demo page (widget + live case table + audit log + a live "what the agent is doing" feed);
- `POST /v1/chat/completions` — the OpenAI-compatible, streamed endpoint ElevenLabs calls
  (also answered at `/chat/completions`, so either Server URL style works).

All data is synthetic (SQLite file `demo.db`).

```
Browser widget ──voice──▶ ElevenLabs (speech⇄text) ──HTTPS──▶ this app /v1/chat/completions ──▶ Azure AI Foundry
                                                                 │  tools run in-process → SQLite
                                                                 │  confirm-before-write guard
                                                                 └─ optional Teams card (case ref + status only)
```

## 1. Run the app (5 minutes)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill AZURE_OPENAI_* and a long random DEMO_LLM_SECRET
uvicorn app:app --port 8080
```

Open http://localhost:8080 — the case table and the feed work before ElevenLabs is set up.

## 2. Give ElevenLabs a public HTTPS URL

ElevenLabs' servers call your endpoint, so it must be reachable from the internet:

```bash
cloudflared tunnel --url http://localhost:8080     # or: ngrok http 8080
```

Note the `https://…` URL it prints. Check it: `curl https://<url>/healthz`.
For lower latency on the day, run the app on a small cloud VM near ElevenLabs instead of a laptop tunnel.

## 3. Create the agent in ElevenLabs

1. ElevenLabs → **Agents** → create a blank agent, e.g. "VerifyHub Ops".
2. **First message:** "Hi, this is the VerifyHub operations assistant. Which case can I help with?"
3. **System prompt:** a short line is enough ("Operations assistant for VerifyHub."). The real rules live on
   your server, which always puts its own system prompt first.
4. **Voice / language:** any voice; English.
5. **LLM → Custom LLM:**
   - **Server URL:** your tunnel URL, e.g. `https://abc.trycloudflare.com` (if the test fails, try adding `/v1`).
   - **Model ID:** anything, e.g. `gpt-6-sol` (the server uses `AZURE_OPENAI_DEPLOYMENT` from `.env`).
   - **API key:** *Create new secret* with the **same value as `DEMO_LLM_SECRET`**.
     If the feed shows "Rejected request: wrong or missing API key", the two values differ.
6. **Security / Advanced:** the web widget needs a **public agent with authentication disabled**.
   Add `localhost` and your tunnel domain to the allowlist if you use one.
7. Copy the **agent ID** from the Widget / embed tab into `.env` as `ELEVENLABS_AGENT_ID`, restart the app,
   reload the page: the widget appears bottom-right.

## 4. Before the audience arrives

- `python reset_db.py` — fresh data.
- One test call; watch the feed show **HEARD → TOOL → TURN** with timings.
- Keep the first-words time under about 0.8 s on the feed; if it's slower, use a smaller model or a closer server.

## 5. Production notes (HIPAA)

The demo uses synthetic data. For real PHI: BAAs with Azure / your Foundry region and ElevenLabs, zero data
retention where available, ElevenLabs Zero Retention Mode with support told you use a Custom LLM, real
authentication instead of a public agent, and the guard + audit pattern shown here.

## Files

| File | What |
|---|---|
| `voice.py` | Custom LLM endpoint: server prompt, tools, filler line, ElevenLabs system-tool pass-through |
| `guard.py` | Confirm-before-write: update refused until read-back + "yes" |
| `store.py` | SQLite, seed data, the three tools (parameterised SQL, audit log) |
| `templates/index.html` | Demo page with the widget and live panels |
| `teams.py` | Optional Teams card |
| `tests/` | `pytest -q` — fake Foundry client, no keys needed |
