#!/usr/bin/env python3
"""docs/README.md must link every document under docs/ (5.56).

Tracked Markdown, YAML and SVG files count; docs/git-ignored/ and the diagram
builders' Python don't. A file linked from a section README that the index
links (docs/incidents/README.md) counts as listed. Every link must point at a
file that exists. Runs as a pre-commit hook, so CI runs it too.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/README.md"
KINDS = (".md", ".yml", ".svg")
# Not documents: the status page's copies of blog diagrams built elsewhere, and the banner.
SKIP = re.compile(r"^docs/(git-ignored/|diagrams/(blog-|banner))")



def links_in(page):
    return {(page.parent / m).resolve() for m in re.findall(r"\]\(([^)#\s]+)", page.read_text())
            if "://" not in m}


# A document is listed if the index links it, or links a section README that does
# (the incident reviews are listed in docs/incidents/README.md, not here).
links = links_in(INDEX)
for sub in [p for p in links if p.name == "README.md" and p.exists() and p != INDEX]:
    links |= links_in(sub)
missing_targets = sorted(str(p.relative_to(ROOT)) for p in links if not p.exists())

tracked = subprocess.run(["git", "ls-files", "docs"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout.split()
unlisted = [f for f in tracked
            if f.endswith(KINDS) and f != "docs/README.md" and not SKIP.match(f)
            and (ROOT / f).resolve() not in links]

for f in unlisted:
    print(f"docs/README.md does not link {f}")
for f in missing_targets:
    print(f"docs/README.md links {f}, which does not exist")
sys.exit(1 if unlisted or missing_targets else 0)
