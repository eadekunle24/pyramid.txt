"""Drafting: one real observation, one reason to care, one simple action."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from . import db, qualify

BANNED = ["i hope this finds you well", "i came across", "i stumbled upon", "leverage", "elevate",
          "boost your online presence", "in today's digital world", "game-changer", "game changer",
          "quick question", "mockup", "mock-up", "mock up", "guarantee", "just bumping", "in case it got buried",
          "—", "–"]
OPT_OUT = "If you’d rather I didn’t follow up, just reply and I’ll take you off my list."

SUBJECTS = {
    "broken_quote_link": "One quote link on your {niche} site",
    "empty_tel": "The call button on your site",
    "service_page_no_next_step": "Asking for a quote on your {service} page",
    "cta_buried": "The call button on your homepage",
    "noindex": "Your {niche} site and Google",
    "not_in_top10": "Your {niche} site on Google for {town}",
}


def words(text: str) -> int:
    """Word count for the opener; a link counts as one word."""
    text = re.sub(r"\S*(https?://|netlify\.app|\.co\.uk|\.com)\S*", " link ", text)
    return len(re.findall(r"[A-Za-z0-9’'&]+", text))


def check_copy(body: str, lo: int, hi: int) -> list[str]:
    problems = []
    low = body.lower()
    for b in BANNED:
        if b in low:
            problems.append(f"banned: {b!r}")
    main = body.split("\n\nEmmanuel Adekunle")[0]
    n = words(main)
    if not lo <= n <= hi:
        problems.append(f"word count {n} outside {lo}-{hi}")
    if OPT_OUT not in body:
        problems.append("missing opt-out line")
    if "Emmanuel Adekunle" not in body:
        problems.append("missing sender identity")
    if body.count("!") > 1:
        problems.append("too many exclamation marks")
    return problems


def _signature(cfg):
    s = cfg["sender"]
    return f"Emmanuel Adekunle\n{s['signoff_line']}\n{s['mailbox']}\n{OPT_OUT}"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def opener(conn, cfg, lead_id: str):
    l = db.lead(conn, lead_id)
    camp = next(c for c in cfg["campaigns"] if c["id"] == l["campaign"])
    sc = conn.execute("SELECT * FROM scores WHERE lead_id=?", (lead_id,)).fetchone()
    evs = conn.execute("SELECT * FROM evidence WHERE lead_id=? AND message_eligible=1 ORDER BY severity DESC",
                       (lead_id,)).fetchall()
    ev = evs[0]
    name = l["trading_name"] or "there"
    short = re.sub(r"\s*\b(ltd|limited|llp|plc)\.?$", "", name, flags=re.I).strip()
    greet = f"Hi {short} team," if l["trading_name"] else "Hi there,"
    if ev["kind"] == "search":
        lead_in = _cap(ev["plain_observation"]) + "."
    elif ev["method"] == "rendered" and (ev["viewport"] or "").startswith(("3", "4")):
        lead_in = f"I was looking at your site on my phone. {_cap(ev['plain_observation'])}."
    else:
        lead_in = f"I was looking at your website. {_cap(ev['plain_observation'])}."
    fix = ev["fix"].rstrip(".")
    fix = fix[0].lower() + fix[1:]
    care = {
        "conversion": "That’s the step where someone with a leaking roof decides who to ring.",
        "search": "That’s usually where local homeowners start when they need the job done.",
    }.get(ev["kind"], "")
    if camp["niche"] != "roofing":
        care = {"conversion": "That’s the moment a customer decides whether to book.",
                "search": "That’s where most new customers start looking."}.get(ev["kind"], "")
    proof = camp["proof"]["line"] if camp.get("proof") else ""
    high = sc["queue"] == "high"
    ask = ("Want me to put together a free concept of that fix on your homepage, shown at phone size? "
           if high else "Want me to put together a free concept of what I’d change on your homepage? ")
    ask += "If you like the direction, I’ll give you a fixed quote."
    body = f"{greet}\n\n{lead_in} {care} I’d {fix}.\n\n{proof}\n\n{ask}\n\n{_signature(cfg)}"
    subject = SUBJECTS.get(ev["issue"], "Your {niche} website").format(
        niche=camp["niche"], town=l["town"] or "your area",
        service=(json.loads(ev["search_context"])["query"] if ev["search_context"] else camp["services"][0]))
    visual = None
    if high:
        visual = {"type": "mobile before/after", "viewport": ev["viewport"] or "390x844",
                  "before": {"page": ev["source_url"], "tap_path": json.loads(ev["steps"] or "[]")},
                  "after": f"Concept: {ev['fix']}", "label": "Concept, not their live site",
                  "status": "to_make"}
    return subject, body, [e["id"] for e in evs], visual


def make_drafts(conn, cfg, lead_id: str):
    l = db.lead(conn, lead_id)
    em = qualify.best_email(conn, lead_id)
    key = f"team:{l['buying_team_key']}:step:1"
    if conn.execute("SELECT 1 FROM messages WHERE idempotency_key=?", (key,)).fetchone():
        return None  # already drafted for this buying team (idempotent re-run)
    live = conn.execute("SELECT 1 FROM messages WHERE buying_team_key=? AND state NOT IN ('cancelled','failed')",
                        (l["buying_team_key"],)).fetchone()
    if live:
        return None
    subject, body, ev_ids, visual = opener(conn, cfg, lead_id)
    problems = check_copy(body, 60, 110)
    camp = next(c for c in cfg["campaigns"] if c["id"] == l["campaign"])
    mid = db.new_id("msg")
    ts = db.now_iso()
    state = "draft" if not problems else "draft"
    conn.execute(
        "INSERT INTO messages(id,lead_id,buying_team_key,step,idempotency_key,to_address,subject,body,offer_variant,"
        "proof_url,evidence_ids,visual_brief,state,state_reason,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, lead_id, l["buying_team_key"], 1, key, em["address"], subject, body, "free_homepage_preview",
         camp["proof"]["url"] if camp.get("proof") else None, json.dumps(ev_ids),
         json.dumps(visual) if visual else None, state, "; ".join(problems) or None, ts, ts))
    db.event(conn, "drafted", lead_id=lead_id, message_id=mid, detail={"problems": problems})
    db.set_state(conn, lead_id, "drafted" if not problems else "review",
                 "draft ready for approval" if not problems else "draft failed copy checks: " + "; ".join(problems))
    return mid


def add_business_days(d: datetime, n: int) -> datetime:
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def followup(conn, cfg, message_id: str, sent_at: datetime):
    """Schedule the single follow-up in the original thread, adding a real detail."""
    m = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    key = f"team:{m['buying_team_key']}:step:2"
    if conn.execute("SELECT 1 FROM messages WHERE idempotency_key=?", (key,)).fetchone():
        return None
    used = set(json.loads(m["evidence_ids"] or "[]")[:1])
    extra = conn.execute("SELECT * FROM evidence WHERE lead_id=? AND message_eligible=1 ORDER BY severity DESC",
                         (m["lead_id"],)).fetchall()
    extra = [e for e in extra if e["id"] not in used]
    if extra:
        detail = f"One more thing I noticed: {extra[0]['plain_observation']}."
    else:
        detail = "To be specific, the concept would show your homepage’s first screen on a phone with a working quote button beside your main services."
    body = (f"Hi again,\n\n{detail} Happy to fold that into the free concept as well, so you can see both fixes "
            f"together.\n\nShall I go ahead?\n\n{_signature(cfg)}")
    due = add_business_days(sent_at, cfg["followup"]["business_days_after"])
    mid = db.new_id("msg")
    ts = db.now_iso()
    conn.execute(
        "INSERT INTO messages(id,lead_id,buying_team_key,step,idempotency_key,to_address,subject,body,offer_variant,"
        "proof_url,evidence_ids,state,due_at,thread_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, m["lead_id"], m["buying_team_key"], 2, key, m["to_address"], "Re: " + m["subject"], body,
         m["offer_variant"], m["proof_url"], json.dumps([e["id"] for e in extra[:1]]), "queued", due.isoformat(),
         m["thread_id"], ts, ts))
    db.event(conn, "followup_scheduled", lead_id=m["lead_id"], message_id=mid, detail={"due": due.isoformat()})
    return mid
