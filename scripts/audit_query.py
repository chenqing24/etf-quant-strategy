#!/usr/bin/env python3
"""Audit log query tool.

Reads JSON Lines audit log (written to stdout by AuditLogger, routed to file
by cron/Skill execution environment) and filters by time/command/source/actor.

Usage:
  # All events from 2026-06-10
  python scripts/audit_query.py --time=2026-06-10

  # All dingtalk_send events
  python scripts/audit_query.py --command=dingtalk_send

  # All events from dialog source
  python scripts/audit_query.py --source=dialog

  # Combine filters
  python scripts/audit_query.py --source=cron --time=2026-06-10

  # From custom log file (default: /var/log/etf_strategy/audit.log)
  python scripts/audit_query.py --logfile=/path/to/audit.log --source=manual
"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_LOG = "/var/log/etf_strategy/audit.log"
VALID_SOURCES = {"cron", "skill", "dialog", "manual", "unknown"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logfile", default=DEFAULT_LOG,
                        help="Path to JSON Lines log file")
    parser.add_argument("--time", help="Filter by date (YYYY-MM-DD)")
    parser.add_argument("--command", help="Filter by command name")
    parser.add_argument("--source", choices=sorted(VALID_SOURCES),
                        help="Filter by execution source")
    parser.add_argument("--actor", help="Filter by actor (user_id / session_id)")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max results (default 100)")
    args = parser.parse_args()

    log_path = Path(args.logfile)
    if not log_path.exists():
        print(f"ERROR: log file not found: {log_path}", file=sys.stderr)
        return 1

    # utf-8-sig 自动剥离 BOM（生产环境日志文件可能带 BOM）
    count = 0
    for line in log_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if args.time and not event.get("timestamp", "").startswith(args.time):
            continue
        if args.command and event.get("command") != args.command:
            continue
        if args.source and event.get("source") != args.source:
            continue
        if args.actor and event.get("actor") != args.actor:
            continue

        print(json.dumps(event, ensure_ascii=False))
        count += 1
        if count >= args.limit:
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
