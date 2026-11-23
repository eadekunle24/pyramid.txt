"""Pilot run for 2026-11-23: roofing, Manchester & Salford.

REAL inputs:   searches_2026-11-23.json (WebSearch results from this session),
               resolutions below (what those searches established about each firm),
               fetch outcomes (every prospect fetch failed: this cloud session's network
               blocks prospect hosts), suppression_seed.csv (existing logs + Gmail).
SIMULATED:     one lead "Fixture Roofing Ltd (SIMULATED)" audited from a real Playwright
               render of render/fixture_site served on localhost. Its evidence is
               method=fixture, so release() will never send it.

Run:  python3 pilot/run_pilot.py   -> writes pilot/PILOT_OUTPUT.md and data/pilot.db
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from emanoutreach import db, discover, pipeline, qualify, release, report  # noqa: E402

CFG = json.loads((ROOT / "config" / "campaigns.json").read_text())
DBP = ROOT / "data" / "pilot.db"
DBP.parent.mkdir(exist_ok=True)
if DBP.exists():
    DBP.unlink()
conn = db.connect(DBP)

# 1. suppression history
import csv  # noqa: E402
with open(ROOT / "pilot" / "suppression_seed.csv") as f:
    for r in csv.DictReader(f):
        qualify.suppress(conn, r["kind"], r["value"], r["reason"], r["source"])

# 2. discovery (real search results)
for payload in json.loads((ROOT / "pilot" / "searches_2026-11-23.json").read_text()):
    discover.import_search(conn, CFG, payload)
conn.commit()


def by_name(name):
    r = conn.execute("SELECT id FROM leads WHERE trading_name=? AND merged_into IS NULL", (name,)).fetchone()
    return r["id"] if r else None


SRC = "WebSearch 2026-11-23 (this session)"
RESOLUTIONS = {
    "TCB Roofing & Building Ltd": {"no_first_party_site": True, "_why": "only directory listings + Facebook found; Checkatrade lists Darwen"},
    "AK Roofing Specialists Ltd": {"domain": "akroofingspecialists.co.uk"},
    "PM & Sons Roofing Specialists Ltd": {"domain": "pmandsonsroofing.co.uk"},
    "Kearneys Driveways & Roofing Ltd": {"no_first_party_site": True, "_why": "Checkatrade profile only; Rochdale/HD7"},
    "Forever Last Roofing Ltd": {"no_first_party_site": True, "_why": "TrustATrader listings only"},
    "Moston Roofing Ltd": {"company_number": "10769531", "no_first_party_site": True,
                           "_why": "company number via Five Star Roofline; no own domain found in search"},
    "Manchester Roofing & Guttering Ltd": {"identity_uncertain": "same trading name on a Bridgwater (Somerset) Rated People profile; no Companies House match found",
                                           "domain": None},
    "High Tech Roofing NW Limited": {"domain": "hightechroofing.co.uk", "company_number": "08676755", "entity_type": "ltd",
                                     "legal_name": "High Tech Roofing NW Limited", "entity_status": "unknown",
                                     "entity_source_url": "https://hightechroofing.co.uk/ (footer, via search snippet)"},
    "Urmston Roofing": {"domain": "urmstonroofing.co.uk"},
    "Atlas Roofing & Building Services": {"domain": "atlas-roofbuild.com"},
    "Dawn Roofs Ltd": {"domain": "dawnroofsltd.co.uk"},
    "Manchester Flat Roofing": {"domain": "manchesterflatroofing.co.uk"},
    "Complete Roofing Services (Stretford page)": {"domain": "roofersalford.uk", "alias_domains": ["roofing-manchester.uk"],
                                                    "identity_uncertain": "two near-identical templated sites sharing one phone number; possibly a lead-gen network, not a roofer"},
}
notes = {}
for name, rec in RESOLUTIONS.items():
    lid = by_name(name)
    if not lid:
        continue
    if rec.get("domain") is None and "domain" in rec and rec.get("identity_uncertain"):
        db.set_state(conn, lid, "review", "identity uncertain: " + rec["identity_uncertain"])
        continue
    rec = {k: v for k, v in rec.items() if not k.startswith("_")}
    discover.import_resolution(conn, CFG, lid, rec)
conn.commit()

# 3. audit: real fetch outcomes (all blocked by this session's network policy)
FETCH_ERR = "getaddrinfo ENOTFOUND (cloud session network blocks prospect hosts) 2026-11-23"
obs = [{"lead_id": l["id"], "method": "text_fetch", "fetched_at": db.now_iso(),
        "pages": [{"role": "home", "url": f"https://{l['canonical_domain']}/", "status": "error"}],
        "fetch_errors": [{"url": l["canonical_domain"], "error": FETCH_ERR}]}
       for l in db.live_leads(conn, ["resolved"])]
pipeline.run_audits(conn, obs)

# 4. SIMULATED lead from a real render of the local fixture site
fixture_obs_path = ROOT / "pilot" / "out" / "fixture_obs.json"
srv = None
if not fixture_obs_path.exists():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=ROOT / "render" / "fixture_site",
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import time; time.sleep(1)  # noqa: E702
    (ROOT / "pilot" / "out").mkdir(exist_ok=True)
    with open(fixture_obs_path, "w") as f:
        subprocess.run(["node", "render/mobile_audit.mjs", "SIM", "http://127.0.0.1:8765/",
                        "http://127.0.0.1:8765/services/flat-roofing.html"], cwd=ROOT, stdout=f, check=True)
    srv.terminate()
sim = discover.import_search(conn, CFG, {"campaign": "roofing-gm", "niche": "roofing", "service": "flat roof repairs",
                                         "town": "Salford", "query": "SIMULATED fixture", "source": "fixture",
                                         "results": [{"url": "https://fixture-roofing.example/", "name": "Fixture Roofing Ltd (SIMULATED)"}]})
sim_id = by_name("Fixture Roofing Ltd (SIMULATED)")
discover.import_resolution(conn, CFG, sim_id, {"domain": "fixture-roofing.example", "company_number": "99999999",
                                               "entity_type": "ltd", "entity_status": "active",
                                               "entity_source_url": "SIMULATED Companies House record"})
o = json.loads(fixture_obs_path.read_text())
o["lead_id"], o["method"] = sim_id, "fixture"
o["trading"] = [{"signal": "SIMULATED: project post dated last month", "date": db.now_iso()[:10], "source_url": "fixture", "strength": "strong"}]
o["contacts"] = [{"channel": "email", "address": "info@fixture-roofing.example", "published_url": "https://fixture-roofing.example/contact",
                  "published_on": "own_site", "provenance": "published", "corporate_basis": "SIMULATED ltd 99999999"}]
pipeline.run_audits(conn, [o])
pipeline.advance(conn, CFG)
conn.commit()

# 5. release check with the shipped config (mode off) -> must stay gated
rel = release.release(conn, CFG, release.HandoffProvider())

# 6. write output
rows = report.lead_table(conn)
md = ["# Pilot output: roofing, Manchester & Salford (2026-11-23)", "",
      "Discovery inputs are REAL (WebSearch from this session). Site audits of real prospects were BLOCKED: this cloud",
      "session's network policy refuses prospect hosts (DNS ENOTFOUND), so those leads sit in the retry queue.",
      "One lead marked SIMULATED was audited from a real Playwright render of a local fixture site.", "",
      f"Release check with shipped config: **{rel['status']}**", "",
      "| Business | Domain | State | Reason | Score |", "|---|---|---|---|---|"]
for r in rows:
    sc = f"{r['score']['total']} ({r['score']['queue']})" if r["score"] else ""
    md.append(f"| {r['name']} | {r['domain'] or ''} | {r['state']} | {(r['reason'] or '').replace('|', '/')[:150]} | {sc} |")
for r in rows:
    if r["messages"]:
        md += ["", f"## Draft for {r['name']}", "", "Evidence:"]
        for e in r["evidence"]:
            md.append(f"- [{e['issue']}] eligible={bool(e['message_eligible'])} conf={e['confidence']} method={e['method']} "
                      f"src={e['source_url']} ({e['ineligible_reason'] or 'ok'})")
        md.append("")
        for m in r["messages"]:
            md += [f"**Subject:** {m['subject']}  (state: {m['state']})", "", "```", m["body"], "```"]
        md += ["", "Gates:"] + [f"- {g}: {'pass' if p else 'FAIL'} ({d})" for g, (p, d) in r["gates"].items()]
md += ["", report.text_report(conn)]
(ROOT / "pilot" / "PILOT_OUTPUT.md").write_text("\n".join(md) + "\n")
print("\n".join(md))
