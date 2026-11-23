"""Auditable eligibility gates, suppression checks and the 100-point score."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import db, resolve

CORPORATE = {"ltd", "limited", "llp", "plc", "dac", "teoranta"}
FREEMAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.co.uk", "yahoo.com",
            "yahoo.co.uk", "btinternet.com", "btconnect.com", "icloud.com", "aol.com", "hotmail.co.uk"}


# ---------------------------------------------------------------- suppression
def suppress(conn, kind, value, reason, source=None):
    if not value:
        return
    conn.execute("INSERT OR IGNORE INTO suppression(kind,value,reason,source,created_at) VALUES (?,?,?,?,?)",
                 (kind, value.strip().lower(), reason, source, db.now_iso()))


def suppressed(conn, lead_id: str, email: str | None = None) -> list[str]:
    l = db.lead(conn, lead_id)
    keys = []
    if email:
        e = email.strip().lower()
        keys += [("email", e)]
        dom = e.split("@")[-1]
        if dom not in FREEMAIL:
            keys += [("domain", dom), ("domain", resolve.root_domain(dom))]
    for r in conn.execute("SELECT domain FROM domains WHERE lead_id=?", (lead_id,)):
        keys.append(("domain", r["domain"]))
    if l["company_number"]:
        keys.append(("company", l["company_number"].lower()))
    if l["buying_team_key"]:
        keys.append(("team", l["buying_team_key"].lower()))
    hits = []
    for kind, val in keys:
        r = conn.execute("SELECT reason FROM suppression WHERE kind=? AND value=?", (kind, val)).fetchone()
        if r:
            hits.append(f"{kind}:{val} ({r['reason']})")
    return hits


# ---------------------------------------------------------------- gates
def best_email(conn, lead_id):
    return conn.execute(
        "SELECT * FROM contacts WHERE lead_id=? AND channel='email' AND status='ok' "
        "ORDER BY CASE published_on WHEN 'own_site' THEN 0 WHEN 'official_listing' THEN 1 ELSE 2 END LIMIT 1",
        (lead_id,)).fetchone()


def run_gates(conn, cfg, lead_id: str):
    l = db.lead(conn, lead_id)
    ts = db.now_iso()
    res = []

    def gate(name, passed, detail, hard=False):
        res.append((name, bool(passed), detail, hard))
        conn.execute("INSERT OR REPLACE INTO gate_results(lead_id,gate,passed,detail,checked_at) VALUES (?,?,?,?,?)",
                     (lead_id, name, int(bool(passed)), detail, ts))

    dom = l["canonical_domain"]
    gate("first_party_site", dom and not resolve.is_directory(dom, cfg),
         dom or "no canonical domain", hard=True)

    st = (l["entity_status"] or "unknown").lower()
    gate("entity_active", st == "active", f"status={st} source={l['entity_source_url']}",
         hard=st in ("dissolved", "liquidation", "closed"))

    et = (l["entity_type"] or "unknown").lower()
    if l["country"] in ("UK", "IE"):
        ok = et in CORPORATE and bool(l["company_number"]) and bool(l["entity_source_url"])
        if et in ("sole_trader", "partnership"):
            detail = f"{et}: individual subscriber under PECR - email needs prior consent; route to call list (check TPS/CTPS)"
            gate("corporate_subscriber", False, detail, hard=True)
        else:
            gate("corporate_subscriber", ok,
                 f"entity={et} company_number={l['company_number']} source={l['entity_source_url']}")
    else:
        gate("corporate_subscriber", False, f"country {l['country']} not configured for email", hard=True)

    em = best_email(conn, lead_id)
    if em is None:
        gate("published_contact", False, "no published business email")
    else:
        ok = (em["provenance"] == "published" and em["published_on"] in ("own_site", "official_listing")
              and bool(em["published_url"]))
        gate("published_contact", ok,
             f"{em['address']} provenance={em['provenance']} on={em['published_on']} url={em['published_url']}",
             hard=em["provenance"] == "estimated")

    hits = suppressed(conn, lead_id, em["address"] if em else None)
    gate("not_suppressed", not hits, "; ".join(hits) or "clear", hard=bool(hits))

    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).date().isoformat()
    sig = conn.execute("SELECT strength, observed_date FROM trading_evidence WHERE lead_id=?", (lead_id,)).fetchall()
    strong = [s for s in sig if s["strength"] == "strong" and (s["observed_date"] or "") >= cutoff]
    weak = [s for s in sig if (s["observed_date"] or "") >= cutoff]
    gate("active_trading", strong or len(weak) >= 2, f"{len(strong)} strong / {len(weak)} recent signals")

    evs = conn.execute("SELECT id, issue FROM evidence WHERE lead_id=? AND message_eligible=1", (lead_id,)).fetchall()
    gate("material_issue", bool(evs),
         ", ".join(e["issue"] for e in evs) or "no supported material issue (only weak or no findings)")
    return res


def qualify(conn, cfg, lead_id: str):
    res = run_gates(conn, cfg, lead_id)
    failed = [r for r in res if not r[1]]
    if not failed:
        db.set_state(conn, lead_id, "qualified", "all gates passed")
        return True, []
    hard = [r for r in failed if r[3]]
    reason = "; ".join(f"{n}: {d}" for n, _, d, _ in failed)
    db.set_state(conn, lead_id, "rejected" if hard else "review", reason)
    return False, failed


# ---------------------------------------------------------------- score
def score(conn, cfg, lead_id: str):
    l = db.lead(conn, lead_id)
    camp = next(c for c in cfg["campaigns"] if c["id"] == l["campaign"])
    evs = conn.execute("SELECT * FROM evidence WHERE lead_id=? AND message_eligible=1 ORDER BY severity DESC",
                       (lead_id,)).fetchall()
    reasons = []
    sev = 0
    if evs:
        sev = min(40, evs[0]["severity"] + (4 if len(evs) > 1 else 0))
        reasons.append(f"severity: {evs[0]['issue']} ({evs[0]['severity']})" + (" +second issue" if len(evs) > 1 else ""))
    eq = 0
    if evs:
        top = evs[0]
        eq = {"high": 22, "medium": 15, "low": 5}.get(top["confidence"], 0)
        steps = json.loads(top["steps"] or "[]")
        if len(steps) >= 3:
            eq += 3
        reasons.append(f"evidence: {top['confidence']} via {top['method']}, {len(steps)} steps")
    eq = min(25, eq)
    sig = conn.execute("SELECT strength FROM trading_evidence WHERE lead_id=?", (lead_id,)).fetchall()
    trading = min(10, 4 * sum(1 for s in sig if s["strength"] == "strong") + sum(1 for s in sig if s["strength"] != "strong"))
    vt = min(20, camp.get("service_value", 5) + trading)
    reasons.append(f"value/trading: service {camp.get('service_value')} + trading {trading}")
    conv = any(e["kind"] == "conversion" for e in evs)
    fit = (10 if camp.get("proof") else 4) + (5 if conv else 2 if evs else 0)
    reasons.append(f"fit: proof {camp['proof']['name'] if camp.get('proof') else 'none'}, scopable fix {'yes' if evs else 'no'}")
    total = sev + eq + vt + fit
    th = cfg["scoring"]
    queue = "high" if total >= th["high_threshold"] else "standard" if total >= th["standard_threshold"] else "review"
    conn.execute("INSERT OR REPLACE INTO scores(lead_id,severity,evidence_quality,value_trading,fit,total,queue,reasons,scored_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?)", (lead_id, sev, eq, vt, fit, total, queue, json.dumps(reasons), db.now_iso()))
    if queue == "review":
        db.set_state(conn, lead_id, "review", f"score {total} below standard threshold")
    else:
        db.set_state(conn, lead_id, "prioritised", f"score {total} -> {queue}")
    return total, queue
