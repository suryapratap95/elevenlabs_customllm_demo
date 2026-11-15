"""In-memory event feed shown live on the demo page (what the audience watches)."""
import time
from collections import deque

_EVENTS: deque = deque(maxlen=60)
_SEQ = 0


def add(kind: str, text: str, ms: float | None = None) -> None:
    global _SEQ
    _SEQ += 1
    _EVENTS.append({"seq": _SEQ, "t": time.strftime("%H:%M:%S"), "kind": kind, "text": text,
                    "ms": round(ms) if ms is not None else None})


def since(seq: int) -> list[dict]:
    return [e for e in _EVENTS if e["seq"] > seq]
