#!/usr/bin/env python3
"""FND-22: check the public page against cloudflare-response-headers.yml.

1. Every inline <script> Glance renders on each page, under each theme, must
   have its sha256 in the CSP script-src list. The script names the theme from
   the visitor's "theme" cookie, so each page is fetched once per theme with
   that cookie. A Glance upgrade changes them; this prints the new values to put
   in the file (and in the Cloudflare rule).
2. Once the Cloudflare rule exists (any CSP header present), every header must
   equal the file, so the dashboard and the repo can't drift apart.

--print-rule prints the header values to paste into Cloudflare and exits.
Exit 0 = OK, 1 = mismatch, 2 = could not fetch.
"""
import argparse
import base64
import hashlib
import re
import sys
import urllib.request

import yaml


def all_hashes(cfg):
    """csp_script_hashes is theme -> page -> hash; script-src lists them all."""
    return [h for pages in cfg["csp_script_hashes"].values() for h in pages.values()]


def load(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    hashes = " ".join(f"'{h}'" for h in all_hashes(cfg))
    csp = "; ".join(d.replace("{hashes}", hashes) for d in cfg["csp_directives"])
    name = "Content-Security-Policy" if cfg["csp_mode"] == "enforce" else "Content-Security-Policy-Report-Only"
    want = dict(cfg["headers"])
    want[name] = csp
    return cfg, want


def fetch(url, theme=None):
    headers = {"User-Agent": "aether-header-check"}
    if theme:
        headers["Cookie"] = f"theme={theme}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace"), r.headers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--base", default="https://status.chetan-thapliyal.cloud")
    ap.add_argument("--print-rule", action="store_true")
    a = ap.parse_args()
    cfg, want = load(a.config)

    if a.print_rule:
        for k, v in want.items():
            print(f"{k}\n  {v}\n")
        return 0

    problems = []
    live_headers = None
    for theme, pages in cfg["csp_script_hashes"].items():
        for slug in [""] + list(pages):
            want_hash = pages.get(slug or "overview")
            try:
                html, headers = fetch(f"{a.base}/{slug}", theme)
            except Exception as e:  # noqa: BLE001
                print(f"FETCH FAILED /{slug} (theme {theme}): {e}")
                return 2
            live_headers = live_headers or headers
            for body in re.findall(r"<script>(.*?)</script>", html, re.S):
                h = "sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                if h != want_hash:
                    problems.append(f"/{slug} (theme {theme}): inline script hash {h} != csp_script_hashes.{theme}.{slug or 'overview'}")

    has_csp = any(live_headers.get(n) for n in ("Content-Security-Policy", "Content-Security-Policy-Report-Only"))
    if has_csp:
        for k, v in want.items():
            got = live_headers.get(k)
            if got != v:
                problems.append(f"header {k}: live {got!r} != file")
    else:
        print("NOTE: no CSP header on the live page yet (Cloudflare rule not set); hashes checked only")

    for p in problems:
        print("MISMATCH " + p)
    if not problems:
        print("OK: script hashes match" + ("; live headers equal the file" if has_csp else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
