# Diagnosis of the existing outreach agent (2026-11-23)

## What the existing agent is

No outreach code lived in a repository. The agent is a **Claude scheduled task**, plus files in Drive and labels in Gmail:

| Component | Where | Notes |
|---|---|---|
| Entry point | Scheduled task "Outreach twice daily (auto-send)", `CRON_TZ=Europe/London 22 8,20 * * *`, permission mode `auto`, model sonnet | Its prompt is the whole agent: "PLAYBOOK v3.3 (approved by Emmanuel 2026-11-23)" |
| Earlier run helper | One-off task "Resume outreach run to 50 drafts" (fired 2026-11-20 11:35) | Shows a stalled run |
| Proposed method | Drive doc "Outreach playbook v4 (free method, 2026-11-23)" | Not adopted in the scheduled task |
| State | Drive folder "Outreach Logs" (`1FpZ...5y`): 9 sheets in 5 days, one new sheet per run | "Drive cannot edit existing files" (v3.3, Storage) |
| Integrations | Gmail (`anironmindbiz@gmail.com`), Drive, WebSearch, WebFetch | Labels Outreach/*, Feedback/* |
| Tests | none | |
| Other repo content | `pyramid.txt`; branch `claude/ai-dropshipping-automation-br41ow` is unrelated dropshipping code | |

Results so far (Gmail, 17 to 23 Nov): about **56 outreach threads sent**, **0 replies**, **1 bounce** (`info@pmandsonsroofing.co.uk`, today's v4 pilot).

## Why existing websites get overlooked and where leads drop

**D1. Search returns directories, and the agent drops them instead of mining them.**
- Evidence: log *2026-11-23*, rows "Norwich and Ipswich roofers (other): Search returned Checkatrade, TrustATrader, FreeIndex and Bark directory pages only", "Chester hair salons: Fresha, Booksy and Salonspy listings only", "Cork cafes and restaurants". Log *2026-11-23 (2)*, row "Preston Bolton Chester Leeds Birmingham Bristol Newcastle Cardiff Kent combos (other): Search mostly returned directory pages ... skipped".
- Playbook v3.3 §1f and §3 have no step that turns a directory listing into a business and then into its own domain.
- Reproduced today: all 6 pilot searches returned directory pages first. 15 named firms appeared only inside listings (TCB, AL Roofing, Kearneys, Forever Last, Moston, Only Roofing, FPL ...). See `pilot/searches_2026-11-23.json`.
- Fix: `discover.import_search` records each directory listing as a lead with `needs_domain_resolution`. Directory search pages are logged as lead lists. Nothing is silently dropped.

**D2. The qualifying filter is "find a broken link", so active firms with working sites get skipped.**
- Evidence: v3.3 §3 ("Good findings are concrete: a quote/contact link that returns a not-found..."); v3.3 has no search-visibility audit. Log 2026-11-23 shows Noble Roofing ("no verified problem") and Larke's Roofs (skipped). Log 2026-11-23 (2) shows Urban Landscape Design and DH Roofing ("no verified problem").
- The v4 doc says it "Replaces the 'find a broken link' filter", but the scheduled task still runs v3.3.
- Fix: the audit covers conversion, search visibility (scoped observations), indexability and speed. A lead with no supported issue goes to **review with a reason** and stays visible.

**D3. The audit is text-only, so findings carry doubts and site failures dead-end.**
- Evidence: v3.3 "Tools available ... WebFetch (returns page text, not visuals) ... You CANNOT see pages visually". Every 2026-11-23 row has `risks_or_doubts = "Text fetch only"`. Doubts such as "Counters may be JS" and "Form may be JS" appear in the 2026-11-20 (2) log. "Fetch blocked by bot detection" (Louisa John, Miller's) became `needs_review` with no retry path.
- The v4 doc says: "The browser needs the Claude desktop app open, so scheduled runs cannot do steps 3 and 4."
- Fix: `render/mobile_audit.mjs` is a real Playwright render at 390x844. It checks every enquiry link's target twice and never submits forms. Failures go to a `retry` state with `retry_after`, and to `review` after 3 failed attempts.

**D4. Runs stall under quota pressure.**
- Evidence: the scheduled task "Resume outreach run to 50 drafts" says "WebFetch limit should have reset ... 31 drafts saved ... blocked agents returned". The v4 doc says "Bulk automated Google requests (dozens at once) were blocked by a safety check".
- Fix: stages are separate and resumable. A crash mid-run resumes from each lead's state. Discovery volume is set independently of sending.

**D5. There is no lead record, so dedupe, retries and history are fragile.**
- Evidence: one new sheet per run (v3.3 "Storage"). Each run must re-read every sheet plus Gmail. Follow-up rows are re-logged as new rows, and `customer_scenario`, `consequence` and `gmail_draft_id` are often empty. `eligible_not_drafted` and `needs_review` leads are never revisited (Haven Building, MPH Builders, DLK Roofing).
- Fix: `schema.sql` adds one record per buying team, with domains/aliases, contacts with provenance, evidence, gate results, scores, messages, send attempts, suppression and an append-only event log.

**D6. Effort is spread away from the proof.**
- Evidence: runs alternate UK/IE (morning) and AU/NZ (evening) across scattered towns (Dubbo, Invercargill, Worcester, Carlisle). Manchester roofing only started in today's v4 pilot.
- Fix: campaigns are configured as service x town x niche. Roofing in Manchester and Salford is stage 1. Salons and restaurants are separate campaigns, disabled until you enable them.

**D7. Sending is not gated on your approval.**
- Evidence: the scheduled task is enabled with "You SEND first-touch emails and follow-ups yourself", up to 10 + 10 per run, twice a day, permission mode `auto`. Follow-ups go out at 3 calendar days (v3.3 §5), not 4 business days.
- Fix: `release.mode` is `off` by default, and `mailbox_approved_by` must be set before anything leaves. In `approval` mode only messages you approved go out. Caps defer messages rather than drop them. Follow-ups are due 4 business days later, in the same thread.

**D8. The messages lead with observations a buyer won't act on.**
- Evidence: sent subjects include "The reviews on the Roof Force homepage" (duplicate review text, an "EDPM" typo) and "The booking form on the Jhons Roofing site" ("Zip Code" field). Neither is a step a homeowner gets stuck on. Zero replies from ~56 sends.
- Fix: severity is weighted toward broken enquiry paths, buried calls to action, service pages with no next step and indexability. Typos, copyright years and meta descriptions are `review only` and cannot drive a message alone.

**D9. Contact and eligibility provenance is thin.**
- Evidence: a bounce today on `info@pmandsonsroofing.co.uk`. Many 2026-11-20 AU rows have `entity_type = "not stated"`.
- Fix: the `published_contact` gate needs `provenance=published`, `published_on` (own_site or official_listing) and the `published_url`, and an estimated address is a hard fail. For UK email, the `corporate_subscriber` gate needs ltd/llp/plc, a company number and an `entity_source_url`. Sole traders and partnerships go to a call list (check TPS/CTPS). Suppression covers email, domain, company and buying team, and the history is seeded from the logs and Gmail (`pilot/suppression_seed.csv`).
