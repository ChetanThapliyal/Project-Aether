#!/usr/bin/env python3
"""Recovery objectives for the Glance page (FND-23), with each component's
newest backup read live on this host (see docs/disaster-recovery/objectives.yml).

Reads the DMZ Uptime Kuma database read-only (last UP heartbeat of each backup
monitor) and systemd (the DMZ's own backup unit), and writes a small JSON file
that Glance renders. Runs on the DMZ from a systemd timer; only display fields
reach the page.

FND-22 also computed 30-day availability of the public sites here; that card
was removed on 16 Nov 2026 (the sites are hosted by Cloudflare). The Kuma site
monitors stay for alerting.
"""
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timezone

DB = "/opt/dmz/uptime-kuma/kuma.db"
OUT = "/opt/dmz/glance/assets/uptime.json"
OBJECTIVES = "/usr/local/etc/aether-objectives.json"  # objectives.yml, converted at deploy
RPO_GRACE_H = 3  # nightly jobs: scheduling jitter and run time


def main():
    # A rebuilt DMZ has no Kuma database until the restore (DR Scenario 05 §3.5).
    # Not an error: skip this run, so the deploy that installs this timer completes
    # and the next run after the restore fills the page (5.53 drill finding).
    if not os.path.exists(DB) or not os.path.getsize(DB):
        print(f"{DB} missing or empty (fresh VM, Kuma not restored yet): skipping this run")
        return
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    out = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    out["recovery"] = recovery(con)
    con.close()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT))
    with os.fdopen(fd, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)  # Glance never reads a half-written file


def last_ok(con, source):
    """Newest successful backup as RFC 3339 UTC, or "" if unknown."""
    kind, _, name = source.partition(":")
    if kind == "kuma":
        row = con.execute(
            "SELECT max(h.time) FROM heartbeat h JOIN monitor m ON m.id = h.monitor_id WHERE m.name = ? AND h.status = 1",
            (name,)).fetchone()
        return row[0][:19].replace(" ", "T") + "Z" if row and row[0] else ""
    if kind == "systemd":
        # Kept by systemd until the next reboot; empty after one, until the next run.
        props = dict(l.split("=", 1) for l in subprocess.run(
            ["systemctl", "show", name, "-p", "Result", "-p", "ExecMainExitTimestamp"],
            capture_output=True, text=True).stdout.splitlines() if "=" in l)
        ts = props.get("ExecMainExitTimestamp", "")
        if props.get("Result") != "success" or not ts:
            return ""
        return datetime.strptime(ts, "%a %Y-%m-%d %H:%M:%S %Z").strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


def recovery(con):
    try:
        with open(OBJECTIVES) as f:
            comps = json.load(f)["components"]
    except (OSError, ValueError, KeyError):
        return []
    rows, now = [], time.time()
    for c in comps:
        ts = last_ok(con, c.get("backup", "")) if c.get("backup") else ""
        row = {k: c.get(k, "") for k in ("name", "rto", "rpo", "proven", "backup_label")}
        row["last_ok"] = ts
        m = re.match(r"(\d+)\s*h", c.get("rpo", ""))
        if ts and m:
            age_h = (now - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()) / 3600
            row["rpo_state"] = "ok" if age_h <= int(m.group(1)) + RPO_GRACE_H else "bad"
        else:
            row["rpo_state"] = "unknown" if c.get("backup") else "static"
        rows.append(row)
    return rows


if __name__ == "__main__":
    main()
