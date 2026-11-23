"""Gated release: approval, caps, pause, suppression-first, idempotent sends, reconciliation."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db, draft, qualify, replies


class ProviderUnavailable(Exception):
    pass


class Provider:
    """Interface. send() returns {'status': 'sent'|'unknown', 'message_id', 'thread_id'}."""
    name = "base"

    def fetch_events(self) -> list[dict]:
        raise NotImplementedError

    def send(self, msg) -> dict:
        raise NotImplementedError

    def lookup(self, msg) -> dict | None:
        """Search provider records (e.g. Gmail Sent) for this message. None = not found."""
        raise NotImplementedError


class HandoffProvider(Provider):
    """For the runtime agent: release writes messages to an outbox the agent sends via the
    Gmail connector, then records each result with `record-send`. Sends stay in 'sending'
    until recorded; anything left there becomes 'unknown' and must be reconciled."""
    name = "handoff"

    def __init__(self, events=None, outbox=None):
        self.events, self.outbox = events or [], outbox if outbox is not None else []

    def fetch_events(self):
        return self.events

    def send(self, msg):
        self.outbox.append({"message_id": msg["id"], "to": msg["to_address"], "subject": msg["subject"],
                            "body": msg["body"], "thread_id": msg["thread_id"], "idempotency_key": msg["idempotency_key"]})
        return {"status": "handed_off"}

    def lookup(self, msg):
        raise ProviderUnavailable("reconcile via record-send / reconcile commands")


def _today_sent(conn, step):
    day = datetime.now(timezone.utc).date().isoformat()
    return conn.execute("SELECT COUNT(*) c FROM send_attempts a JOIN messages m ON m.id=a.message_id "
                        "WHERE a.outcome IN ('sent','started','reconciled_sent') AND a.started_at>=? AND m.step=?",
                        (day, step)).fetchone()["c"]


def safety_stop(conn, cfg):
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    sent = conn.execute("SELECT COUNT(*) c FROM send_attempts WHERE outcome IN ('sent','reconciled_sent') AND started_at>=?",
                        (since,)).fetchone()["c"]
    bounces = conn.execute("SELECT COUNT(*) c FROM events WHERE type='bounce' AND at>=?", (since,)).fetchone()["c"]
    s = cfg["release"]["safety_stop"]
    if bounces > s["max_bounces_7d"] or (sent and bounces / sent > s["max_bounce_rate_7d"] and bounces >= 2):
        return f"safety stop: {bounces} bounces / {sent} sent in 7 days"
    return None


def approve(conn, message_ids, by="Emmanuel"):
    for mid in message_ids:
        conn.execute("UPDATE messages SET state='approved', approved_at=?, updated_at=? WHERE id=? AND state='draft' "
                     "AND state_reason IS NULL", (db.now_iso(), db.now_iso(), mid))
        db.event(conn, "approved", message_id=mid, detail={"by": by})


def reconcile(conn, provider):
    out = []
    for m in conn.execute("SELECT * FROM messages WHERE state IN ('unknown','sending')").fetchall():
        try:
            found = provider.lookup(m)
        except ProviderUnavailable as e:
            out.append((m["id"], "unresolved", str(e)))
            if m["state"] == "sending":
                conn.execute("UPDATE messages SET state='unknown', state_reason='send outcome not recorded' WHERE id=?", (m["id"],))
            continue
        record_reconcile(conn, m["id"], found)
        out.append((m["id"], "sent" if found else "absent", None))
    return out


def record_reconcile(conn, message_id, found: dict | None):
    ts = db.now_iso()
    if found:
        conn.execute("UPDATE messages SET state='sent', provider_message_id=?, thread_id=?, state_reason='reconciled', "
                     "updated_at=? WHERE id=?", (found.get("message_id"), found.get("thread_id"), ts, message_id))
        conn.execute("INSERT INTO send_attempts(message_id,started_at,finished_at,outcome,provider_ref) VALUES (?,?,?,?,?)",
                     (message_id, ts, ts, "reconciled_sent", found.get("message_id")))
    else:
        conn.execute("UPDATE messages SET state='queued', state_reason='reconciled: not found at provider', updated_at=? "
                     "WHERE id=?", (ts, message_id))
        conn.execute("INSERT INTO send_attempts(message_id,started_at,finished_at,outcome) VALUES (?,?,?,?)",
                     (message_id, ts, ts, "reconciled_absent"))


def record_send(conn, cfg, message_id, provider_message_id, thread_id, sent_at=None):
    ts = sent_at or db.now_iso()
    m = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    conn.execute("UPDATE messages SET state='sent', provider_message_id=?, thread_id=?, updated_at=? WHERE id=?",
                 (provider_message_id, thread_id or m["thread_id"], ts, message_id))
    conn.execute("UPDATE send_attempts SET outcome='sent', finished_at=?, provider_ref=? WHERE message_id=? AND outcome='started'",
                 (ts, provider_message_id, message_id))
    db.event(conn, "sent", lead_id=m["lead_id"], message_id=message_id, detail={"provider_message_id": provider_message_id})
    l = db.lead(conn, m["lead_id"])
    if l["state"] == "drafted":
        db.set_state(conn, m["lead_id"], "in_sequence", "opener sent")
    if m["step"] == 1:
        draft.followup(conn, cfg, message_id, datetime.fromisoformat(ts))


def release(conn, cfg, provider: Provider, now=None, allow_fixture=False):
    rc = cfg["release"]
    report = {"sent": [], "handed_off": [], "deferred": [], "blocked": [], "status": "ok"}
    if rc["mode"] == "off":
        report["status"] = "gated: release mode is off"
        return report
    if not rc.get("mailbox_approved_by"):
        report["status"] = "gated: mailbox not approved by Emmanuel"
        return report
    if rc.get("paused"):
        report["status"] = "paused"
        return report
    # 1. stop events first: a reply/bounce/opt-out that arrived while queued wins.
    try:
        for ev in provider.fetch_events():
            replies.apply(conn, ev)
    except ProviderUnavailable as e:
        report["status"] = f"provider unavailable while syncing replies; nothing released ({e})"
        return report
    stop = safety_stop(conn, cfg)
    if stop:
        report["status"] = stop
        return report
    # 2. ambiguous outcomes are reconciled before anything is retried
    report["reconciled"] = reconcile(conn, provider)
    now = now or datetime.now(timezone.utc)
    states = ("approved", "queued") if rc["mode"] == "approval" else ("approved", "queued", "draft")
    rows = conn.execute(
        "SELECT m.*, COALESCE(s.total,0) score FROM messages m LEFT JOIN scores s ON s.lead_id=m.lead_id "
        "WHERE m.state IN (%s) ORDER BY m.step DESC, score DESC, m.created_at" % ",".join("?" * len(states)), states).fetchall()
    for m in rows:
        if m["state"] == "draft" and m["state_reason"]:
            continue  # failed copy checks
        if m["step"] == 2 and m["due_at"] and datetime.fromisoformat(m["due_at"]) > now:
            continue
        if m["step"] == 2 and rc["mode"] == "approval":
            parent = conn.execute("SELECT approved_at FROM messages WHERE buying_team_key=? AND step=1", (m["buying_team_key"],)).fetchone()
            if not parent or not parent["approved_at"]:
                continue
        l = db.lead(conn, m["lead_id"])
        why = None
        hits = qualify.suppressed(conn, m["lead_id"], m["to_address"])
        if hits:
            why = "suppressed: " + "; ".join(hits)
        elif l["state"] in ("stopped", "rejected", "review", "won") or l["merged_into"]:
            why = f"lead state {l['state']}"
        elif m["step"] == 1 and conn.execute(
                "SELECT 1 FROM messages WHERE buying_team_key=? AND step=1 AND state IN ('sent','sending','unknown') AND id<>?",
                (m["buying_team_key"], m["id"])).fetchone():
            why = "team already has a live sequence"
        elif not allow_fixture and any(r["method"] == "fixture" for r in conn.execute(
                "SELECT method FROM evidence WHERE id IN (SELECT value FROM json_each(?))", (m["evidence_ids"] or "[]",))):
            why = "evidence is simulated (fixture) - never sent"
        if why:
            conn.execute("UPDATE messages SET state='cancelled', state_reason=?, updated_at=? WHERE id=?", (why, db.now_iso(), m["id"]))
            report["blocked"].append((m["id"], why))
            continue
        cap = rc["daily_cap"] if m["step"] == 1 else rc["followup_daily_cap"]
        if _today_sent(conn, m["step"]) >= cap:
            conn.execute("UPDATE messages SET state='queued', state_reason='deferred: daily cap reached' WHERE id=?", (m["id"],))
            db.event(conn, "deferred_cap", lead_id=m["lead_id"], message_id=m["id"])
            report["deferred"].append(m["id"])
            continue
        ts = db.now_iso()
        conn.execute("INSERT INTO send_attempts(message_id,started_at,outcome) VALUES (?,?,'started')", (m["id"], ts))
        conn.execute("UPDATE messages SET state='sending', updated_at=? WHERE id=?", (ts, m["id"]))
        conn.commit()  # the attempt is durable before the provider is called
        try:
            res = provider.send(m)
        except ProviderUnavailable as e:
            conn.execute("UPDATE messages SET state='queued', state_reason=? WHERE id=?", (f"provider unavailable: {e}", m["id"]))
            conn.execute("UPDATE send_attempts SET outcome='failed', finished_at=?, detail=? WHERE message_id=? AND outcome='started'",
                         (db.now_iso(), str(e), m["id"]))
            report["status"] = f"provider unavailable: {e}; remaining queue preserved"
            break
        except TimeoutError as e:
            conn.execute("UPDATE messages SET state='unknown', state_reason='send outcome unknown - reconcile before retry' WHERE id=?", (m["id"],))
            conn.execute("UPDATE send_attempts SET outcome='unknown', finished_at=?, detail=? WHERE message_id=? AND outcome='started'",
                         (db.now_iso(), str(e), m["id"]))
            report["blocked"].append((m["id"], "unknown outcome"))
            continue
        if res.get("status") == "sent":
            record_send(conn, cfg, m["id"], res.get("message_id"), res.get("thread_id"))
            report["sent"].append(m["id"])
        elif res.get("status") == "handed_off":
            report["handed_off"].append(m["id"])
        else:
            conn.execute("UPDATE messages SET state='unknown', state_reason='provider returned ambiguous status' WHERE id=?", (m["id"],))
            conn.execute("UPDATE send_attempts SET outcome='unknown', finished_at=? WHERE message_id=? AND outcome='started'",
                         (db.now_iso(), m["id"]))
            report["blocked"].append((m["id"], "unknown outcome"))
    conn.commit()
    return report
