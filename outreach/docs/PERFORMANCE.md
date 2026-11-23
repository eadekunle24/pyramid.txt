# Performance report and outstanding dependencies (2026-11-23)

## Baseline: old agent (playbook v3.3), 17 to 23 Nov 2026
Source: Gmail (`in:sent after:2026/11/17`, inbox replies and bounces) and the Drive "Outreach Logs" sheets.

| Metric | Value |
|---|---|
| Outreach threads in Sent | about 56 (first touches + follow-ups) |
| Replies | 0 |
| Positive replies / booked calls / quotes / wins | 0 / 0 / 0 / 0 |
| Bounces | 1 (`info@pmandsonsroofing.co.uk`, 23 Nov) |
| Booked / paid revenue | £0 / £0 |
| Markets | UK, IE, AU, NZ across scattered towns; Manchester roofing only from 23 Nov |

Too few sends and no replies yet, so this can't credit or blame the wording. The evidence quality (D8 in the diagnosis) and the market spread (D6) are the likelier causes.

## Pilot: new pipeline, roofing in Manchester & Salford (`pilot/PILOT_OUTPUT.md`)

| Stage | Count | Notes |
|---|---|---|
| Real searches | 6 | Most results were directory pages |
| Businesses discovered | 22 records | 15 named firms came only from directory listings and would have been dropped before |
| Rejected: existing contact / suppressed | 2 | AK Roofing Specialists Ltd and PM & Sons (contacted today; PM & Sons bounced) |
| Rejected: no first-party site | 4 | TCB, Forever Last, Kearneys, Moston: outside the core campaign (candidates for a call list) |
| Review: identity uncertain | 2 | A lead-gen template network across two domains; a name clash with a Somerset firm |
| Retry: audit blocked | 5 | This session's network refuses prospect hosts |
| Awaiting domain resolution | 7 | Walker Roofing (NW) Ltd, SMV Roofing Ltd, AL Roofing Ltd ... |
| Drafted | 1 (SIMULATED) | Fixture lead from a real render: score 94, high queue; never sendable |
| Sent | 0 | Release is gated off |

## Outstanding dependencies
1. **Network for audits.** This cloud session can only reach package registries, so prospect sites and the portfolio can't be fetched or rendered. Fix one of these ways:
   - Run the scheduled agent in an environment with unrestricted outbound access, or with prospect sites reachable.
   - Run `render/mobile_audit.mjs` from the desktop app or a local machine.
   Until then, real audits are pending and the pilot leads sit in `retry`.
2. **Reference videos.** Both MP4s are inaccessible (see `docs/VIDEO_MATRIX.md`).
3. **Mailbox and release approval.** Emmanuel needs to confirm `anironmindbiz@gmail.com` (or a separate sending domain) and set `release.mode` and `mailbox_approved_by`.
4. **Scheduled task cut-over.** The live task "Outreach twice daily (auto-send)" still runs v3.3 and **auto-sends**. It needs pausing or repointing to `AGENT_INSTRUCTIONS.md`, and needs Emmanuel's decision.
5. **Companies House API key** (optional, free). It would make entity checks reliable and allow discovery by SIC code. Without it, entity status comes from the public register page.
6. **Persistent DB location.** `data/outreach.db` is ignored by git. A scheduled run in a fresh container needs the DB stored somewhere durable (for example Drive, uploaded and downloaded each run, or a committed data branch) so state carries across runs.
