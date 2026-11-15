#!/usr/bin/env python3
"""Public page data built at deploy time from the repo. Prints JSON to stdout;
deploy-dmz.yml copies it into Glance's assets.

  build_track_record.py REPO          track record (FND-22): latest incident
                                      reviews with their first lesson, and
                                      commits in the last 30 days
  build_track_record.py REPO --docs   docs index (FND-23): every ADR, incident
                                      review, DR scenario and runbook

Everything here is already public in the repository.
"""
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

GH = "https://github.com/ChetanThapliyal/Project-Aether/blob/main/"
# Internal work-item IDs (chores, DR stages) mean nothing to a visitor and
# HARD-17 keeps them off the public page.
WORK_ID = re.compile(r"\s*\((?:DR|HARD|FND|GOP|OPS|SEC|IaC)-\d+\)|\b(?:DR|HARD|FND|GOP|OPS|SEC|IaC)-\d+\b\s*")


def public(text):
    return re.sub(r"\s{2,}", " ", WORK_ID.sub("", text)).strip()
LATEST = 4


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


def incidents(repo, lessons=True):
    rows = []
    index = (repo / "docs/incidents/README.md").read_text()
    for m in re.finditer(r"^\| \[(INC-\d{4}-\d{3})\]\(([^)]+)\) \| (\d{4}-\d{2}-\d{2}) \| ([^|]+) \| (SEV\d) \|", index, re.M):
        inc, fname, date, title, sev = m.groups()
        row = {"id": inc, "date": date, "title": title.strip(), "severity": sev, "url": GH + "docs/incidents/" + fname}
        if lessons:
            row["lesson"] = first_lesson(repo / "docs/incidents" / fname)
        rows.append(row)
    if not rows:
        sys.exit("no incidents parsed from docs/incidents/README.md")
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return rows


def when(value):
    """(datetime, precise) from a review field: 'YYYY-MM-DD HH:MM', a bare date
    (day precision), or None when unknown."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?: (\d{2}:\d{2}))?", value.strip())
    if not m:
        return None
    return datetime.fromisoformat(m.group(1) + " " + (m.group(2) or "00:00")), bool(m.group(2))


def span_hours(a, b):
    """Hours from a to b. When either is only a date, count whole days."""
    if not a or not b:
        return None
    if a[1] and b[1]:
        return max(0.0, (b[0] - a[0]).total_seconds() / 3600)
    return max(0, (b[0].date() - a[0].date()).days) * 24.0


def human(hours):
    if hours is None:
        return ""
    if hours < 1:
        return f"{max(1, round(hours * 60))} min"
    if hours < 48:
        return f"{round(hours)} h"
    return f"{round(hours / 24)} days"


def response(repo, rows):
    """Time to detect and to restore, from each review's Started / Detected /
    Resolved fields, grouped by how the incident was found."""
    index = (repo / "docs/incidents/README.md").read_text()
    found = dict(re.findall(r"^\| \[(INC-\d{4}-\d{3})\]\([^)]+\) \|[^|]+\|[^|]+\|[^|]+\| ([^|]+) \|", index, re.M))
    per = []
    for r in rows:
        text = (repo / "docs/incidents" / r["url"].rsplit("/", 1)[1]).read_text()
        field = lambda k: (re.search(rf"^\| {k} \| ([^|]+) \|", text, re.M) or [None, ""])[1]
        st, de, rs = when(field("Started")), when(field("Detected")), when(field("Resolved"))
        if not de or not rs:
            sys.exit(f"{r['id']}: Detected and Resolved fields are required")
        how = found.get(r["id"], "").strip()
        per.append({"found": "alert" if how.lower().startswith("alert") else "other",
                    "detect_h": span_hours(st, de), "restore_h": span_hours(de, rs),
                    "change": field("Cause").strip().lower().startswith("change")})
    med = lambda xs: statistics.median(xs) if xs else None
    alert = [p for p in per if p["found"] == "alert"]
    other = [p for p in per if p["found"] == "other"]
    return {
        "total": len(per),
        "by_alert": len(alert),
        "detect_alert": human(med([p["detect_h"] for p in alert if p["detect_h"] is not None])),
        "detect_other": human(med([p["detect_h"] for p in other if p["detect_h"] is not None])),
        "detect_other_known": sum(1 for p in other if p["detect_h"] is not None),
        "restore": human(med([p["restore_h"] for p in per])),
        "restore_alert": human(med([p["restore_h"] for p in alert])),
        "caused_by_change": sum(1 for p in per if p["change"]),
    }


def adrs(repo):
    out = []
    for f in sorted((repo / "docs/adr").glob("[0-9][0-9][0-9]-*.md")):
        text = f.read_text()
        t = re.search(r"ADR-(\d{3}):\s*(.+)", text)
        st = re.search(r"\*\*Status:\*\*\s*([^\n]+)", text)
        if not t:
            sys.exit(f"no 'ADR-NNN: title' line in {f.name}")
        status = re.split(r"[(;,.]", st.group(1))[0].strip() if st else "Unknown"
        out.append({"num": t.group(1), "title": public(t.group(2)), "status": status, "url": GH + "docs/adr/" + f.name})
    return out


def dr_scenarios(repo):
    out = []
    readme = (repo / "docs/disaster-recovery/README.md").read_text()
    for m in re.finditer(r"^\| \[(\d{2}): ([^\]]+)\]\((scenarios/[^)]+)\) \| (SEV\d) \| ([^|]+) \|", readme, re.M):
        num, title, path, sev, drilled = m.groups()
        drilled = public(drilled)
        out.append({"num": num, "title": public(title), "severity": sev, "url": GH + "docs/disaster-recovery/" + path,
                    "last_drilled": drilled, "drilled": "not recorded" not in drilled.lower()})
    if not out:
        sys.exit("no scenarios parsed from docs/disaster-recovery/README.md")
    return out


def runbooks(repo):
    out = []
    for f in sorted((repo / "docs/runbooks").glob("*.md")):
        h1 = re.search(r"^# (.+)$", f.read_text(), re.M)
        title = h1.group(1).strip() if h1 else f.stem.replace("-", " ")
        out.append({"title": public(re.sub(r"\s+runbook$", "", title, flags=re.I)), "url": GH + "docs/runbooks/" + f.name})
    return out


def commits_30d(repo):
    return int(subprocess.run(["git", "-C", str(repo), "rev-list", "--count", "--since=30.days", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip())


def main():
    repo = Path(sys.argv[1]).resolve()
    if "--docs" in sys.argv[2:]:
        data = {"adrs": adrs(repo), "incidents": incidents(repo, lessons=False),
                "dr": dr_scenarios(repo), "runbooks": runbooks(repo)}
        data["counts"] = {k: len(v) for k, v in data.items()}
    else:
        inc = incidents(repo)
        data = {"incidents": {"total": len(inc), "last_date": inc[0]["date"] + "T00:00:00Z", "latest": inc[:LATEST]},
                "response": response(repo, inc),
                "delivery": {"commits_30d": commits_30d(repo)}}
    print(json.dumps(data, separators=(",", ":")))


if __name__ == "__main__":
    main()
