#!/usr/bin/env bash
# Phase 04 task 4.15 drill (ADR-022): restore every app database from last night's
# dump and prove it loads, without touching production.
#
#   task dr:drill:k8s        (runs from a workstation with kubectl access)
#
# 1. find the newest dump night on the db-dumps volume (NFS)
# 2. start a throwaway PostgreSQL (same image, own empty storage, no network: the
#    namespace's default-deny admits nothing to it) with the dumps mounted read-only
# 3. load each dump into its own database there and compare tables and row counts
#    with the counts the dump Job recorded, then with live (read-only count; live
#    may have moved on since the dump)
# The pod is removed on exit. Avoid 01:30-02:00 IST, when the dump Job runs.
set -euo pipefail
NS=databases
POD=dr-drill-pg
IMAGE=$(kubectl -n "$NS" get sts postgres -o jsonpath='{.spec.template.spec.containers[0].image}')
COUNTS_SQL="SELECT table_schema || '.' || table_name || '|' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1"
WORK=$(mktemp -d)
cleanup() { kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true; rm -f "$WORK"/*; rmdir "$WORK"; }
trap cleanup EXIT
now() { date +%s; }
step() { printf '\n== %s\n' "$*"; }
kubectl -n "$NS" get pod "$POD" >/dev/null 2>&1 && { echo "$POD already exists: another drill running, or a stale one to delete"; exit 1; }

T0=$(now)
step "1-2. Throwaway PostgreSQL with the dumps mounted read-only"
kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  namespace: $NS
  labels: { app.kubernetes.io/name: dr-drill }
spec:
  restartPolicy: Never
  activeDeadlineSeconds: 1800
  securityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile: { type: RuntimeDefault }
  containers:
    - name: pg
      image: $IMAGE
      env:
        - { name: POSTGRES_PASSWORD, value: drill }
        - { name: PGDATA, value: /var/lib/postgresql/data/pgdata }
      resources:
        requests: { cpu: 50m, memory: 128Mi }
        limits: { cpu: "1", memory: 512Mi }
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities: { drop: [ALL] }
      volumeMounts:
        - { name: data, mountPath: /var/lib/postgresql/data }
        - { name: run, mountPath: /var/run/postgresql }
        - { name: tmp, mountPath: /tmp }
        - { name: dumps, mountPath: /dumps, readOnly: true }
  volumes:
    - { name: data, emptyDir: { sizeLimit: 2Gi } }
    - { name: run, emptyDir: {} }
    - { name: tmp, emptyDir: {} }
    - name: dumps
      persistentVolumeClaim: { claimName: db-dumps, readOnly: true }
EOF
kubectl -n "$NS" wait --for=condition=Ready "pod/$POD" --timeout=180s >/dev/null
# The entrypoint starts PostgreSQL twice (init, then for real): wait for the second.
for _ in $(seq 120); do
  [ "$(kubectl -n "$NS" logs "$POD" 2>/dev/null | grep -c 'ready to accept connections')" -ge 2 ] && break
  sleep 1
done
pgx() { kubectl -n "$NS" exec "$POD" -- "$@"; }
NIGHT=$(pgx sh -c 'ls -1d /dumps/20??-??-?? | sort | tail -1')
[ -n "$NIGHT" ] || { echo "FAIL: no dump night on the volume"; exit 1; }
echo "dump night: $(basename "$NIGHT") · marker: $(pgx cat /dumps/LAST_SUCCESS)"
T1=$(now)

step "3. Load each dump and compare"
TOTAL_T=0 TOTAL_R=0 N=0
for dump in $(pgx sh -c "ls -1 $NIGHT/*.dump"); do
  db=$(basename "$dump" .dump)
  pgx createdb -U postgres "$db"
  pgx pg_restore -U postgres -d "$db" --no-owner --no-privileges --exit-on-error "$dump"
  pgx psql -U postgres -At -d "$db" -c "$COUNTS_SQL" | LC_ALL=C sort > "$WORK/$db.restored"
  pgx sh -c "cat $NIGHT/$db.counts" | LC_ALL=C sort > "$WORK/$db.atdump"
  kubectl -n "$NS" exec postgres-0 -- psql -U postgres -At -d "$db" -c "$COUNTS_SQL" | LC_ALL=C sort > "$WORK/$db.live"
  read -r T R < <(awk -F'|' '{n++; s+=$2} END {print n+0, s+0}' "$WORK/$db.restored")
  printf '%-12s %3s tables %7s rows' "$db" "$T" "$R"
  if ! diff -q "$WORK/$db.restored" "$WORK/$db.atdump" >/dev/null; then
    echo "  FAIL: differs from the counts taken at dump time"; diff "$WORK/$db.restored" "$WORK/$db.atdump" || true; exit 1
  fi
  if ! diff -q <(cut -d'|' -f1 "$WORK/$db.restored") <(cut -d'|' -f1 "$WORK/$db.live") >/dev/null; then
    echo "  FAIL: table list differs from live"; exit 1
  fi
  echo "  = at dump time; tables = live"
  LC_ALL=C join -t'|' "$WORK/$db.restored" "$WORK/$db.live" | awk -F'|' '$2 != $3 {printf "    changed since the dump: %s %s -> %s\n", $1, $2, $3}'
  TOTAL_T=$((TOTAL_T + T)) TOTAL_R=$((TOTAL_R + R)) N=$((N + 1))
done
[ "$N" -gt 0 ] || { echo "FAIL: no dumps in $NIGHT"; exit 1; }
T2=$(now)
printf '\nDRILL OK %s · dump night %s · %s databases, %s tables, %s rows · database up %ss · restore and compare %ss · total %ss\n' \
  "$(date -u +%Y-%m-%d)" "$(basename "$NIGHT")" "$N" "$TOTAL_T" "$TOTAL_R" $((T1 - T0)) $((T2 - T1)) $((T2 - T0))
