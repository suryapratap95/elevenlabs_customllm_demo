"""Server-side confirm-before-write: the caller must hear a read-back and say yes before any update.

Stateless check over the conversation ElevenLabs sends on every turn:
  1. the previous spoken assistant turn read back this case and this status;
  2. the caller's latest turn is an affirmative.
"""
import re

_YES = re.compile(r"^\s*(yes|yeah|yep|yup|correct|confirm(ed)?|that'?s (right|correct)|go ahead|do it|please do|sure|right)\b", re.I)
_DIGITS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
           "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
_STATUS = {"approved": ("approve", "approved"), "rejected": ("reject", "rejected"),
           "needs_review": ("needs review", "need review", "review")}


def _text(m: dict) -> str:
    c = m.get("content") or ""
    if isinstance(c, list):
        c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return c


def check(messages: list[dict], case_ref: str, status: str) -> tuple[bool, str]:
    turns = [m for m in messages if m.get("role") in ("user", "assistant") and _text(m).strip()]
    if len(turns) < 2 or turns[-1]["role"] != "user" or turns[-2]["role"] != "assistant":
        return False, "no read-back yet"
    readback = _text(turns[-2]).lower()
    spoken = re.sub(r"\b(" + "|".join(_DIGITS) + r")\b", lambda m: _DIGITS[m.group(1)], readback)
    if re.sub(r"\D", "", case_ref) not in re.sub(r"[\s,.-]", "", spoken):
        return False, f"read-back did not mention {case_ref}"
    if not any(w in readback for w in _STATUS[status]):
        return False, f"read-back did not mention '{status}'"
    if not _YES.match(_text(turns[-1])):
        return False, "caller has not said yes"
    return True, "confirmed"
