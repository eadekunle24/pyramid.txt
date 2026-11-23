# Eman Web Dev outreach pipeline

A repeatable pipeline that finds active businesses with live websites, audits them on a phone viewport, picks out the problems that block enquiries, and turns the best findings into drafts that stay gated until Emmanuel approves release.

```
discover -> resolve -> audit -> qualify (gates) -> prioritise (score) -> draft -> release (gated) -> replies/outcomes
```

| Path | What it is |
|---|---|
| `schema.sql` | Lead / evidence / message schema (one lead = one buying team) |
| `config/campaigns.json` | Campaigns (service x town x niche), proof concepts, scoring thresholds, release gate and caps |
| `emanoutreach/` | Stage code: `discover`, `resolve`, `audit`, `qualify`, `draft`, `release`, `replies`, `report`, `cli` |
| `render/mobile_audit.mjs` | Real Playwright mobile render audit (read-only, rechecks link targets twice) |
| `AGENT_INSTRUCTIONS.md` | Runtime instructions for the scheduled agent (replacement for the playbook v3.3 task prompt) |
| `docs/DIAGNOSIS.md` | Why the old agent overlooked sites and stalled, with evidence |
| `docs/VIDEO_MATRIX.md` | Reference video comparison (pending: videos not accessible) |
| `docs/PERFORMANCE.md` | Baseline performance report and outstanding dependencies |
| `pilot/` | Real discovery inputs from 2026-11-23, suppression seed, pilot runner and output |
| `tests/test_cases.py` | Definition-of-done cases |

## Run it

Requires Python 3.11+ (stdlib only). Node and Playwright are needed for the renderer.

```bash
cd outreach
python3 -m unittest tests.test_cases -v        # 14 tests
python3 pilot/run_pilot.py                     # rebuilds data/pilot.db and pilot/PILOT_OUTPUT.md

# normal entry point (what the scheduled agent runs; see AGENT_INSTRUCTIONS.md)
python3 -m emanoutreach import-suppression pilot/suppression_seed.csv   # once, to carry history over
python3 -m emanoutreach plan-searches roofing-gm --limit 6
python3 -m emanoutreach import-search searches.json
python3 -m emanoutreach pending-resolution
python3 -m emanoutreach import-resolution resolutions.json
node render/mobile_audit.mjs <lead_id> https://example.co.uk/ https://example.co.uk/flat-roofing > obs.json
python3 -m emanoutreach import-observation obs.json      # accepts a JSON list of observations
python3 -m emanoutreach advance
python3 -m emanoutreach drafts
python3 -m emanoutreach approve <message_id> ...
python3 -m emanoutreach release --events events.json     # gated unless release.mode + mailbox approval are set
python3 -m emanoutreach record-send <message_id> <gmail_id> --thread <thread_id>
python3 -m emanoutreach report
```

## Release gate

`release.mode` is `off` as shipped. To send, Emmanuel sets:

```json
"release": { "mode": "approval", "mailbox_approved_by": "Emmanuel", "mailbox_approved_at": "2026-11-24", "daily_cap": 10 }
```

- `approval` sends only the messages he approved with `approve`. `auto` sends any draft that passes the gates.
- `paused: true` stops everything.
- Messages over the cap stay queued.
- The safety stop halts release on more than 3 bounces, or more than 5% bounces, in 7 days.
- Evidence marked `fixture` (simulated) is never sent.

## Scoring

The gates run first: first-party site, active entity, corporate subscriber, published contact, not suppressed, active trading, material issue. A high score cannot override a failed gate. Then the 100-point score:

| Dimension | Points |
|---|---|
| Severity of the observed problem | 0-40 |
| Evidence quality and reproducibility | 0-25 |
| Service value and active trading | 0-20 |
| Fit with a portfolio concept and a scopable fix | 0-15 |

Queues: 75 and above is high priority (concept offered at phone size, with a `visual_brief` for a before/after); 60 to 74 is standard; below 60 goes to review with its reason. Thresholds live in config and should be calibrated against real replies.
