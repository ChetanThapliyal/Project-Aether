#!/usr/bin/env python3
"""FND-22: check the public page against cloudflare-response-headers.yml.

1. Every inline <script> Glance renders on each page must have its sha256 in
   the CSP script-src list. A Glance upgrade changes them; this prints the new
   values to put in the file (and in the Cloudflare rule).
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


def load(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    hashes = " ".join(f"'{h}'" for h in cfg["csp_script_hashes"].values())
    csp = "; ".join(d.replace("{hashes}", hashes) for d in cfg["csp_directives"])
    name = "Content-Security-Policy" if cfg["csp_mode"] == "enforce" else "Content-Security-Policy-Report-Only"
    want = dict(cfg["headers"])
    want[name] = csp
    return cfg, want


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "aether-header-check"})
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
    allowed = set(cfg["csp_script_hashes"].values())
    live_headers = None
    for slug in [""] + list(cfg["csp_script_hashes"]):
        try:
            html, headers = fetch(f"{a.base}/{slug}")
        except Exception as e:  # noqa: BLE001
            print(f"FETCH FAILED /{slug}: {e}")
            return 2
        live_headers = live_headers or headers
        for body in re.findall(r"<script>(.*?)</script>", html, re.S):
            h = "sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
            if h not in allowed:
                problems.append(f"/{slug}: inline script hash {h} is not in csp_script_hashes")

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
