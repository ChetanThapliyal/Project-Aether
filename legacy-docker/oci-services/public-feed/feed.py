#!/usr/bin/env python3
"""Project Aether public feed (FND-20, ADR-020).

Builds a sanitised summary of the estate from Prometheus every INTERVAL seconds
and serves it as /summary.json for the public Glance page on the DMZ.

Rules:
  * Only aggregates and fixed labels leave this process: no hostnames, node
    names, IPs or label values from Prometheus, except container image names
    (repository:tag), which are public anyway.
  * Every value is a number or a plain string; the page draws the charts itself.
  * A summary that fails the allow-list check is never published. The last good
    one keeps being served and `fresh` goes false once it is 15 minutes old.

Standard library only, so the container needs no packages.
"""
import json
import math
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROM = os.environ.get("PROM_URL", "http://prometheus:9090")
INTERVAL = int(os.environ.get("INTERVAL", "300"))
PORT = int(os.environ.get("PORT", "8080"))
STALE_AFTER = int(os.environ.get("STALE_AFTER", "900"))

# Charts: 6 hours at 5-minute steps, drawn in a 300 x 80 viewBox.
RANGE_S, STEP_S = 6 * 3600, 300
CHART_W, CHART_H, CHART_PAD = 300.0, 80.0, 6.0

K3S = 'job="k3s-node-exporter"'
HYP = 'job="proxmox-host"'
OCI = 'job="node-exporter"'

SCALARS = {
    "nodes_ready": 'sum(kube_node_status_condition{condition="Ready",status="true"})',
    "nodes_total": "count(kube_node_info)",
    "apps_ok": 'count(argocd_app_info{sync_status="Synced",health_status="Healthy"}) or vector(0)',
    "apps_total": "count(argocd_app_info)",
    "pods_running": 'sum(kube_pod_status_phase{phase="Running"})',
    "pods_total": "sum(kube_pod_status_phase)",
    "targets_up": "count(up == 1)",
    "targets_total": "count(up)",
    "alerts_firing": 'count(ALERTS{alertstate="firing",alertname!="Watchdog"}) or vector(0)',
    "cluster_cpu_pct": f'100 * (1 - avg(rate(node_cpu_seconds_total{{{K3S},mode="idle"}}[5m])))',
    "cluster_mem_pct": f"100 * (1 - sum(node_memory_MemAvailable_bytes{{{K3S}}}) / sum(node_memory_MemTotal_bytes{{{K3S}}}))",
    "hyp_cpu_pct": f'100 * (1 - avg(rate(node_cpu_seconds_total{{{HYP},mode="idle"}}[5m])))',
    "hyp_mem_pct": f"100 * (1 - sum(node_memory_MemAvailable_bytes{{{HYP}}}) / sum(node_memory_MemTotal_bytes{{{HYP}}}))",
    "hyp_temp_c": f'max(node_hwmon_temp_celsius{{{HYP},chip="platform_coretemp_0"}})',
    "hyp_root_pct": f'100 * (1 - max(node_filesystem_avail_bytes{{{HYP},mountpoint="/"}}) / max(node_filesystem_size_bytes{{{HYP},mountpoint="/"}}))',
    "hyp_uptime_days": f"(time() - max(node_boot_time_seconds{{{HYP}}})) / 86400",
    "oci_cpu_pct": f'100 * (1 - avg(rate(node_cpu_seconds_total{{{OCI},mode="idle"}}[5m])))',
    "oci_mem_pct": f"100 * (1 - sum(node_memory_MemAvailable_bytes{{{OCI}}}) / sum(node_memory_MemTotal_bytes{{{OCI}}}))",
    "oci_disk_pct": f'100 * (1 - max(node_filesystem_avail_bytes{{{OCI},mountpoint="/"}}) / max(node_filesystem_size_bytes{{{OCI},mountpoint="/"}}))',
}

# name: (PromQL, y-axis min, y-axis max, unit)
SERIES = {
    "cluster_cpu": (SCALARS["cluster_cpu_pct"], 0, 100, "%"),
    "cluster_mem": (SCALARS["cluster_mem_pct"], 0, 100, "%"),
    "hyp_temp": (SCALARS["hyp_temp_c"], 20, 100, "°C"),
    "oci_cpu": (SCALARS["oci_cpu_pct"], 0, 100, "%"),
}

GAUGES = [  # (label, scalar key, group shown under the gauge)
    ("Cluster CPU", "cluster_cpu_pct", "K3s, 3 nodes"),
    ("Cluster memory", "cluster_mem_pct", "K3s, 3 nodes"),
    ("Host memory", "hyp_mem_pct", "Proxmox host"),
    ("Host disk", "hyp_root_pct", "Proxmox SSD"),
    ("Cloud memory", "oci_mem_pct", "Oracle Cloud"),
    ("Cloud disk", "oci_disk_pct", "Oracle Cloud"),
]

# Anything matching these must never reach the public page.
FORBIDDEN = re.compile(
    r"ts\.net|tail[0-9a-f]{6}|192\.168\.|\b10\.4[0-9]\.|\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\."
    r"|k3s-(control|worker)|bookorbit|homelab|aether-gcp|proxmox-host|:9100",
    re.IGNORECASE,
)
GAUGE_R = 26.0
GAUGE_C = 2 * math.pi * GAUGE_R

_state = {"body": None, "generated": 0.0, "error": "starting"}
_lock = threading.Lock()


def prom(path, params):
    url = f"{PROM}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    if data.get("status") != "success":
        raise RuntimeError(f"prometheus: {data.get('error', 'query failed')}")
    return data["data"]["result"]


def scalar(q):
    res = prom("/api/v1/query", {"query": q})
    if not res:
        return None
    v = float(res[0]["value"][1])
    return None if math.isnan(v) or math.isinf(v) else v


def series(q, lo, hi):
    end = time.time()
    res = prom("/api/v1/query_range", {"query": q, "start": end - RANGE_S, "end": end, "step": STEP_S})
    if not res:
        return None
    pts = [(float(t), float(v)) for t, v in res[0]["values"] if v not in ("NaN", "+Inf", "-Inf")]
    if len(pts) < 2:
        return None
    t0 = end - RANGE_S
    span = hi - lo
    coords = []
    for t, v in pts:
        x = max(0.0, min(CHART_W, (t - t0) / RANGE_S * CHART_W))
        y = CHART_H - CHART_PAD - (min(max(v, lo), hi) - lo) / span * (CHART_H - 2 * CHART_PAD)
        coords.append(f"{x:.1f},{y:.1f}")
    line = " ".join(coords)
    first_x, last_x = coords[0].split(",")[0], coords[-1].split(",")[0]
    area = f"{first_x},{CHART_H:.0f} {line} {last_x},{CHART_H:.0f}"
    vals = [v for _, v in pts]
    return {"line": line, "area": area, "last": round(vals[-1], 1), "min": round(min(vals), 1),
            "max": round(max(vals), 1), "lo": lo, "hi": hi}


def versions():
    res = prom("/api/v1/query", {"query": "count by (image) (kube_pod_container_info)"})
    seen = {}
    for r in res:
        img = r["metric"].get("image", "")
        if img.startswith("sha256:"):  # running by digest only: no name to show
            continue
        img = img.split("@", 1)[0]
        if "/" in img and "." in img.split("/", 1)[0]:  # drop the registry host
            img = img.split("/", 1)[1]
        name, _, tag = img.rpartition(":") if ":" in img.split("/")[-1] else (img, "", "latest")
        for prefix in ("docker/library/", "library/"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        if name:
            seen[name] = tag
    return [{"image": n, "tag": t} for n, t in sorted(seen.items())]


def build():
    s = {k: scalar(q) for k, q in SCALARS.items()}
    r = lambda v, n=1: None if v is None else round(v, n)
    kv = prom("/api/v1/query", {"query": "count by (kubelet_version) (kube_node_info)"})
    k3s = kv[0]["metric"].get("kubelet_version", "") if kv else ""
    summary = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cluster": {
            "nodes_ready": int(s["nodes_ready"] or 0), "nodes_total": int(s["nodes_total"] or 0),
            "apps_ok": int(s["apps_ok"] or 0), "apps_total": int(s["apps_total"] or 0),
            "pods_running": int(s["pods_running"] or 0), "pods_total": int(s["pods_total"] or 0),
            "k3s_version": k3s.split("+")[0],
        },
        "monitoring": {
            "targets_up": int(s["targets_up"] or 0), "targets_total": int(s["targets_total"] or 0),
            "alerts_firing": int(s["alerts_firing"] or 0),
        },
        "host": {"temp_c": r(s["hyp_temp_c"], 0), "uptime_days": r(s["hyp_uptime_days"], 1),
                 "cpu_pct": r(s["hyp_cpu_pct"])},
        "gauges": [],
        "charts": {},
        "versions": versions(),
    }
    for label, key, group in GAUGES:
        v = s[key]
        if v is None:
            continue
        pct = max(0.0, min(100.0, v))
        summary["gauges"].append({
            "label": label, "group": group, "pct": round(pct, 1),
            "dash": round(GAUGE_C * pct / 100, 2), "gap": round(GAUGE_C, 2),
            "level": "high" if pct >= 85 else ("warn" if pct >= 70 else "ok"),
        })
    for name, (q, lo, hi, unit) in SERIES.items():
        c = series(q, lo, hi)
        if c:
            c["unit"] = unit
            summary["charts"][name] = c
    return summary


def check(summary):
    text = json.dumps(summary)
    m = FORBIDDEN.search(text)
    if m:
        raise ValueError(f"allow-list violation near {text[max(0, m.start() - 20):m.end() + 20]!r}")
    for v in summary["versions"]:
        if not re.fullmatch(r"[a-z0-9._/-]+", v["image"]) or not re.fullmatch(r"[A-Za-z0-9._+-]{1,64}", v["tag"]):
            raise ValueError(f"unexpected image string {v!r}")


def loop():
    while True:
        try:
            s = build()
            check(s)
            body = json.dumps(s, separators=(",", ":"))
            with _lock:
                _state.update(body=body, generated=time.time(), error=None)
            print(f"{s['generated_at']} published {len(body)} bytes", flush=True)
        except Exception as e:  # keep serving the last good summary
            with _lock:
                _state["error"] = f"{type(e).__name__}: {e}"
            print(f"build failed: {_state['error']}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


class Handler(BaseHTTPRequestHandler):
    server_version = "aether-feed"
    sys_version = ""

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._send(200, b"ok\n", "text/plain")
        if path != "/summary.json":
            return self._send(404, b"not found\n", "text/plain")
        with _lock:
            body, generated, error = _state["body"], _state["generated"], _state["error"]
        if body is None:
            return self._send(503, json.dumps({"fresh": False, "error": "no summary yet"}).encode(), "application/json")
        age = int(time.time() - generated)
        out = json.loads(body)
        out["age_seconds"] = age
        out["fresh"] = age < STALE_AFTER          # the page and the Kuma monitor key off this
        out["build_ok"] = error is None           # false: last build failed, older summary served
        self._send(200, json.dumps(out, separators=(",", ":")).encode(), "application/json")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep logs to publish events only
        pass


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
