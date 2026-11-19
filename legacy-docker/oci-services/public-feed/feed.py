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
  * Visits to the status page come from Cloudflare Web Analytics (counts only),
    kept as one number per day in STATE_DIR so the total outlives Cloudflare's
    retention. Headless browsers (our own test runs) are not counted.

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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROM = os.environ.get("PROM_URL", "http://prometheus:9090")
INTERVAL = int(os.environ.get("INTERVAL", "300"))
PORT = int(os.environ.get("PORT", "8080"))
STALE_AFTER = int(os.environ.get("STALE_AFTER", "900"))

# Visits (Cloudflare Web Analytics). Without a token the page shows "unknown".
CF_GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
CF_TOKEN = os.environ.get("CF_API_TOKEN", "")
CF_ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "")
CF_HOST = os.environ.get("CF_HOST", "status.chetan-thapliyal.cloud")
VISITS_SINCE = os.environ.get("VISITS_SINCE", "2026-11-12")  # the page's first day online
STATE_DIR = os.environ.get("STATE_DIR", "/state")
VISITS_EVERY = 3600       # ask Cloudflare at most hourly
VISITS_REFETCH_DAYS = 3   # recent days are re-read, so late or partial counts settle
VISITS_STALE_DAYS = 2     # no good fetch for this long: show "unknown"

# Charts: 6 hours at 5-minute steps, drawn in a 300 x 80 viewBox.
RANGE_S, STEP_S = 6 * 3600, 300
CHART_W, CHART_H, CHART_PAD = 300.0, 80.0, 6.0

K3S = 'job="k3s-node-exporter"'
HYP = 'job="proxmox-host"'
OCI = 'job="node-exporter"'
DMZ = 'job="gcp-dmz-node"'  # FND-14 node exporter on the edge host
NET_DEV = 'device!~"lo|veth.*|cni.*|flannel.*|tailscale.*|docker.*|br-.*"'

SCALARS = {
    "nodes_ready": 'sum(kube_node_status_condition{condition="Ready",status="true"})',
    "nodes_total": "count(kube_node_info)",
    "apps_ok": 'count(argocd_app_info{sync_status="Synced",health_status="Healthy"}) or vector(0)',
    "apps_total": "count(argocd_app_info)",
    "pods_running": 'sum(kube_pod_status_phase{phase="Running"})',
    # FND-21: finished job pods (Succeeded) never run again, so counting them
    # made "running / total" look like a fault forever.
    "pods_total": 'sum(kube_pod_status_phase{phase!="Succeeded"})',
    # FND-22: delivery over the last week (counts only; Prometheus keeps 30 days)
    "syncs_7d": "sum(increase(argocd_app_sync_total[7d])) or vector(0)",
    "syncs_failed_7d": 'sum(increase(argocd_app_sync_total{phase!="Succeeded"}[7d])) or vector(0)',
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
    # FND-22: the edge host's own usage, and cluster network throughput (MB/s, in + out)
    "dmz_cpu_pct": f'100 * (1 - avg(rate(node_cpu_seconds_total{{{DMZ},mode="idle"}}[5m])))',
    "dmz_mem_pct": f"100 * (1 - sum(node_memory_MemAvailable_bytes{{{DMZ}}}) / sum(node_memory_MemTotal_bytes{{{DMZ}}}))",
    "dmz_disk_pct": f'100 * (1 - max(node_filesystem_avail_bytes{{{DMZ},mountpoint="/"}}) / max(node_filesystem_size_bytes{{{DMZ},mountpoint="/"}}))',
    "cluster_net_mbs": f"(sum(rate(node_network_receive_bytes_total{{{K3S},{NET_DEV}}}[5m])) + sum(rate(node_network_transmit_bytes_total{{{K3S},{NET_DEV}}}[5m]))) / 1e6",
}

# name: (PromQL, hard floor, hard ceiling (None: open), smallest y span, unit).
# FND-22: the y-axis fits the data with some padding, inside the hard limits,
# and never narrower than the smallest span, so a quiet line isn't drawn as a cliff.
SERIES = {
    "cluster_cpu": (SCALARS["cluster_cpu_pct"], 0, 100, 10, "%"),
    "cluster_mem": (SCALARS["cluster_mem_pct"], 0, 100, 10, "%"),
    "oci_cpu": (SCALARS["oci_cpu_pct"], 0, 100, 10, "%"),
    "oci_mem": (SCALARS["oci_mem_pct"], 0, 100, 10, "%"),
    "hyp_temp": (SCALARS["hyp_temp_c"], 20, 105, 10, "°C"),
    "cluster_net": (SCALARS["cluster_net_mbs"], 0, None, 0.5, " MB/s"),
}

# Hypervisor disks and ZFS pool, as one line on the page: counts and yes/no only,
# never disk, pool or host names. Aggregated over every disk and pool.
STORAGE = {
    "disks_total": "count(smartmon_device_smart_healthy)",
    "disks_healthy": "count(smartmon_device_smart_healthy == 1)",  # empty, not 0, when none is
    "pools_total": 'count(node_zfs_zpool_state{state="online"})',
    "pools_online": 'count(node_zfs_zpool_state{state="online"} == 1)',
    "oldest_scrub_ts": "min(aether_zfs_pool_last_scrub_timestamp_seconds)",  # 0: never scrubbed
    "device_errors": "sum(aether_zfs_pool_device_errors)",
    "scrub_errors": "sum(aether_zfs_pool_scrub_errors)",
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


def nice_range(vals, floor, ceil, min_span):
    """A y-range around the data: 15% padding, at least min_span wide, rounded
    to tidy numbers, and kept inside [floor, ceil]."""
    lo, hi = min(vals), max(vals)
    pad = max((hi - lo) * 0.15, min_span / 2 - (hi - lo) / 2, 0)
    lo, hi = lo - pad, hi + pad
    step = 10 ** math.floor(math.log10(max(hi - lo, 1e-9)))
    step = step / 2 if (hi - lo) / step < 3 else step
    lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step
    if lo < floor:
        hi, lo = hi + (floor - lo), floor
    if ceil is not None and hi > ceil:
        lo, hi = max(floor, lo - (hi - ceil)), ceil
    return round(lo, 2), round(hi, 2)


def series(q, floor, ceil, min_span):
    end = time.time()
    res = prom("/api/v1/query_range", {"query": q, "start": end - RANGE_S, "end": end, "step": STEP_S})
    if not res:
        return None
    pts = [(float(t), float(v)) for t, v in res[0]["values"] if v not in ("NaN", "+Inf", "-Inf")]
    if len(pts) < 2:
        return None
    lo, hi = nice_range([v for _, v in pts], floor, ceil, min_span)
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
    nd = 1 if max(abs(v) for v in vals) >= 1 else 2  # small units (MB/s) keep two decimals
    return {"line": line, "area": area, "last": round(vals[-1], nd), "min": round(min(vals), nd),
            "max": round(max(vals), nd), "lo": lo, "hi": hi,
            "mid": round((lo + hi) / 2, 2)}


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


def storage():
    """Missing metrics give null, which the page shows as "unknown": a healthy
    value is never assumed."""
    v = {k: scalar(q) for k, q in STORAGE.items()}
    total, pools = v["disks_total"], v["pools_total"]
    ts = v["oldest_scrub_ts"]
    errs = None if v["device_errors"] is None or v["scrub_errors"] is None else v["device_errors"] + v["scrub_errors"]
    return {
        "disks_total": None if total is None else int(total),
        "disks_healthy": None if total is None else int(v["disks_healthy"] or 0),
        "pool_online": None if pools is None else int(v["pools_online"] or 0) == int(pools),
        "scrub_age_days": None if ts is None or ts <= 0 else max(0, int((time.time() - ts) // 86400)),
        "errors": None if errs is None else int(errs),
    }


_visits = {"checked": 0.0}


def cf_daily_visits(start, end):
    """{date: visits} for the status page, UTC days start..end inclusive."""
    query = """query($a:String!,$f:AccountRumPageloadEventsAdaptiveGroupsFilter_InputObject){
      viewer{accounts(filter:{accountTag:$a}){
        rumPageloadEventsAdaptiveGroups(limit:1000,filter:$f){sum{visits} dimensions{date}}}}}"""
    flt = {"date_geq": start.isoformat(), "date_leq": end.isoformat(),
           "requestHost": CF_HOST, "userAgentBrowser_neq": "ChromeHeadless"}
    req = urllib.request.Request(
        CF_GRAPHQL, data=json.dumps({"query": query, "variables": {"a": CF_ACCOUNT, "f": flt}}).encode(),
        headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(f"cloudflare: {data['errors'][0].get('message', 'query failed')[:200]}")
    days = {}
    for g in data["data"]["viewer"]["accounts"][0]["rumPageloadEventsAdaptiveGroups"]:
        d = g["dimensions"]["date"]
        days[d] = days.get(d, 0) + int(g["sum"]["visits"])
    return days


def visits():
    """Visits in the last 30 days and since the first day, from the daily log.
    Each day is stored by date, so re-reading a day replaces it, never adds twice."""
    path = os.path.join(STATE_DIR, "visits.json")
    try:
        with open(path) as f:
            log = json.load(f)
    except (OSError, ValueError):
        log = {"days": {}, "fetched_at": 0}
    today = datetime.now(timezone.utc).date()
    if CF_TOKEN and CF_ACCOUNT and time.time() - _visits["checked"] >= VISITS_EVERY:
        _visits["checked"] = time.time()
        first = datetime.strptime(VISITS_SINCE, "%Y-%m-%d").date()
        start = first
        if log["days"]:
            last = datetime.strptime(max(log["days"]), "%Y-%m-%d").date()
            start = max(first, last - timedelta(days=VISITS_REFETCH_DAYS))
        start = max(start, today - timedelta(days=180))  # Cloudflare keeps about 26 weeks
        try:
            got = {}
            while start <= today:  # one query may span at most about 13 weeks
                end = min(today, start + timedelta(days=89))
                got.update(cf_daily_visits(start, end))
                for n in range((end - start).days + 1):  # a day with no visits is a real 0
                    got.setdefault((start + timedelta(days=n)).isoformat(), 0)
                start = end + timedelta(days=1)
            log["days"].update(got)
            log["fetched_at"] = int(time.time())
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(log, f, sort_keys=True)
            os.replace(tmp, path)
        except Exception as e:  # keep the log as it was; the page goes "unknown" if this lasts
            print(f"visits fetch failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
    if not log["days"] or time.time() - log["fetched_at"] > VISITS_STALE_DAYS * 86400:
        return {"visits_30d": None, "visits_total": None, "since": None}
    cutoff = (today - timedelta(days=29)).isoformat()
    first = min(log["days"])
    return {
        "visits_30d": sum(v for d, v in log["days"].items() if d >= cutoff),
        "visits_total": sum(log["days"].values()),
        "since": datetime.strptime(first, "%Y-%m-%d").strftime("%b %Y"),
    }


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
        "delivery": {"syncs_7d": int(round(s["syncs_7d"] or 0)),
                     "syncs_failed_7d": int(round(s["syncs_failed_7d"] or 0))},
        "edge": {k: r(s[f"dmz_{k}"]) for k in ("cpu_pct", "mem_pct", "disk_pct")},
        "host": {"temp_c": r(s["hyp_temp_c"], 0), "uptime_days": r(s["hyp_uptime_days"], 1),
                 "cpu_pct": r(s["hyp_cpu_pct"])},
        "gauges": [],
        "charts": {},
        "versions": versions(),
        "storage": storage(),
        "visitors": visits(),
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
    for name, (q, floor, ceil, min_span, unit) in SERIES.items():
        c = series(q, floor, ceil, min_span)
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
    vis = summary["visitors"]
    if any(v is not None and type(v) is not int for v in (vis["visits_30d"], vis["visits_total"])) \
            or not (vis["since"] is None or re.fullmatch(r"[A-Z][a-z]{2} \d{4}", vis["since"])):
        raise ValueError(f"unexpected visitors block {vis!r}")


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
