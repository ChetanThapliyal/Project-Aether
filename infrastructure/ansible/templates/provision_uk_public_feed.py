#!/usr/bin/env python3
"""FND-20: DMZ Uptime Kuma pieces for the public Glance page. Idempotent.

1. A JSON-query monitor on the public feed that goes DOWN when the summary is
   stale (`fresh` != true) or unreachable, and alerts on Telegram.
2. A status page (slug `public`) that lists only monitors whose names are safe
   to show publicly. Glance reads it over localhost on the DMZ.

Requires uptime-kuma-api>=1.2.1 (Kuma 2.x needs the `conditions` workaround).
"""
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
p.add_argument("--feed-url", required=True)
p.add_argument("--public-monitors", required=True, help="JSON list of monitor names allowed on the public page")
a = p.parse_args()

FEED_MONITOR = "Public feed — fresh (FND-20)"
SLUG, TITLE = "public", "Project Aether"

api = UptimeKumaApi(a.url, timeout=30)
api.login(a.username, a.password)
notif = [n["id"] for n in api.get_notifications() if n.get("name") == a.notification]
if not notif:
    sys.exit(f"ERROR: notification '{a.notification}' not found; run the OPS-02 provisioning first")
monitors = {m["name"]: m for m in api.get_monitors()}

# 1. Freshness monitor
cur = monitors.get(FEED_MONITOR)
want = {"url": a.feed_url, "jsonPath": "fresh", "expectedValue": "true", "interval": 300}
if cur and all(str(cur.get(k)) == str(v) for k, v in want.items()):
    print(f"SKIP: {FEED_MONITOR}")
else:
    data = api._build_monitor_data(
        type=MonitorType.JSON_QUERY, name=FEED_MONITOR, url=a.feed_url, interval=300,
        retryInterval=120, maxretries=2, notificationIDList=notif)
    data["jsonPath"] = "fresh"
    data["jsonPathOperator"] = "=="
    data["expectedValue"] = "true"
    _convert_monitor_input(data)
    _check_arguments_monitor(data)
    data["conditions"] = []
    if cur:
        data["id"] = cur["id"]
        api._call("editMonitor", data)
        print(f"OK: updated {FEED_MONITOR}")
    else:
        mid = api._call("add", data)["monitorID"]
        print(f"OK: created {FEED_MONITOR} (id={mid})")
        # get_monitors() lags behind a fresh add; use the id the call returned.
        monitors[FEED_MONITOR] = {"id": mid, "name": FEED_MONITOR}

# 2. Public status page
allowed = json.loads(a.public_monitors) + [FEED_MONITOR]
missing = [n for n in allowed if n not in monitors]
if missing:
    sys.exit(f"ERROR: monitors not found: {missing}")
if SLUG not in [s["slug"] for s in api.get_status_pages()]:
    api.add_status_page(SLUG, TITLE)
    print(f"OK: created status page {SLUG}")
# Kuma 2's REST endpoint 404s for a page that was never saved, and the
# library's get/save_status_page read it first, so check over REST and save
# with the raw socket call the UI uses.
import urllib.request
ids = [monitors[n]["id"] for n in allowed]
try:
    with urllib.request.urlopen(f"{a.url}/api/status-page/{SLUG}", timeout=15) as r:
        page = json.load(r)
    have = [m["id"] for g in page.get("publicGroupList", []) for m in g.get("monitorList", [])]
except Exception:
    have = None
if have == ids:
    print(f"SKIP: status page {SLUG}")
else:
    config = {
        "slug": SLUG, "title": TITLE,
        "description": "Public-safe monitors for the Glance status page (FND-20)",
        "icon": "/icon.svg", "theme": "dark", "published": True, "showTags": False,
        "domainNameList": [], "customCSS": "", "footerText": None,
        "showPoweredBy": False, "showCertificateExpiry": False, "analyticsType": None,
        "analyticsId": None, "analyticsScriptUrl": None, "autoRefreshInterval": 300,
    }
    groups = [{"name": "Backups and alerting", "monitorList": [{"id": i} for i in ids]}]
    api._call("saveStatusPage", (SLUG, config, "/icon.svg", groups))
    print(f"OK: status page {SLUG} lists {len(ids)} monitors")
api.disconnect()
