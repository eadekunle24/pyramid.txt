"""SQLite storage, state transitions and event history."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

# Allowed lead state transitions. Anything else raises, so a run can never
# silently skip a stage.
LEAD_STATES = {
    "discovered": {"resolved", "rejected", "review", "retry"},
    "resolved": {"audited", "rejected", "review", "retry"},
    "retry": {"resolved", "audited", "review", "rejected"},
    "audited": {"qualified", "review", "rejected", "audited"},
    "qualified": {"prioritised", "review", "rejected"},
    "prioritised": {"drafted", "review", "rejected"},
    "drafted": {"in_sequence", "review", "rejected", "stopped", "drafted"},
    "in_sequence": {"stopped", "won", "in_sequence"},
    "review": {"resolved", "audited", "qualified", "prioritised", "rejected", "review", "retry"},
    "rejected": {"review"},
    "stopped": {"won", "stopped"},
    "won": set(),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return conn


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def event(conn, type_: str, lead_id=None, message_id=None, detail=None, value=None, at=None):
    conn.execute(
        "INSERT INTO events(lead_id, message_id, type, detail, value, at) VALUES (?,?,?,?,?,?)",
        (lead_id, message_id, type_, json.dumps(detail) if detail is not None else None, value, at or now_iso()),
    )


def set_state(conn, lead_id: str, state: str, reason: str | None = None):
    row = conn.execute("SELECT state FROM leads WHERE id=?", (lead_id,)).fetchone()
    if row is None:
        raise KeyError(lead_id)
    cur = row["state"]
    if state != cur and state not in LEAD_STATES.get(cur, set()):
        raise ValueError(f"illegal transition {cur} -> {state} for {lead_id}")
    conn.execute(
        "UPDATE leads SET state=?, state_reason=?, updated_at=? WHERE id=?",
        (state, reason, now_iso(), lead_id),
    )
    event(conn, "state", lead_id=lead_id, detail={"from": cur, "to": state, "reason": reason})


def lead(conn, lead_id: str):
    return conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()


def live_leads(conn, states=None):
    q = "SELECT * FROM leads WHERE merged_into IS NULL"
    args: list = []
    if states:
        q += " AND state IN (%s)" % ",".join("?" * len(states))
        args = list(states)
    return conn.execute(q + " ORDER BY created_at", args).fetchall()
