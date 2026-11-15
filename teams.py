"""Optional MS Teams card (Workflows webhook). Case reference and status only - never patient data."""
import os
import threading

import httpx

import events

URL = os.environ.get("TEAMS_WEBHOOK_URL", "")


def notify(case_ref: str, status: str) -> None:
    if not URL:
        return
    card = {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
        "body": [{"type": "TextBlock", "weight": "Bolder", "text": f"Case {case_ref} updated by voice"},
                 {"type": "FactSet", "facts": [{"title": "New status", "value": status}]}]}}]}

    def send():
        try:
            httpx.post(URL, json=card, timeout=5)
            events.add("teams", f"Teams card sent: {case_ref} → {status}")
        except Exception as exc:
            events.add("error", f"Teams webhook failed: {type(exc).__name__}")

    threading.Thread(target=send, daemon=True).start()
