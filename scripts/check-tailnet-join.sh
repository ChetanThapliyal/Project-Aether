#!/bin/bash
# Prove a machine could rejoin the tailnet, without rebuilding it (INC-2026-016).
# Starts an ephemeral, userspace Tailscale node in a container on this workstation,
# logs it in with the same stored secret and tag the real machine uses, reports the
# result, then logs out and removes the container. The node is ephemeral, but Tailscale
# can keep listing it offline for a while: delete it under Machines (join-check-*) if it lingers.
#
#   scripts/check-tailnet-join.sh dmz    # the edge VM's secret (02-gcp-dmz tfvars), tag:gcp-dmz
#   scripts/check-tailnet-join.sh k3s    # the cluster nodes' secret (Ansible), tag:k3s
#
# Needs docker and SOPS access. The secret is never printed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "${1:-}" in
  dmz) TAG="tag:gcp-dmz"
       SECRET=$(sops -d "$ROOT/infrastructure/terraform/02-gcp-dmz/terraform.sops.tfvars" \
         | sed -n 's/^[[:space:]]*tailscale_auth_key[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' | tail -1) ;;
  k3s) TAG="tag:k3s"
       SECRET=$(sops -d --extract '["tailscale_auth_key"]' "$ROOT/infrastructure/secrets/ansible-secrets.sops.yaml") ;;
  *)   echo "usage: $0 dmz|k3s" >&2; exit 2 ;;
esac
case "$SECRET" in *\?*) KEY="${SECRET}&ephemeral=true" ;; *) KEY="${SECRET}?ephemeral=true&preauthorized=true" ;; esac
unset SECRET
NAME="join-check-$1"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" tailscale/tailscale:v1.104.7 \
  tailscaled --tun=userspace-networking --state=mem: >/dev/null
trap 'docker exec "$NAME" tailscale logout >/dev/null 2>&1 || true; docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT
sleep 3
if OUT=$(docker exec "$NAME" tailscale up --authkey="$KEY" --advertise-tags="$TAG" \
           --hostname="$NAME" --timeout=40s 2>&1); then
  unset KEY
  echo "OK: the $1 secret joins with $TAG"
else
  unset KEY
  echo "FAIL: the $1 secret can't join with $TAG: $(echo "$OUT" | tail -1)"
  exit 1
fi
