"""Discovery: service x town x niche search batches, result import, dry-segment tracking.

Search itself is performed by the runtime agent (WebSearch / Companies House /
directory pages) or a configured API. This module plans the batches, records
which search found each business, and turns directory listings into leads
that still need a first-party domain resolved instead of dropping them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import db, resolve


def plan_queries(conn, cfg, campaign_id: str, include_expansion=False, limit=None):
    camp = next(c for c in cfg["campaigns"] if c["id"] == campaign_id)
    towns = list(camp["towns"]) + (camp.get("expansion_towns", []) if include_expansion else [])
    skip_days = cfg["discovery"]["skip_empty_query_days"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=skip_days)).isoformat()
    out = []
    for town in towns:
        for service in camp["services"]:
            q = f"{service} {town}"
            prev = conn.execute(
                "SELECT MAX(page) p, SUM(new_leads) n, MAX(run_at) r FROM search_queries "
                "WHERE campaign=? AND query=? AND run_at>=?", (campaign_id, q, cutoff)).fetchone()
            if prev["r"] is not None and (prev["n"] or 0) == 0:
                continue  # ran recently and found nothing new: don't repeat an empty search
            page = (prev["p"] or 0) + 1 if prev["r"] else 1
            if page > cfg["discovery"]["max_pages_per_query"]:
                continue
            out.append({"campaign": campaign_id, "niche": camp["niche"], "service": service,
                        "town": town, "query": q, "page": page})
    return out[:limit] if limit else out


def import_search(conn, cfg, payload: dict):
    """payload: {campaign, niche, service, town, query, source, page,
                 results: [{url, title, name?, phone?, company_number?}]}"""
    ts = db.now_iso()
    cur = conn.execute(
        "INSERT INTO search_queries(campaign,niche,service,town,query,source,page,run_at,results_count) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (payload["campaign"], payload.get("niche"), payload.get("service"), payload.get("town"),
         payload["query"], payload.get("source", "websearch"), payload.get("page", 1), ts,
         len(payload.get("results", []))))
    qid = cur.lastrowid
    fp = dr = new = 0
    for r in payload.get("results", []):
        url = r.get("url", "")
        kind = "directory" if resolve.is_directory(url, cfg) else "first_party"
        before = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        if kind == "first_party":
            fp += 1
            lid = resolve.upsert_lead(conn, campaign=payload["campaign"], niche=payload["niche"],
                                      name=r.get("name") or r.get("title"), domain=url, phone=r.get("phone"),
                                      company_number=r.get("company_number"), town=payload.get("town"))
        else:
            dr += 1
            if not r.get("name"):
                # a directory *search page* (list of firms) rather than one firm's profile
                conn.execute("INSERT INTO discoveries(lead_id,query_id,source_url,raw_name,kind,found_at) "
                             "VALUES (NULL,?,?,?,?,?)", (qid, url, r.get("title"), "directory_list", ts))
                continue
            lid = resolve.upsert_lead(conn, campaign=payload["campaign"], niche=payload["niche"],
                                      name=r["name"], phone=r.get("phone"),
                                      company_number=r.get("company_number"), town=payload.get("town"))
            l = db.lead(conn, lid)
            if l["state"] == "discovered" and not l["canonical_domain"]:
                conn.execute("UPDATE leads SET state_reason='needs_domain_resolution' WHERE id=?", (lid,))
        if conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"] > before:
            new += 1
        conn.execute("INSERT INTO discoveries(lead_id,query_id,source_url,raw_name,kind,found_at) VALUES (?,?,?,?,?,?)",
                     (lid, qid, url, r.get("name") or r.get("title"), kind, ts))
    conn.execute("UPDATE search_queries SET first_party=?, directory=?, new_leads=? WHERE id=?", (fp, dr, new, qid))
    return {"query_id": qid, "first_party": fp, "directory": dr, "new_leads": new}


def import_resolution(conn, cfg, lead_id: str, rec: dict):
    """Result of resolving a business to its real site and entity.

    rec: {domain?, alias_domains?, no_first_party_site?: bool, company_number?, legal_name?, entity_type?,
          entity_status?, entity_source_url?, phone?, parked?: bool, identity_uncertain?: str}
    """
    l = db.lead(conn, lead_id)
    if rec.get("domain") and resolve.is_directory(rec["domain"], cfg):
        rec = {**rec, "domain": None, "no_first_party_site": True}
    lid = resolve.upsert_lead(conn, campaign=l["campaign"], niche=l["niche"], name=l["trading_name"],
                              domain=rec.get("domain"), phone=rec.get("phone"),
                              company_number=rec.get("company_number"), town=l["town"],
                              alias_domains=rec.get("alias_domains", ()))
    if lid != lead_id:
        resolve.merge(conn, lid, lead_id, "resolution matched existing team")
    sets = {k: rec[k] for k in ("legal_name", "entity_type", "entity_status", "entity_source_url") if rec.get(k)}
    if sets:
        sets["entity_checked_at"] = db.now_iso()
        conn.execute("UPDATE leads SET %s WHERE id=?" % ",".join(f"{k}=?" for k in sets), (*sets.values(), lid))
    l = db.lead(conn, lid)
    from . import qualify  # local import: qualify depends on resolve
    hits = qualify.suppressed(conn, lid)
    if hits:
        db.set_state(conn, lid, "rejected", "existing contact / suppressed: " + "; ".join(hits))
    elif rec.get("entity_status") in ("dissolved", "liquidation", "closed"):
        db.set_state(conn, lid, "rejected", f"business not active: {rec['entity_status']}")
    elif rec.get("parked"):
        db.set_state(conn, lid, "rejected", "parked domain")
    elif rec.get("no_first_party_site") or not l["canonical_domain"]:
        db.set_state(conn, lid, "rejected", "no first-party site (directory/social only) - outside core campaign")
    elif rec.get("identity_uncertain"):
        db.set_state(conn, lid, "review", f"identity uncertain: {rec['identity_uncertain']}")
    elif l["state"] in ("discovered", "retry", "review"):
        db.set_state(conn, lid, "resolved")
    return lid


def dry_segments(conn, min_runs=2):
    """Campaign/town/service combinations that keep returning nothing usable."""
    return [dict(r) for r in conn.execute(
        "SELECT campaign, town, service, COUNT(*) runs, SUM(results_count) results, SUM(first_party) first_party, "
        "SUM(directory) directory, SUM(new_leads) new_leads FROM search_queries GROUP BY campaign, town, service "
        "HAVING runs>=? AND SUM(new_leads)=0 ORDER BY runs DESC", (min_runs,))]
