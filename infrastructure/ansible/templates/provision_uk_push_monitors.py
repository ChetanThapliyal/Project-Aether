#!/usr/bin/env python3
"""Provision Uptime Kuma PUSH monitors idempotently. Requires uptime-kuma-api>=1.2.1."""
import argparse
import json
import sys

from uptime_kuma_api import MonitorType, UptimeKumaApi
from uptime_kuma_api.api import _check_arguments_monitor, _convert_monitor_input

p = argparse.ArgumentParser()
p.add_argument("--url", required=True)
p.add_argument("--username", required=True)
p.add_argument("--password", required=True)
p.add_argument("--notification", default="Telegram — Aether Alerts")
p.add_argument("--monitors", required=True, help='JSON: [{"name": str, "token": str, "interval": int}]')
p.add_argument("--dry-run", action="store_true")
a = p.parse_args()

api = UptimeKumaApi(a.url)
api.login(a.username, a.password)
notif = [n["id"] for n in api.get_notifications() if n.get("name") == a.notification]
if not notif:
    sys.exit(f"ERROR: notification '{a.notification}' not found; run the OPS-02 Telegram provisioning first")
existing = {m["name"]: m for m in api.get_monitors()}

for m in json.loads(a.monitors):
    cur = existing.get(m["name"])
    if cur and cur.get("pushToken") == m["token"] and cur.get("interval") == m["interval"]:
        print(f"SKIP: {m['name']}")
        continue
    if a.dry_run:
        print(f"WOULD {'UPDATE' if cur else 'CREATE'}: {m['name']}")
        continue
    if cur:
        mid = cur["id"]
        api.edit_monitor(mid, pushToken=m["token"], interval=m["interval"])
    else:
        # add_monitor() can't be used on Kuma 2.x: uptime-kuma-api 1.2.1 omits the
        # NOT NULL `conditions` column and has no pushToken parameter. Build the
        # same payload, add both fields, and send it in one call.
        data = api._build_monitor_data(
            type=MonitorType.PUSH, name=m["name"], interval=m["interval"],
            retryInterval=m["interval"], maxretries=0, notificationIDList=notif)
        data["pushToken"] = m["token"]
        _convert_monitor_input(data)
        _check_arguments_monitor(data)
        data["conditions"] = []  # list, as the Kuma 2 UI sends it
        mid = api._call("add", data)["monitorID"]
    print(f"OK: {m['name']} (id={mid})")
api.disconnect()
