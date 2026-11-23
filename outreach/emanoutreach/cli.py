"""Command-line entry point: python -m emanoutreach <command> ...

Normal run order (what the scheduled agent does):
  plan-searches -> [agent searches] -> import-search -> [agent resolves] -> import-resolution
  -> [agent/renderer audits] -> import-observation -> advance -> report
  -> (only with approval) release -> [agent sends via Gmail] -> record-send
  Every run starts with import-mail-events so stop events win before release.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import db, discover, pipeline, qualify, release, replies, report

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "outreach.db"
DEFAULT_CFG = ROOT / "config" / "campaigns.json"


def load(path):
    p = Path(path)
    data = json.loads(p.read_text())
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(prog="emanoutreach")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--config", default=str(DEFAULT_CFG))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan-searches"); p.add_argument("campaign"); p.add_argument("--expand", action="store_true"); p.add_argument("--limit", type=int)
    p = sub.add_parser("import-search"); p.add_argument("file", help="JSON object or list of search payloads")
    p = sub.add_parser("pending-resolution")
    p = sub.add_parser("import-resolution"); p.add_argument("file", help="JSON list of {lead_id, ...}")
    p = sub.add_parser("pending-audit")
    p = sub.add_parser("import-observation"); p.add_argument("file", help="JSON list of observation docs")
    sub.add_parser("advance")
    p = sub.add_parser("import-suppression"); p.add_argument("file", help="CSV: kind,value,reason,source")
    p = sub.add_parser("import-mail-events"); p.add_argument("file", help="JSON list of {type,email|thread_id,...}")
    p = sub.add_parser("approve"); p.add_argument("message_ids", nargs="+")
    p = sub.add_parser("release"); p.add_argument("--events", help="JSON list of mail events fetched this run")
    p = sub.add_parser("record-send"); p.add_argument("message_id"); p.add_argument("provider_message_id"); p.add_argument("--thread")
    p = sub.add_parser("reconcile"); p.add_argument("message_id"); p.add_argument("--found-id"); p.add_argument("--thread"); p.add_argument("--absent", action="store_true")
    p = sub.add_parser("report"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("drafts"); p.add_argument("--state", default="draft")
    a = ap.parse_args(argv)

    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(a.db)
    cfg = load(a.config)
    out = None
    if a.cmd == "plan-searches":
        out = discover.plan_queries(conn, cfg, a.campaign, a.expand, a.limit)
    elif a.cmd == "import-search":
        data = load(a.file)
        out = [discover.import_search(conn, cfg, d) for d in (data if isinstance(data, list) else [data])]
    elif a.cmd == "pending-resolution":
        out = [dict(id=l["id"], name=l["trading_name"], town=l["town"], phone=l["phone"], reason=l["state_reason"])
               for l in db.live_leads(conn, ["discovered"])]
    elif a.cmd == "import-resolution":
        out = [discover.import_resolution(conn, cfg, r["lead_id"], r) for r in load(a.file)]
    elif a.cmd == "pending-audit":
        out = [dict(id=l["id"], name=l["trading_name"], domain=l["canonical_domain"], state=l["state"])
               for l in db.live_leads(conn, ["resolved", "retry"])]
    elif a.cmd == "import-observation":
        out = pipeline.run_audits(conn, load(a.file))
    elif a.cmd == "advance":
        out = pipeline.advance(conn, cfg)
    elif a.cmd == "import-suppression":
        n = 0
        with open(a.file) as f:
            for row in csv.DictReader(f):
                qualify.suppress(conn, row["kind"], row["value"], row.get("reason") or "import", row.get("source"))
                n += 1
        out = {"imported": n}
    elif a.cmd == "import-mail-events":
        out = [replies.apply(conn, e) for e in load(a.file)]
    elif a.cmd == "approve":
        release.approve(conn, a.message_ids)
        out = {"approved": a.message_ids}
    elif a.cmd == "release":
        outbox = []
        prov = release.HandoffProvider(events=load(a.events) if a.events else [], outbox=outbox)
        out = release.release(conn, cfg, prov)
        out["outbox"] = outbox
    elif a.cmd == "record-send":
        release.record_send(conn, cfg, a.message_id, a.provider_message_id, a.thread)
        out = {"recorded": a.message_id}
    elif a.cmd == "reconcile":
        release.record_reconcile(conn, a.message_id, None if a.absent else {"message_id": a.found_id, "thread_id": a.thread})
        out = {"reconciled": a.message_id}
    elif a.cmd == "report":
        out = report.lead_table(conn) if a.json else report.text_report(conn)
    elif a.cmd == "drafts":
        out = [dict(r) for r in conn.execute("SELECT id, lead_id, to_address, subject, body, state, state_reason, visual_brief "
                                             "FROM messages WHERE state=?", (a.state,))]
    conn.commit()
    if isinstance(out, str):
        print(out)
    else:
        json.dump(out, sys.stdout, indent=2, default=str)
        print()


if __name__ == "__main__":
    main()
