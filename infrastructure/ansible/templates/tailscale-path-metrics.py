#!/usr/bin/env python3
# Managed by Ansible (oci-monitoring.yml). INC-2026-011 follow-up, built in INC-2026-017.
#
# Prometheus scrapes the homelab over the tailnet from this host. A peer that
# loses its direct path falls back to a DERP relay, and a relay stalls for
# minutes at a time: scrapes time out and node-down alerts flap. This writes,
# for each peer Prometheus scrapes, whether this host reaches it directly, so
# TailnetPeerRelayed can fire before the scrapes start to suffer.
#
# CurAddr is set only while the path is direct. Relay always names the peer's
# home DERP region, direct or not, so it can't be used to tell.
import json
import os
import subprocess
import tempfile
import time

PEERS = {{ tailscale_path_peers | to_json }}
OUT = "{{ node_exporter_textfile_dir }}/aether_tailscale.prom"

status = json.loads(subprocess.run(
    ["tailscale", "status", "--json"], capture_output=True, text=True, check=True, timeout=30,
).stdout)

lines = [
    "# HELP aether_tailscale_peer_direct 1 when this host has a direct WireGuard path to the peer, 0 when it goes through a relay.",
    "# TYPE aether_tailscale_peer_direct gauge",
]
for peer in status.get("Peer", {}).values():
    name = peer.get("HostName", "")
    # An offline or idle peer has no path at all; the scrape alerts cover it.
    if name in PEERS and peer.get("Online") and peer.get("Active"):
        direct = 1 if peer.get("CurAddr") else 0
        lines.append('aether_tailscale_peer_direct{peer="%s"} %d' % (name, direct))
lines += [
    "# HELP aether_tailscale_paths_timestamp_seconds When the path check last ran.",
    "# TYPE aether_tailscale_paths_timestamp_seconds gauge",
    f"aether_tailscale_paths_timestamp_seconds {int(time.time())}",
]

fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".aether_tailscale.")
try:
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)
except BaseException:
    os.unlink(tmp)
    raise
