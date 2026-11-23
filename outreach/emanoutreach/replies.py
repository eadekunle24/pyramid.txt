"""Reply, bounce and opt-out handling. Stop events always win over queued sends."""
from __future__ import annotations

import json

from . import db, qualify, resolve

STOP_TYPES = {"reply", "positive_reply", "not_interested", "opt_out", "bounce", "booked_call", "disqualified"}
OUTCOME_TYPES = {"booked_call", "quote_sent", "won", "paid"}


def _find_lead(conn, ev):
    if ev.get("lead_id"):
        return ev["lead_id"]
    if ev.get("thread_id"):
        r = conn.execute("SELECT lead_id FROM messages WHERE thread_id=? LIMIT 1", (ev["thread_id"],)).fetchone()
        if r:
            return r["lead_id"]
    if ev.get("email"):
        e = ev["email"].strip().lower()
        r = conn.execute("SELECT lead_id FROM contacts WHERE address=?", (e,)).fetchone() or \
            conn.execute("SELECT lead_id FROM messages WHERE lower(to_address)=? LIMIT 1", (e,)).fetchone()
        if r:
            return r["lead_id"]
        r = conn.execute("SELECT lead_id FROM domains WHERE domain=?", (resolve.root_domain(e.split('@')[-1]),)).fetchone()
        if r:
            return r["lead_id"]
    return None


def cancel_queued(conn, lead_id, reason):
    l = db.lead(conn, lead_id)
    n = conn.execute("UPDATE messages SET state='cancelled', state_reason=?, updated_at=? "
                     "WHERE buying_team_key=? AND state IN ('draft','approved','queued')",
                     (reason, db.now_iso(), l["buying_team_key"])).rowcount
    return n


def apply(conn, ev: dict):
    """ev: {type, email?, thread_id?, lead_id?, at?, summary?, value?}"""
    t = ev["type"]
    lead_id = _find_lead(conn, ev)
    email = (ev.get("email") or "").strip().lower() or None
    if t == "opt_out" or t == "not_interested":
        qualify.suppress(conn, "email", email, t, "reply")
    if t == "bounce":
        qualify.suppress(conn, "email", email, "bounce", "provider")
        conn.execute("UPDATE contacts SET status='bounced' WHERE address=?", (email,))
    if lead_id is None:
        db.event(conn, f"unmatched_{t}", detail=ev)
        return None
    l = db.lead(conn, lead_id)
    if t in ("opt_out", "not_interested"):
        dom = (email or "").split("@")[-1]
        if dom and dom not in qualify.FREEMAIL:
            qualify.suppress(conn, "domain", dom, t, "reply")
        qualify.suppress(conn, "company", l["company_number"], t, "reply")
        qualify.suppress(conn, "team", l["buying_team_key"], t, "reply")
        conn.execute("UPDATE contacts SET status='opted_out' WHERE lead_id=? AND channel='email'", (lead_id,))
    if t in ("reply", "positive_reply", "booked_call"):
        qualify.suppress(conn, "team", l["buying_team_key"], "replied", "reply")  # no more automated touches
    if t in STOP_TYPES:
        n = cancel_queued(conn, lead_id, f"stopped by {t}")
        if l["state"] in ("drafted", "in_sequence"):
            db.set_state(conn, lead_id, "stopped", t)
        db.event(conn, t, lead_id=lead_id, detail={**ev, "cancelled": n}, at=ev.get("at"))
    if t in ("positive_reply", "booked_call"):
        msg = conn.execute("SELECT id, subject, offer_variant FROM messages WHERE lead_id=? AND state='sent' ORDER BY step LIMIT 1",
                           (lead_id,)).fetchone()
        evid = [dict(r) for r in conn.execute(
            "SELECT issue, plain_observation, source_url, observed_at FROM evidence WHERE lead_id=? AND message_eligible=1", (lead_id,))]
        summary = {"business": l["trading_name"], "domain": l["canonical_domain"], "said": ev.get("summary"),
                   "offer": msg["offer_variant"] if msg else None, "subject": msg["subject"] if msg else None,
                   "evidence": evid}
        conn.execute("INSERT INTO handoffs(lead_id,message_id,reason,summary,created_at) VALUES (?,?,?,?,?)",
                     (lead_id, msg["id"] if msg else None, t, json.dumps(summary), db.now_iso()))
    if t in OUTCOME_TYPES - {"booked_call"}:
        db.event(conn, t, lead_id=lead_id, value=ev.get("value"), detail=ev, at=ev.get("at"))
        if t == "won" and l["state"] != "won":
            db.set_state(conn, lead_id, "won", f"won {ev.get('value')}")
    return lead_id
