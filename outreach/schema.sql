-- Eman Web Dev outreach pipeline: lead / evidence / message schema (SQLite).
-- One row in `leads` = one BUYING TEAM. Domains, listings and branches that
-- reach the same team are folded into it via `domains` and `buying_team_key`.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS leads (
  id               TEXT PRIMARY KEY,
  campaign         TEXT NOT NULL,            -- e.g. roofing-gm, salons-gm, restaurants-gm
  niche            TEXT NOT NULL,            -- roofing | salon | restaurant | ...
  trading_name     TEXT,
  legal_name       TEXT,
  company_number   TEXT,                     -- Companies House / CRO number
  entity_type      TEXT,                     -- ltd | llp | plc | sole_trader | partnership | unknown
  entity_status    TEXT,                     -- active | dissolved | liquidation | unknown
  entity_source_url TEXT,
  entity_checked_at TEXT,
  country          TEXT DEFAULT 'UK',
  town             TEXT,
  canonical_domain TEXT,
  phone            TEXT,
  buying_team_key  TEXT UNIQUE,              -- company:<no> | domain:<root> | phone:<e164>
  state            TEXT NOT NULL DEFAULT 'discovered',
  state_reason     TEXT,
  retry_after      TEXT,                     -- for retry queue (temporary site failure)
  merged_into      TEXT REFERENCES leads(id),
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS domains (
  domain   TEXT PRIMARY KEY,
  lead_id  TEXT NOT NULL REFERENCES leads(id),
  role     TEXT NOT NULL DEFAULT 'alias'      -- canonical | alias | redirect
);

CREATE TABLE IF NOT EXISTS search_queries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign      TEXT NOT NULL,
  niche         TEXT, service TEXT, town TEXT,
  query         TEXT NOT NULL,
  source        TEXT NOT NULL,               -- websearch | companies_house | directory:<name> | manual
  page          INTEGER NOT NULL DEFAULT 1,
  run_at        TEXT NOT NULL,
  results_count INTEGER NOT NULL DEFAULT 0,
  first_party   INTEGER NOT NULL DEFAULT 0,  -- results that were a business's own site
  directory     INTEGER NOT NULL DEFAULT 0,  -- results that were directory/listing pages
  new_leads     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS discoveries (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id    TEXT REFERENCES leads(id),
  query_id   INTEGER REFERENCES search_queries(id),
  source_url TEXT, raw_name TEXT, kind TEXT, -- first_party | directory | registry
  found_at   TEXT NOT NULL
);

-- Trading signals (recent projects, booking availability, filings, reviews with dates)
CREATE TABLE IF NOT EXISTS trading_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id TEXT NOT NULL REFERENCES leads(id),
  signal TEXT NOT NULL, observed_date TEXT, source_url TEXT, strength TEXT -- strong | weak
);

CREATE TABLE IF NOT EXISTS contacts (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id        TEXT NOT NULL REFERENCES leads(id),
  channel        TEXT NOT NULL,              -- email | contact_form | phone | social
  address        TEXT NOT NULL,
  published_url  TEXT,                       -- page the address is published on
  published_on   TEXT,                       -- own_site | official_listing | directory | none
  provenance     TEXT NOT NULL,              -- published | estimated | unknown
  corporate_basis TEXT,                      -- why recipient is treated as a UK corporate subscriber
  verified_at    TEXT,
  status         TEXT NOT NULL DEFAULT 'ok', -- ok | bounced | opted_out
  UNIQUE(lead_id, channel, address)
);

-- Evidence contract: every message-driving claim lives here.
CREATE TABLE IF NOT EXISTS evidence (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id          TEXT NOT NULL REFERENCES leads(id),
  kind             TEXT NOT NULL,            -- conversion | search | speed | design | trading
  issue            TEXT NOT NULL,            -- broken_quote_link | empty_tel | noindex | not_in_top10 | ...
  claim            TEXT NOT NULL,            -- internal statement
  plain_observation TEXT,                    -- owner-facing wording, scoped
  source_url       TEXT,
  observed_at      TEXT,
  method           TEXT,                     -- rendered | text_fetch | search | manual | fixture
  viewport         TEXT,
  steps            TEXT,                     -- JSON list of reproduction steps
  search_context   TEXT,                     -- JSON {query, engine, location, device, date, depth, result_type}
  confidence       TEXT,                     -- high | medium | low
  consequence      TEXT,                     -- plausible customer impact
  fix              TEXT,
  severity         INTEGER NOT NULL DEFAULT 0,  -- 0-40 contribution
  message_eligible INTEGER NOT NULL DEFAULT 0,
  ineligible_reason TEXT,
  untrusted_flags  TEXT                      -- e.g. instruction-like page text detected
);

CREATE TABLE IF NOT EXISTS gate_results (
  lead_id TEXT NOT NULL REFERENCES leads(id),
  gate    TEXT NOT NULL,
  passed  INTEGER NOT NULL,
  detail  TEXT,
  checked_at TEXT NOT NULL,
  PRIMARY KEY (lead_id, gate)
);

CREATE TABLE IF NOT EXISTS scores (
  lead_id          TEXT PRIMARY KEY REFERENCES leads(id),
  severity         INTEGER, evidence_quality INTEGER, value_trading INTEGER, fit INTEGER,
  total            INTEGER,
  queue            TEXT,                     -- high | standard | review | drop
  reasons          TEXT,
  scored_at        TEXT
);

-- Unknown commercial figures stay NULL unless a client grants analytics access.
CREATE TABLE IF NOT EXISTS analytics (
  lead_id TEXT PRIMARY KEY REFERENCES leads(id),
  monthly_traffic INTEGER, missed_enquiries INTEGER, revenue_impact REAL,
  source TEXT,                               -- search_console | ga4 | verified_events ; NULL = unknown
  granted_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id               TEXT PRIMARY KEY,
  lead_id          TEXT NOT NULL REFERENCES leads(id),
  buying_team_key  TEXT NOT NULL,
  step             INTEGER NOT NULL,         -- 1 = opener, 2 = follow-up
  idempotency_key  TEXT NOT NULL UNIQUE,     -- team:<key>:step:<n>
  to_address       TEXT NOT NULL,
  subject          TEXT NOT NULL,
  body             TEXT NOT NULL,
  offer_variant    TEXT,                     -- preview_mockup | preview_fix | ...
  proof_url        TEXT,
  evidence_ids     TEXT,                     -- JSON list
  visual_brief     TEXT,                     -- high-priority: before/after brief
  state            TEXT NOT NULL,            -- draft | approved | queued | sending | sent | unknown | failed | cancelled
  state_reason     TEXT,
  due_at           TEXT,
  approved_at      TEXT,
  provider_message_id TEXT,
  thread_id        TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS send_attempts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT NOT NULL REFERENCES messages(id),
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  outcome     TEXT NOT NULL,                 -- started | sent | failed | unknown | reconciled_sent | reconciled_absent
  provider_ref TEXT,
  detail      TEXT
);

CREATE TABLE IF NOT EXISTS suppression (
  kind    TEXT NOT NULL,                     -- email | domain | company | team
  value   TEXT NOT NULL,
  reason  TEXT NOT NULL,                     -- opt_out | bounce | replied | existing_contact | disqualified | import
  source  TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (kind, value)
);

-- Append-only event history (state transitions, replies, outcomes, revenue)
CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id    TEXT,
  message_id TEXT,
  type       TEXT NOT NULL,
  detail     TEXT,
  value      REAL,                           -- £ for quote / won / paid events
  at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handoffs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id TEXT NOT NULL, message_id TEXT, reason TEXT, summary TEXT, created_at TEXT NOT NULL, done INTEGER DEFAULT 0
);
