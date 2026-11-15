#!/usr/bin/env python3
"""FND-22: 30-day availability of the public sites, for the Glance page.

Reads the DMZ Uptime Kuma database read-only (daily stats) and writes a small
JSON file that Glance renders. Runs on the DMZ from a systemd timer, so the
numbers never leave the host they were measured on, and nothing private is in
them: only the display labels below, dates and percentages.

The monitor names must match deploy-dmz.yml (site_monitors).
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone

DB = "/opt/dmz/uptime-kuma/kuma.db"
OUT = "/opt/dmz/glance/assets/uptime.json"
DAYS = 30
SITES = [  # (Kuma monitor name, label shown on the page)
    ("Public site — Portfolio", "Portfolio and blog"),
    ("Public site — Lexicon", "Lexicon notes"),
    ("Public site — Status page", "This status page"),
]
SLO = ("Public site — Portfolio", 99.5)  # one objective, on the main site


def main():
    if not os.path.getsize(DB):
        sys.exit(f"{DB} is empty")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    ids = dict(con.execute("SELECT name, id FROM monitor"))
    interval = dict(con.execute("SELECT id, interval FROM monitor"))
    today = int(time.time()) // 86400 * 86400
    first = today - (DAYS - 1) * 86400
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "days": DAYS, "sites": []}
    for name, label in SITES:
        mid = ids.get(name)
        rows = {} if mid is None else {
            ts: (up, down) for ts, up, down in con.execute(
                "SELECT timestamp, up, down FROM stat_daily WHERE monitor_id = ? AND timestamp >= ?", (mid, first))
        }
        bars, up_sum, down_sum = [], 0, 0
        for d in range(DAYS):
            ts = first + d * 86400
            up, down = rows.get(ts, (0, 0))
            day = datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b")
            if up + down == 0:
                bars.append({"day": day, "level": "none", "pct": 0})
                continue
            pct = 100.0 * up / (up + down)
            up_sum, down_sum = up_sum + up, down_sum + down
            level = "ok" if pct >= 99.9 else ("warn" if pct >= 99.0 else "bad")
            bars.append({"day": day, "level": level, "pct": round(pct, 2)})
        total = up_sum + down_sum
        days_with_data = sum(1 for b in bars if b["level"] != "none")
        site = {
            "label": label,
            "days_with_data": days_with_data,
            "uptime_pct": round(100.0 * up_sum / total, 2) if total else None,
            "down_minutes": round(down_sum * interval.get(mid, 60) / 60) if mid else 0,
            "bars": bars,
        }
        out["sites"].append(site)
        if name == SLO[0]:
            allowed = (100 - SLO[1]) / 100 * total
            out["slo"] = {
                "label": label, "target": SLO[1], "days_with_data": days_with_data,
                "met": bool(total) and site["uptime_pct"] >= SLO[1],
                "budget_left_pct": round(max(0.0, 100.0 * (1 - down_sum / allowed)), 1) if allowed else None,
            }
    con.close()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT))
    with os.fdopen(fd, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)  # Glance never reads a half-written file


if __name__ == "__main__":
    main()
