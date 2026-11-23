"""Identity resolution: canonical domain, buying-team key, alias folding."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import db

SECOND_LEVEL = {"co", "org", "ltd", "plc", "me", "net", "ac", "gov", "com"}
PARKED_SIGNALS = [
    "this domain is for sale", "buy this domain", "domain parking", "parked free",
    "sedo", "dan.com", "hugedomains", "this domain may be for sale", "godaddy.com/domains",
]


def root_domain(url_or_host: str | None) -> str | None:
    if not url_or_host:
        return None
    s = url_or_host.strip().lower()
    if "://" not in s:
        s = "http://" + s
    host = (urlparse(s).hostname or "").strip(".")
    if not host:
        return None
    parts = host.split(".")
    if parts[0] == "www":
        parts = parts[1:]
    if len(parts) >= 3 and parts[-1] in {"uk", "au", "nz", "ie"} and parts[-2] in SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_directory(url: str, cfg) -> bool:
    d = root_domain(url) or ""
    host = (urlparse(url if "://" in url else "http://" + url).hostname or "").lower()
    for dd in cfg["discovery"]["directory_domains"]:
        if d == dd or host == dd or host.endswith("." + dd):
            return True
    return False


def looks_parked(page_text: str | None) -> bool:
    t = (page_text or "").lower()
    return any(s in t for s in PARKED_SIGNALS)


def norm_phone(p: str | None) -> str | None:
    if not p:
        return None
    digits = re.sub(r"\D", "", p)
    if digits.startswith("44"):
        digits = "0" + digits[2:]
    return digits if len(digits) >= 10 else None


def norm_name(n: str | None) -> str:
    n = re.sub(r"[^a-z0-9& ]+", " ", (n or "").lower())
    n = re.sub(r"\b(ltd|limited|llp|plc|the|and|&)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def norm_company(n: str | None) -> str | None:
    if not n:
        return None
    n = re.sub(r"\s", "", n).upper()
    return n.zfill(8) if n.isdigit() else n


def team_key(company_number=None, domain=None, phone=None, name=None, town=None) -> str:
    if norm_company(company_number):
        return f"company:{norm_company(company_number)}"
    if domain:
        return f"domain:{domain}"
    if norm_phone(phone):
        return f"phone:{norm_phone(phone)}"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{name or ''}-{town or ''}".lower()).strip("-")
    return f"name:{slug}"


def find_existing(conn, domain=None, company_number=None, phone=None, name=None, town=None):
    """Return all live leads that reach the same buying team."""
    hits = {}
    if domain:
        r = conn.execute("SELECT lead_id FROM domains WHERE domain=?", (domain,)).fetchone()
        if r:
            hits[r["lead_id"]] = "domain"
    if norm_company(company_number):
        for r in conn.execute("SELECT id FROM leads WHERE company_number=? AND merged_into IS NULL",
                              (norm_company(company_number),)):
            hits[r["id"]] = "company_number"
    if norm_phone(phone):
        for r in conn.execute("SELECT id, phone FROM leads WHERE merged_into IS NULL AND phone IS NOT NULL"):
            if norm_phone(r["phone"]) == norm_phone(phone):
                hits.setdefault(r["id"], "phone")
    if name and not hits:
        # Same exact business name inside one campaign region (e.g. found via Salford and via Eccles
        # searches) is the same buying team until a registry check says otherwise.
        n = norm_name(name)
        for r in conn.execute("SELECT id, trading_name FROM leads WHERE merged_into IS NULL AND trading_name IS NOT NULL"):
            if norm_name(r["trading_name"]) == n:
                hits[r["id"]] = "same_name"
    # follow merges to the surviving record
    out = {}
    for lid, why in hits.items():
        row = db.lead(conn, lid)
        while row is not None and row["merged_into"]:
            row = db.lead(conn, row["merged_into"])
        if row is not None:
            out[row["id"]] = why
    return out


def merge(conn, keep_id: str, drop_id: str, why: str):
    """Fold drop into keep. Keeps at most one live sequence for the team."""
    if keep_id == drop_id:
        return keep_id
    keep, drop = db.lead(conn, keep_id), db.lead(conn, drop_id)
    for col in ("company_number", "legal_name", "entity_type", "entity_status", "entity_source_url",
                "canonical_domain", "phone", "town", "trading_name"):
        if not keep[col] and drop[col]:
            conn.execute(f"UPDATE leads SET {col}=? WHERE id=?", (drop[col], keep_id))
    for tbl in ("domains", "contacts", "evidence", "discoveries", "trading_evidence"):
        conn.execute(f"UPDATE OR IGNORE {tbl} SET lead_id=? WHERE lead_id=?", (keep_id, drop_id))
    conn.execute("DELETE FROM contacts WHERE lead_id=?", (drop_id,))  # duplicates that failed to move
    # Messages: the surviving team may carry only one live sequence.
    live = ("draft", "approved", "queued", "sending", "unknown", "sent")
    keep_live = conn.execute(
        "SELECT COUNT(*) c FROM messages WHERE lead_id=? AND state IN (%s)" % ",".join("?" * len(live)),
        (keep_id, *live)).fetchone()["c"]
    for m in conn.execute("SELECT * FROM messages WHERE lead_id=?", (drop_id,)).fetchall():
        if m["state"] in ("sent", "sending", "unknown"):
            # Already out (or possibly out): it becomes the team's sequence; cancel keep's unsent ones.
            conn.execute("UPDATE messages SET lead_id=? WHERE id=?", (keep_id, m["id"]))
            conn.execute("UPDATE messages SET state='cancelled', state_reason='team already contacted via alias' "
                         "WHERE lead_id=? AND state IN ('draft','approved','queued') AND id<>?", (keep_id, m["id"]))
        elif keep_live:
            conn.execute("UPDATE messages SET state='cancelled', state_reason='merged duplicate of team' WHERE id=?",
                         (m["id"],))
        else:
            conn.execute("UPDATE messages SET lead_id=? WHERE id=?", (keep_id, m["id"]))
    conn.execute("UPDATE leads SET merged_into=?, state_reason=?, buying_team_key=NULL, updated_at=? WHERE id=?",
                 (keep_id, f"merged: {why}", db.now_iso(), drop_id))
    db.event(conn, "merged", lead_id=keep_id, detail={"dropped": drop_id, "why": why})
    rekey(conn, keep_id)
    return keep_id


def rekey(conn, lead_id: str):
    l = db.lead(conn, lead_id)
    k = team_key(l["company_number"], l["canonical_domain"], l["phone"], l["trading_name"], l["town"])
    other = conn.execute("SELECT id FROM leads WHERE buying_team_key=? AND id<>?", (k, lead_id)).fetchone()
    if other:
        merge(conn, other["id"], lead_id, f"same team key {k}")
        return
    conn.execute("UPDATE leads SET buying_team_key=?, updated_at=? WHERE id=?", (k, db.now_iso(), lead_id))
    conn.execute("UPDATE messages SET buying_team_key=? WHERE lead_id=?", (k, lead_id))


def upsert_lead(conn, *, campaign, niche, name=None, domain=None, phone=None, company_number=None,
                town=None, country="UK", alias_domains=()):
    domain = root_domain(domain) if domain else None
    aliases = [root_domain(a) for a in alias_domains if a]
    existing = {}
    for d in [domain, *aliases]:
        existing.update(find_existing(conn, domain=d))
    existing.update(find_existing(conn, company_number=company_number, phone=phone, name=name, town=town))
    ids = sorted(existing, key=lambda i: conn.execute("SELECT rowid FROM leads WHERE id=?", (i,)).fetchone()[0])
    if ids:
        keep = ids[0]
        for other in ids[1:]:
            merge(conn, keep, other, existing[other])
        lid = keep
        l = db.lead(conn, lid)
        updates = {"trading_name": name, "canonical_domain": domain, "phone": phone,
                   "company_number": norm_company(company_number), "town": town}
        for col, val in updates.items():
            if val and not l[col]:
                conn.execute(f"UPDATE leads SET {col}=? WHERE id=?", (val, lid))
    else:
        lid = db.new_id("lead")
        ts = db.now_iso()
        conn.execute(
            "INSERT INTO leads(id,campaign,niche,trading_name,company_number,country,town,canonical_domain,phone,"
            "buying_team_key,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'discovered', ?, ?)",
            (lid, campaign, niche, name, norm_company(company_number), country, town, domain, phone,
             f"tmp:{lid}", ts, ts))
        db.event(conn, "discovered", lead_id=lid, detail={"name": name, "domain": domain})
    for d, role in [(domain, "canonical"), *[(a, "alias") for a in aliases]]:
        if d:
            conn.execute("INSERT OR IGNORE INTO domains(domain, lead_id, role) VALUES (?,?,?)", (d, lid, role))
    if domain:
        conn.execute("UPDATE domains SET role='alias' WHERE lead_id=? AND domain<>? AND role='canonical'", (lid, domain))
        conn.execute("UPDATE domains SET role='canonical' WHERE domain=?", (domain,))
        if not db.lead(conn, lid)["canonical_domain"]:
            conn.execute("UPDATE leads SET canonical_domain=? WHERE id=?", (domain, lid))
    rekey(conn, lid)
    # rekey may have merged lid into an older team record
    row = db.lead(conn, lid)
    while row["merged_into"]:
        row = db.lead(conn, row["merged_into"])
    return row["id"]
