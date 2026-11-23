"""Funnel and bottleneck reporting by niche, area, issue and offer."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from . import discover

FUNNEL = ["discovered", "audited", "qualified", "drafted", "sent", "positive_replies", "booked_calls",
          "quotes", "wins", "booked_revenue", "paid_revenue"]
REACHED = {
    "audited": {"audited", "qualified", "prioritised", "drafted", "in_sequence", "stopped", "won"},
    "qualified": {"qualified", "prioritised", "drafted", "in_sequence", "stopped", "won"},
    "drafted": {"drafted", "in_sequence", "stopped", "won"},
}


def funnel(conn, by="niche"):
    rows = defaultdict(lambda: Counter())
    leads = conn.execute("SELECT * FROM leads WHERE merged_into IS NULL").fetchall()
    for l in leads:
        top = conn.execute("SELECT issue FROM evidence WHERE lead_id=? AND message_eligible=1 ORDER BY severity DESC LIMIT 1",
                           (l["id"],)).fetchone()
        msg = conn.execute("SELECT offer_variant FROM messages WHERE lead_id=? AND step=1 LIMIT 1", (l["id"],)).fetchone()
        key = {"niche": l["niche"], "area": l["town"], "issue": top["issue"] if top else "-",
               "offer": msg["offer_variant"] if msg else "-", "campaign": l["campaign"]}[by] or "-"
        c = rows[key]
        c["discovered"] += 1
        was_audited = conn.execute("SELECT 1 FROM events WHERE lead_id=? AND type='state' AND detail LIKE '%\"to\": \"audited\"%'",
                                   (l["id"],)).fetchone()
        for stage, states in REACHED.items():
            if l["state"] in states or (stage == "audited" and was_audited):
                c[stage] += 1
        if conn.execute("SELECT 1 FROM messages WHERE lead_id=? AND state='sent'", (l["id"],)).fetchone():
            c["sent"] += 1
        for et, name in [("positive_reply", "positive_replies"), ("booked_call", "booked_calls"),
                         ("quote_sent", "quotes"), ("won", "wins")]:
            if conn.execute("SELECT 1 FROM events WHERE lead_id=? AND type=?", (l["id"], et)).fetchone():
                c[name] += 1
        for et, name in [("won", "booked_revenue"), ("paid", "paid_revenue")]:
            v = conn.execute("SELECT COALESCE(SUM(value),0) v FROM events WHERE lead_id=? AND type=?", (l["id"], et)).fetchone()["v"]
            c[name] += v
    return {k: {f: v.get(f, 0) for f in FUNNEL} for k, v in rows.items()}


def rejection_reasons(conn):
    c = Counter()
    for r in conn.execute("SELECT gate, detail FROM gate_results WHERE passed=0"):
        c[r["gate"]] += 1
    for r in conn.execute("SELECT state_reason FROM leads WHERE state IN ('rejected','review','retry') AND merged_into IS NULL"):
        c["state: " + (r["state_reason"] or "?").split(":")[0][:60]] += 1
    return c.most_common()


def lead_table(conn):
    out = []
    for l in conn.execute("SELECT * FROM leads WHERE merged_into IS NULL ORDER BY campaign, state, trading_name"):
        s = conn.execute("SELECT total, queue FROM scores WHERE lead_id=?", (l["id"],)).fetchone()
        gates = {g["gate"]: (bool(g["passed"]), g["detail"]) for g in
                 conn.execute("SELECT * FROM gate_results WHERE lead_id=?", (l["id"],))}
        ev = [dict(e) for e in conn.execute(
            "SELECT issue, plain_observation, source_url, observed_at, method, confidence, message_eligible, ineligible_reason "
            "FROM evidence WHERE lead_id=? ORDER BY severity DESC", (l["id"],))]
        msgs = [dict(m) for m in conn.execute("SELECT id, step, state, state_reason, subject, body, to_address "
                                               "FROM messages WHERE lead_id=? ORDER BY step", (l["id"],))]
        out.append({"lead": l["id"], "name": l["trading_name"], "domain": l["canonical_domain"], "town": l["town"],
                    "state": l["state"], "reason": l["state_reason"], "score": dict(s) if s else None,
                    "gates": gates, "evidence": ev, "messages": msgs})
    return out


def text_report(conn):
    lines = ["# Pipeline report", "", "## Funnel by campaign"]
    for k, v in funnel(conn, "campaign").items():
        lines.append(f"- **{k}**: " + ", ".join(f"{f} {v[f]}" for f in FUNNEL))
    lines += ["", "## Funnel by issue"]
    for k, v in funnel(conn, "issue").items():
        lines.append(f"- {k}: discovered {v['discovered']}, drafted {v['drafted']}, sent {v['sent']}, positive {v['positive_replies']}")
    lines += ["", "## Rejection / hold reasons"]
    for reason, n in rejection_reasons(conn):
        lines.append(f"- {reason}: {n}")
    dry = discover.dry_segments(conn, min_runs=1)
    lines += ["", "## Searches running dry (no new leads)"]
    lines += [f"- {d['campaign']} / {d['town']} / {d['service']}: {d['runs']} runs, {d['directory']} directory hits, "
              f"{d['first_party']} first-party" for d in dry] or ["- none"]
    h = conn.execute("SELECT * FROM handoffs WHERE done=0").fetchall()
    lines += ["", "## Needs Emmanuel"] + ([f"- {json.loads(x['summary'])['business']}: {x['reason']}" for x in h] or ["- nothing"])
    return "\n".join(lines)
