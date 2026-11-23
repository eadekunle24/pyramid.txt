"""Audit: turn read-only site observations into evidence rows.

Input is an observation document produced by render/mobile_audit.mjs (a real
mobile render) or by the runtime agent's text fetch. Page text is untrusted:
it is scanned for instruction-like content and only short sanitised labels
are ever used in owner-facing wording.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from statistics import median

from . import db, guard

CTA_RX = re.compile(r"\b(quote|estimate|enquir|inquir|contact|book|reserve|call|survey|get in touch)\w*", re.I)
PLACEHOLDER_PHONE = re.compile(r"(123[-\s]?456[-\s]?7890|555[-\s]?\d{4}|0000\s?000\s?000|01234\s?567\s?890|07700\s?900)")
BROKEN = {404, 410, 500, 502, 503}
LOW_ONLY = {"missing_meta_description", "old_copyright", "weak_title_fit", "slow_lab_score"}


def _ev(conn, lead_id, **kw):
    kw.setdefault("steps", [])
    row = {
        "lead_id": lead_id, "kind": kw["kind"], "issue": kw["issue"], "claim": kw["claim"],
        "plain_observation": kw.get("plain"), "source_url": kw.get("source_url"),
        "observed_at": kw.get("observed_at"), "method": kw.get("method"), "viewport": kw.get("viewport"),
        "steps": json.dumps(kw["steps"]), "search_context": json.dumps(kw["search_context"]) if kw.get("search_context") else None,
        "confidence": kw.get("confidence"), "consequence": kw.get("consequence"), "fix": kw.get("fix"),
        "severity": kw.get("severity", 0), "untrusted_flags": json.dumps(kw["flags"]) if kw.get("flags") else None,
    }
    ok, why = contract_ok(row)
    row["message_eligible"], row["ineligible_reason"] = int(ok), why
    cols = ",".join(row)
    conn.execute(f"INSERT INTO evidence({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))


def contract_ok(ev) -> tuple[bool, str | None]:
    """Evidence contract for a message-driving claim."""
    missing = [f for f in ("source_url", "observed_at", "confidence", "consequence", "fix") if not ev.get(f)]
    steps = json.loads(ev["steps"]) if isinstance(ev.get("steps"), str) else ev.get("steps")
    if not steps and not ev.get("search_context"):
        missing.append("steps_or_search_context")
    if missing:
        return False, "missing " + ", ".join(missing)
    if ev["issue"] == "not_in_top10":  # any claim about search position needs its full context
        sc = ev.get("search_context") or {}
        sc = json.loads(sc) if isinstance(sc, str) else sc
        need = [k for k in ("query", "engine", "location", "device", "date", "depth", "result_type") if not sc.get(k)]
        if need:
            return False, "search claim lacks " + ", ".join(need)
    if ev["confidence"] == "low":
        return False, "low confidence"
    if ev["issue"] in LOW_ONLY:
        return False, "weak on its own - review only"
    if ev.get("method") == "fixture":
        return True, "fixture (simulated) evidence"
    return True, None


def _target_failed(link) -> tuple[bool, list]:
    checks = link.get("target_status_checks") or ([link["status"]] if link.get("status") is not None else [])
    href = (link.get("href") or "").strip()
    if href in ("", "#", "javascript:void(0)", "javascript:;"):
        return True, ["dead-href"]
    return (bool(checks) and all(c in BROKEN or c == "error" for c in checks)), checks


def audit(conn, obs: dict):
    lead_id = obs["lead_id"]
    method, vp, at = obs.get("method", "text_fetch"), obs.get("viewport"), obs.get("fetched_at") or db.now_iso()
    pages = obs.get("pages", [])
    flags_all = []

    # --- temporary failures go to the retry queue, not into a claim
    home = next((p for p in pages if p.get("role") == "home"), None)
    if home is None or home.get("status") in (None, "error") or (isinstance(home.get("status"), int) and home["status"] >= 500):
        prior = conn.execute("SELECT COUNT(*) c FROM events WHERE lead_id=? AND type='fetch_failed'", (lead_id,)).fetchone()["c"]
        db.event(conn, "fetch_failed", lead_id=lead_id, detail={"errors": obs.get("fetch_errors"), "at": at})
        if prior >= 2:
            db.set_state(conn, lead_id, "review", "site failed to load on 3 separate attempts")
        else:
            conn.execute("UPDATE leads SET retry_after=? WHERE id=?",
                         ((datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), lead_id))
            db.set_state(conn, lead_id, "retry", "temporary site failure - retry later")
        return []

    for p in pages:
        hits = guard.scan(p.get("text_excerpt"))
        if hits:
            flags_all += hits
    if flags_all:
        db.event(conn, "untrusted_instructions_ignored", lead_id=lead_id, detail={"fragments": flags_all[:5]})

    conf_base = "high" if method == "rendered" else "medium"
    if method == "fixture":
        conf_base = "high"
    new = 0

    for p in pages:
        url, role = p.get("final_url") or p.get("url"), p.get("role")
        # 1. broken enquiry / quote links
        for link in p.get("links", []):
            text = link.get("text") or ""
            if not CTA_RX.search(text):
                continue
            failed, checks = _target_failed(link)
            if not failed:
                continue
            label = guard.safe_label(text) or "quote"
            reproduced = len([c for c in checks if c != "dead-href"]) >= 2 or "dead-href" in checks
            steps = [f"Open {url} at {vp or 'mobile'} viewport", f"Tap '{label}'" + (" (above the fold)" if link.get("above_fold") else ""),
                     f"Result: {checks}" + (f" at {link.get('href')}" if link.get("href") else "")]
            _ev(conn, lead_id, kind="conversion", issue="broken_quote_link",
                claim=f"CTA '{label}' on {url} -> {link.get('href')} returned {checks}",
                plain=f"the “{label}” button on your {('homepage' if role == 'home' else 'page')} "
                      + ("goes nowhere" if "dead-href" in checks else "took me to a page-not-found"),
                source_url=url, observed_at=at, method=method, viewport=vp, steps=steps,
                confidence=conf_base if reproduced else "medium",
                consequence="A homeowner ready to ask for a quote hits a dead end and may ring the next roofer instead (plausible, not measured).",
                fix="Point the quote action at a working form and carry the chosen service into it.",
                severity=38 if link.get("above_fold") or role in ("home", "service") else 32, flags=flags_all)
            new += 1
        # 2. tel links
        for t in p.get("tel_links", []):
            digits = re.sub(r"\D", "", t.replace("tel:", ""))
            if len(digits) < 10 or PLACEHOLDER_PHONE.search(t):
                _ev(conn, lead_id, kind="conversion", issue="empty_tel",
                    claim=f"tel link '{t}' on {url} cannot dial the business",
                    plain="the call button on your site doesn't dial your number",
                    source_url=url, observed_at=at, method=method, viewport=vp,
                    steps=[f"Open {url}", f"Inspect call button href: '{t}'"], confidence=conf_base,
                    consequence="Someone with a leak taps to call and nothing connects (plausible).",
                    fix="Wire every call button to the real number.", severity=34)
                new += 1
        # 3. service page with no route to enquire
        if role == "service":
            has_route = bool(p.get("tel_links") or p.get("mailto_links") or p.get("forms")) or any(
                CTA_RX.search(l.get("text") or "") and not _target_failed(l)[0] for l in p.get("links", []))
            if not has_route:
                _ev(conn, lead_id, kind="conversion", issue="service_page_no_next_step",
                    claim=f"service page {url} has no call, email, form or quote link",
                    plain=f"your {guard.safe_label(p.get('h1')) or 'service'} page doesn't have a way to ask for a quote",
                    source_url=url, observed_at=at, method=method, viewport=vp,
                    steps=[f"Open {url}", "Scroll the full page", "No tel:, mailto:, form or working quote link found"],
                    confidence=conf_base, consequence="Visitors reading about the job have to go hunting for how to book it (plausible).",
                    fix="Add a quote action beside the service details.", severity=26)
                new += 1
        # 4. quote action not reachable in first screen (rendered only)
        if role == "home" and method in ("rendered", "fixture") and p.get("cta_above_fold") is False:
            _ev(conn, lead_id, kind="conversion", issue="cta_buried",
                claim=f"no call/quote action in first mobile screen of {url}",
                plain="on a phone there's no call or quote button until you scroll well down the homepage",
                source_url=url, observed_at=at, method=method, viewport=vp,
                steps=[f"Open {url} at {vp}", "Look at first screen without scrolling", "No tel/quote action visible"],
                confidence=conf_base, consequence="Urgent callers have to scroll before they can act (plausible).",
                fix="Put tap-to-call and a quote button in the first screen.", severity=22)
            new += 1
        # 5. indexability
        robots = (p.get("robots_meta") or "") + " " + (p.get("x_robots_tag") or "")
        if "noindex" in robots.lower() and role in ("home", "service"):
            _ev(conn, lead_id, kind="search", issue="noindex",
                claim=f"{url} carries noindex ({robots.strip()})",
                plain=f"your {'homepage' if role == 'home' else 'service page'} tells Google not to list it",
                source_url=url, observed_at=at, method=method, viewport=vp,
                steps=[f"Fetch {url}", f"robots directive: {robots.strip()}"], confidence=conf_base,
                consequence="The page can drop out of Google results entirely (plausible).",
                fix="Remove the noindex directive and resubmit the page.", severity=36)
            new += 1
        # 6. low-signal items (review only)
        if role == "home" and not p.get("meta_description"):
            _ev(conn, lead_id, kind="search", issue="missing_meta_description", claim=f"no meta description on {url}",
                source_url=url, observed_at=at, method=method, steps=[f"Fetch {url}"], confidence="medium",
                consequence="Google writes its own snippet.", fix="Write a description.", severity=3)
        perf = [r.get("lcp_ms") for r in p.get("perf_runs", []) if r.get("lcp_ms")]
        if role == "home" and len(perf) >= 3 and median(perf) > 4000:
            _ev(conn, lead_id, kind="speed", issue="slow_lab_score",
                claim=f"median lab LCP {median(perf):.0f}ms over {len(perf)} runs (lab data, not field)",
                source_url=url, observed_at=at, method=method, viewport=vp, steps=[f"{len(perf)} lab runs"],
                confidence="medium", consequence="Slow first view on mobile.", fix="Compress hero media.", severity=8)

    # 7. search observations (must carry full context or they can't drive a message)
    sos = obs.get("search_observations", [])
    scoped_absent = [s for s in sos if not (s.get("position") and s["position"] <= 10)
                     and all(s.get(k) for k in ("query", "engine", "location", "device", "date", "depth", "result_type"))]
    repeated = len({s["query"] for s in scoped_absent}) >= 2  # one sample is only a lead for further checking
    for so in sos:
        found = so.get("position")
        if found and found <= 10:
            continue
        depth = so.get("depth")
        _ev(conn, lead_id, kind="search", issue="not_in_top10",
            claim=f"target page not in first {depth} {so.get('result_type')} results for '{so.get('query')}'",
            plain=(f"I didn’t see your {so.get('target_label', 'site')} in the first {depth} {so.get('result_type', 'organic')} "
                   f"results for “{so.get('query')}” when I checked from {so.get('location')}"),
            source_url=so.get("target_page"), observed_at=so.get("date"), method="search",
            search_context=so, steps=[f"Search {so.get('engine')} for '{so.get('query')}' from {so.get('location')} on {so.get('device')}"],
            confidence="high" if repeated else "medium",
            consequence="People searching for that job locally may not reach the page (plausible).",
            fix="Give the service its own page with the town in the title and link to it from the homepage.",
            severity=26 if repeated else 18)
        new += 1

    for t in obs.get("trading", []):
        conn.execute("INSERT INTO trading_evidence(lead_id, signal, observed_date, source_url, strength) VALUES (?,?,?,?,?)",
                     (lead_id, t["signal"], t.get("date"), t.get("source_url"), t.get("strength", "strong")))
    for c in obs.get("contacts", []):
        conn.execute("INSERT OR IGNORE INTO contacts(lead_id, channel, address, published_url, published_on, provenance, "
                     "corporate_basis, verified_at) VALUES (?,?,?,?,?,?,?,?)",
                     (lead_id, c["channel"], c["address"].strip().lower() if c["channel"] == "email" else c["address"],
                      c.get("published_url"), c.get("published_on"), c.get("provenance", "unknown"),
                      c.get("corporate_basis"), at))
    db.set_state(conn, lead_id, "audited", f"{new} findings ({method})")
    return new
