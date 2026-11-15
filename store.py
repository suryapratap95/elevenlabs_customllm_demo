"""SQLite store + the voice agent's tools (synthetic data only).

Standalone version of VerifyHub's tools layer: one clinic, verification cases, an audit log.
Every tool is a plain Python function with parameterised SQL. The LLM never writes SQL.
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("DEMO_DB", Path(__file__).parent / "demo.db"))
WRITABLE = ("approved", "rejected", "needs_review")

SEED = [
    # case_ref, first, last, doc_type, expiry, status, reason
    ("P-1001", "Avery", "Thompson", "driver license", "2028-03-14", "pending", None),
    ("P-1002", "Jordan", "Reyes", "passport", "2031-06-30", "pending", None),
    ("P-1003", "Casey", "Nguyen", "state ID", "2025-07-21", "pending", None),
    ("P-1004", "Riley", "Patel", "driver license", "2029-01-30", "approved", "Docs verified"),
    ("P-1005", "Morgan", "Okafor", "driver license", "2027-09-09", "needs_review", "DOB differs by one day"),
    ("P-1006", "Taylor", "Kim", "passport", "2030-05-17", "pending", None),
    ("P-1042", "Avery", "Thompson", "passport", "2033-03-14", "pending", None),
]


class ToolError(Exception):
    """A short, speakable error for the model."""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reset() -> None:
    with connect() as c:
        c.executescript("""
            DROP TABLE IF EXISTS audit_log; DROP TABLE IF EXISTS cases;
            CREATE TABLE cases (
              case_ref TEXT PRIMARY KEY, first_name TEXT, last_name TEXT, doc_type TEXT,
              doc_expiry TEXT, status TEXT NOT NULL, reason TEXT,
              updated_at TEXT NOT NULL DEFAULT (datetime('now')));
            CREATE TABLE audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT, case_ref TEXT, actor TEXT, channel TEXT,
              old_status TEXT, new_status TEXT, reason TEXT,
              at TEXT NOT NULL DEFAULT (datetime('now')));
        """)
        c.executemany(
            "INSERT INTO cases (case_ref, first_name, last_name, doc_type, doc_expiry, status, reason) VALUES (?,?,?,?,?,?,?)",
            SEED,
        )


def ensure_db() -> None:
    if not DB_PATH.exists():
        reset()


def normalize_ref(raw: str) -> str:
    """Speech-to-text gives 'p 1042', 'P one zero four two' is handled by the model; we accept any digits."""
    digits = re.sub(r"\D", "", raw or "")
    if not 3 <= len(digits) <= 6:
        raise ToolError(f"'{raw}' is not a valid case reference. Case references look like P-1042.")
    return f"P-{digits}"


def all_cases() -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cases ORDER BY case_ref")]


def recent_audit(limit: int = 8) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]


# ---------------- tools the model can call ----------------

def get_case_status(case_ref: str) -> dict:
    ref = normalize_ref(case_ref)
    with connect() as c:
        row = c.execute(
            "SELECT case_ref, first_name, doc_type, doc_expiry, status, reason FROM cases WHERE case_ref = ?", (ref,)
        ).fetchone()
    if not row:
        raise ToolError(f"I couldn't find case {ref}.")
    # Minimum necessary: first name only, no DOB or document numbers.
    return {"case_ref": row["case_ref"], "patient_first_name": row["first_name"], "document_type": row["doc_type"],
            "document_expiry": row["doc_expiry"], "status": row["status"], "status_reason": row["reason"]}


def list_pending_cases(limit: int = 5) -> dict:
    limit = max(1, min(int(limit or 5), 10))
    with connect() as c:
        rows = c.execute(
            "SELECT case_ref, status FROM cases WHERE status IN ('pending','needs_review') ORDER BY updated_at, case_ref LIMIT ?",
            (limit,),
        ).fetchall()
    return {"cases": [dict(r) for r in rows]}


def update_case_status(case_ref: str, status: str, reason: str | None, actor: str = "Voice agent") -> dict:
    if status not in WRITABLE:
        raise ToolError(f"Status must be one of: {', '.join(WRITABLE)}.")
    if status == "rejected" and not (reason and reason.strip()):
        raise ToolError("A reason is required to reject a case.")
    ref = normalize_ref(case_ref)
    with connect() as c:
        row = c.execute("SELECT status FROM cases WHERE case_ref = ?", (ref,)).fetchone()
        if not row:
            raise ToolError(f"I couldn't find case {ref}.")
        if row["status"] == status:
            return {"case_ref": ref, "status": status, "changed": False}
        c.execute("UPDATE cases SET status = ?, reason = ?, updated_at = datetime('now') WHERE case_ref = ?",
                  (status, (reason or "").strip()[:200] or None, ref))
        c.execute("INSERT INTO audit_log (case_ref, actor, channel, old_status, new_status, reason) VALUES (?,?,?,?,?,?)",
                  (ref, actor, "voice", row["status"], status, reason))
    return {"case_ref": ref, "old_status": row["status"], "status": status, "changed": True}
