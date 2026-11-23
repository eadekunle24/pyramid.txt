# Pilot output: roofing, Manchester & Salford (2026-11-23)

Discovery inputs are REAL (WebSearch from this session). Site audits of real prospects were BLOCKED: this cloud
session's network policy refuses prospect hosts (DNS ENOTFOUND), so those leads sit in the retry queue.
One lead marked SIMULATED was audited from a real Playwright render of a local fixture site.

Release check with shipped config: **gated: release mode is off**

| Business | Domain | State | Reason | Score |
|---|---|---|---|---|
| AL Roofing Ltd |  | discovered | needs_domain_resolution |  |
| Bradley Roofing Services |  | discovered | needs_domain_resolution |  |
| FPL Roofing Ltd |  | discovered | needs_domain_resolution |  |
| Manchester Roofing Repairs Ltd |  | discovered | needs_domain_resolution |  |
| Only Roofing Ltd |  | discovered | needs_domain_resolution |  |
| SMV Roofing Ltd |  | discovered | needs_domain_resolution |  |
| Walker Roofing (North West) Ltd |  | discovered | needs_domain_resolution |  |
| Fixture Roofing Ltd (SIMULATED) | fixture-roofing.example | drafted | draft ready for approval | 94 (high) |
| AK Roofing Specialists Ltd | akroofingspecialists.co.uk | rejected | existing contact / suppressed: domain:akroofingspecialists.co.uk (existing_contact) |  |
| Forever Last Roofing Ltd |  | rejected | no first-party site (directory/social only) - outside core campaign |  |
| Kearneys Driveways & Roofing Ltd |  | rejected | no first-party site (directory/social only) - outside core campaign |  |
| Moston Roofing Ltd |  | rejected | no first-party site (directory/social only) - outside core campaign |  |
| PM & Sons Roofing Specialists Ltd | pmandsonsroofing.co.uk | rejected | existing contact / suppressed: domain:pmandsonsroofing.co.uk (existing_contact) |  |
| TCB Roofing & Building Ltd |  | rejected | no first-party site (directory/social only) - outside core campaign |  |
| Atlas Roofing & Building Services | atlas-roofbuild.com | retry | temporary site failure - retry later |  |
| Dawn Roofs Ltd | dawnroofsltd.co.uk | retry | temporary site failure - retry later |  |
| High Tech Roofing NW Limited | hightechroofing.co.uk | retry | temporary site failure - retry later |  |
| Manchester Flat Roofing | manchesterflatroofing.co.uk | retry | temporary site failure - retry later |  |
| Urmston Roofing | urmstonroofing.co.uk | retry | temporary site failure - retry later |  |
| Complete Roofing Services (Stretford page) | roofersalford.uk | review | identity uncertain: two near-identical templated sites sharing one phone number; possibly a lead-gen network, not a roofer |  |
| Manchester Roofing & Guttering Ltd |  | review | identity uncertain: same trading name on a Bridgwater (Somerset) Rated People profile; no Companies House match found |  |

## Draft for Fixture Roofing Ltd (SIMULATED)

Evidence:
- [broken_quote_link] eligible=True conf=high method=fixture src=http://127.0.0.1:8765/ (fixture (simulated) evidence)
- [noindex] eligible=True conf=high method=fixture src=http://127.0.0.1:8765/services/flat-roofing.html (fixture (simulated) evidence)
- [empty_tel] eligible=True conf=high method=fixture src=http://127.0.0.1:8765/ (fixture (simulated) evidence)
- [service_page_no_next_step] eligible=True conf=high method=fixture src=http://127.0.0.1:8765/services/flat-roofing.html (fixture (simulated) evidence)
- [cta_buried] eligible=True conf=high method=fixture src=http://127.0.0.1:8765/ (fixture (simulated) evidence)
- [missing_meta_description] eligible=False conf=medium method=fixture src=http://127.0.0.1:8765/ (weak on its own - review only)

**Subject:** One quote link on your roofing site  (state: draft)

```
Hi Fixture Roofing Ltd (SIMULATED) team,

I was looking at your website. The “Get a quote” button on your homepage took me to a page-not-found. That’s the step where someone with a leaking roof decides who to ring. I’d point the quote action at a working form and carry the chosen service into it.

I built that kind of quote flow into Ridge & Slate, one of my roofing concepts: emanwebdev.netlify.app/work/roofing

Want me to put together a free concept of that fix on your homepage, shown at phone size? If you like the direction, I’ll give you a fixed quote.

Emmanuel Adekunle
Web design for local businesses
anironmindbiz@gmail.com
If you’d rather I didn’t follow up, just reply and I’ll take you off my list.
```

Gates:
- active_trading: pass (1 strong / 1 recent signals)
- corporate_subscriber: pass (entity=ltd company_number=99999999 source=SIMULATED Companies House record)
- entity_active: pass (status=active source=SIMULATED Companies House record)
- first_party_site: pass (fixture-roofing.example)
- material_issue: pass (broken_quote_link, empty_tel, cta_buried, service_page_no_next_step, noindex)
- not_suppressed: pass (clear)
- published_contact: pass (info@fixture-roofing.example provenance=published on=own_site url=https://fixture-roofing.example/contact)

# Pipeline report

## Funnel by campaign
- **roofing-gm**: discovered 21, audited 1, qualified 1, drafted 1, sent 0, positive_replies 0, booked_calls 0, quotes 0, wins 0, booked_revenue 0, paid_revenue 0

## Funnel by issue
- -: discovered 20, drafted 0, sent 0, positive 0
- broken_quote_link: discovered 1, drafted 1, sent 0, positive 0

## Rejection / hold reasons
- state: temporary site failure - retry later: 5
- state: no first-party site (directory/social only) - outside core c: 4
- state: existing contact / suppressed: 2
- state: identity uncertain: 2

## Searches running dry (no new leads)
- roofing-gm / Didsbury / roof repairs: 1 runs, 4 directory hits, 0 first-party

## Needs Emmanuel
- nothing
