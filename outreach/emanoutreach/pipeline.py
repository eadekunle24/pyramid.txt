"""Stage runner: audit -> qualify -> prioritise -> draft for whatever is ready.

Each stage only picks up leads in its input state, so runs are retryable and a
resumed run after a partial failure continues where it stopped.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import audit, db, draft, qualify


def run_audits(conn, observations):
    out = {}
    for obs in observations:
        l = db.lead(conn, obs["lead_id"])
        if l is None or l["merged_into"] or l["state"] not in ("resolved", "retry", "audited"):
            out[obs["lead_id"]] = "skipped (state)"
            continue
        if l["state"] == "retry" and l["retry_after"] and datetime.fromisoformat(l["retry_after"]) > datetime.now(timezone.utc) \
                and not obs.get("force"):
            out[obs["lead_id"]] = "waiting for retry window"
            continue
        out[obs["lead_id"]] = audit.audit(conn, obs)
        conn.commit()
    return out


def advance(conn, cfg):
    """Qualify, score and draft every lead that is ready. Safe to re-run."""
    log = []
    for l in db.live_leads(conn, ["audited"]):
        ok, failed = qualify.qualify(conn, cfg, l["id"])
        log.append((l["id"], "qualified" if ok else "not qualified", [f[0] for f in failed]))
        conn.commit()
    for l in db.live_leads(conn, ["qualified"]):
        total, queue = qualify.score(conn, cfg, l["id"])
        log.append((l["id"], f"score {total}", queue))
        conn.commit()
    for l in db.live_leads(conn, ["prioritised"]):
        mid = draft.make_drafts(conn, cfg, l["id"])
        log.append((l["id"], "drafted" if mid else "draft skipped (team already has a message)", mid))
        conn.commit()
    return log
