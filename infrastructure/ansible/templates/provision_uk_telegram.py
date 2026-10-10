#!/usr/bin/env python3
"""
OPS-02: Provision a Telegram notification channel in Uptime Kuma via Socket.IO API.
Requires: uptime-kuma-api (pip install uptime-kuma-api)
Idempotent: skips if a notification with the same name already exists.
"""

import argparse
import sys

try:
    from uptime_kuma_api import UptimeKumaApi, NotificationType
except ImportError:
    print("ERROR: uptime-kuma-api not installed. Run: pip3 install uptime-kuma-api")
    sys.exit(1)

parser = argparse.ArgumentParser()
parser.add_argument("--url",       required=True,  help="Uptime Kuma base URL (e.g. http://127.0.0.1:3001)")
parser.add_argument("--username",  default="admin", help="Admin username (default: admin)")
parser.add_argument("--password",  required=True,  help="Admin password")
parser.add_argument("--bot-token", required=True,  help="Telegram bot token")
parser.add_argument("--chat-id",   required=True,  help="Telegram chat ID")
parser.add_argument("--name",      default="Telegram — Aether Alerts", help="Notification channel name")
args = parser.parse_args()

try:
    api = UptimeKumaApi(args.url, ssl_verify=False)
    try:
        api.login(args.username, args.password)
    except Exception as login_err:
        # If default admin failed, try fallback common usernames
        logged_in = False
        for fallback_user in ["admin", "che01tan", "kill3rbee"]:
            if fallback_user == args.username:
                continue
            try:
                api.login(fallback_user, args.password)
                logged_in = True
                break
            except Exception:
                pass
        if not logged_in:
            raise login_err

    # Idempotency check — skip if already exists
    existing = api.get_notifications()
    for n in existing:
        if n.get("name") == args.name:
            print(f"SKIP: Notification '{args.name}' already exists (id={n.get('id')})")
            api.disconnect()
            sys.exit(0)

    # Create Telegram notification, set as default and apply to all existing monitors
    api.add_notification(
        type=NotificationType.TELEGRAM,
        name=args.name,
        isDefault=True,
        applyExisting=True,
        telegramBotToken=str(args.bot_token),
        telegramChatID=str(args.chat_id),
        telegramSendSilently=False,
        telegramProtectContent=False,
    )

    print(f"OK: Telegram notification '{args.name}' created and applied to all monitors.")
    api.disconnect()
    sys.exit(0)

except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
