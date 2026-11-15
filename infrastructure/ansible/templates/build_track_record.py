#!/usr/bin/env python3
"""FND-22: the public page's track record, built at deploy time from the repo.

Prints JSON to stdout (deploy-dmz.yml copies it into Glance's assets):
- incidents: the latest reviews from docs/incidents/README.md, each with its
  first lesson, plus the total and the date of the most recent one;
- delivery: commits on the current branch in the last 30 days.

Everything here is already public in the repository.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
LATEST = 4
GH = "https://github.com/ChetanThapliyal/Project-Aether/blob/main/docs/incidents/"


def first_lesson(path):
    text = path.read_text()
    m = re.search(r"^## Lessons?\s*\n(.*?)(?:\n## |\Z)", text, re.S | re.M)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ")):
            return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line[2:]).replace("`", "").strip()
    return ""


def incidents():
    rows = []
    index = (REPO / "docs/incidents/README.md").read_text()
    for m in re.finditer(r"^\| \[(INC-\d{4}-\d{3})\]\(([^)]+)\) \| (\d{4}-\d{2}-\d{2}) \| ([^|]+) \| (SEV\d) \|", index, re.M):
        inc, fname, date, title, sev = m.groups()
        rows.append({"id": inc, "date": date, "title": title.strip(), "severity": sev,
                     "url": GH + fname, "lesson": first_lesson(REPO / "docs/incidents" / fname)})
    if not rows:
        sys.exit("no incidents parsed from docs/incidents/README.md")
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return {"total": len(rows), "last_date": rows[0]["date"] + "T00:00:00Z", "latest": rows[:LATEST]}


def delivery():
    git = ["git", "-C", str(REPO)]
    commits = subprocess.run(git + ["rev-list", "--count", "--since=30.days", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
    return {"commits_30d": int(commits)}


print(json.dumps({"incidents": incidents(), "delivery": delivery()}, separators=(",", ":")))
