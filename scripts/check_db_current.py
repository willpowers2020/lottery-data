#!/usr/bin/env python3
"""Utility to report the most recent draw stored in whichever database is active.

This script is designed to be runnable both locally and in CI.  When invoked by
GitHub Actions it can exit nonzero if the database is behind the expected
date, causing the workflow to fail and GitHub to notify watchers automatically.

The Flask application already exposes an endpoint that returns statistics for a
state/game combination.  This little script exercises that endpoint for a
list of states and games, printing the last draw date and the total number of
records.  You can run it against the default backend or force a different one
with the DB_MODE environment variable or the ``?db=`` query parameter.

Usage examples:

    # use whatever DB_MODE is set in the environment (default: mongo_v2)
    $ python3 check_db_current.py

    # force sqlite explicitly
    $ DB_MODE=sqlite python3 check_db_current.py

    # run in CI and notify watchers on failure (exit code 1):
    $ python3 check_db_current.py --alert-days 0
"""

import os
import os, sys
from datetime import datetime, timedelta

# ensure `src/` is on PYTHONPATH when running as a script
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(root, 'src'))

from mld.api import app

# pick a set of states to verify; you can expand this list or populate it by
# querying the collection directly.
STATES = [
    "Florida",
    "Maryland",
    "Virginia",
    "Delaware",
    "Ohio",
    "Pennsylvania",
    "Georgia",
    "Washington DC",
    "Louisiana",
]
GAMES = ["pick2", "pick3", "pick4", "pick5"]


def send_email(subject, body, to_addrs):
    """Simple SMTP helper using localhost."""
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = os.environ.get('ALERT_FROM', 'mld-alert@example.com')
    msg['To'] = ', '.join(to_addrs)
    msg.set_content(body)

    with smtplib.SMTP(os.environ.get('SMTP_HOST', 'localhost'), int(os.environ.get('SMTP_PORT', 25))) as s:
        s.send_message(msg)


def send_discord(webhook_url, content):
    """Post a simple message to a Discord webhook."""
    try:
        import requests
    except ImportError:
        return  # no requests, skip

    payload = {"content": content}
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception:
        pass


def check(db_mode=None, alert_threshold_days=1, email_to=None):
    client = app.test_client()
    print(f"DB_MODE={db_mode or os.environ.get('DB_MODE', 'mongo_v2')}\n")

    alerts = []
    today = datetime.now().date()
    threshold_date = today - timedelta(days=alert_threshold_days)

    for state in STATES:
        for game in GAMES:
            url = f"/api/rbtl/data-stats/{state}/{game}"
            if db_mode:
                url += f"?db={db_mode}"
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json
                print(
                    f"{state:15} {game:6}  last={data['last_draw_date']}  "
                    f"first={data['first_draw_date']}  total={data['total_draws']}"
                )
                try:
                    last = datetime.strptime(data['last_draw_date'], '%Y-%m-%d').date()
                    if last < threshold_date:
                        alerts.append(f"{state}/{game} lagging: last={last}")
                except Exception:
                    alerts.append(f"{state}/{game} bad date: {data['last_draw_date']}")
            else:
                msg = f"{state:15} {game:6}  ERROR {resp.status_code}: {resp.get_data(as_text=True)}"
                print(msg)
                alerts.append(msg)

    # email if requested
    if email_to:
        subject = f"MLD DB status {'ALERT' if alerts else 'OK'}"
        body = []
        if alerts:
            body.append('ALERTS:')
            body.extend(alerts)
            body.append('')
        body.append('Full report:')
        body = '\n'.join(body)
        send_email(subject, body, email_to)

    # discord alert if webhook configured
    webhook = os.environ.get('DISCORD_WEBHOOK')
    if webhook:
        status = 'ALERT' if alerts else 'OK'
        msg = f"[MLD DB {status}] "
        if alerts:
            msg += '; '.join(alerts[:5])  # include up to first few alerts
        else:
            msg += 'all up-to-date'
        # Discord limits message length, keep it short
        send_discord(webhook, msg)

    # exit non-zero if anything was flagged so that CI can detect problems
    if alerts:
        # short message on stderr for visibility in workflow logs
        import sys
        print(f"{len(alerts)} alert(s) found, exiting with error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import os
    import argparse

    parser = argparse.ArgumentParser(description="Check DB currency and optionally email alerts")
    parser.add_argument("--db", help="Database mode (sqlite,mongo,mongo_v2)")
    parser.add_argument("--alert-days", type=int, default=1,
                        help="Number of days behind which to raise an alert")
    parser.add_argument("--email", action="store_true",
                        help="Send an email report (requires ALERT_TO env var)")
    args = parser.parse_args()

    db = args.db or os.environ.get('DB_MODE', None)
    email_to = None
    if args.email:
        to = os.environ.get('ALERT_TO')
        if to:
            email_to = [addr.strip() for addr in to.split(',') if addr.strip()]
        else:
            print("Warning: ALERT_TO not set; skipping email")

    check(db, alert_threshold_days=args.alert_days, email_to=email_to)
