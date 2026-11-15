#!/usr/bin/env bash
# DR Scenario 02 drill (FND-23): restore one app from the restic backup and prove
# its database loads, without touching production.
#
#   task dr:drill:oci        (runs this on the OCI host as root over SSH)
#
# 1. restic check reading 5% of the pack data (read-only)
# 2. restore BookOrbit's files and OCI Uptime Kuma's data into a scratch dir
# 3. load BookOrbit's nightly dump into a throwaway Postgres (same image, no
#    network) and compare tables and row counts with the live database
#    (a read-only count; rows may differ by what changed since the snapshot)
# 4. integrity check of the restored Kuma database
# Everything is removed on exit. Never run near the 03:00 UTC backup.
set -euo pipefail

APP_DIR=/home/ubuntu/bookorbit
DUMP=$APP_DIR/db.sql
LIVE_DB=bookorbit-db DB_USER=bookorbit DB_NAME=bookorbit
KUMA_DB=/home/ubuntu/uptimekuma/data/kuma.db
WORK=/var/tmp/dr-drill
SCRATCH=dr-drill-pg

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
[ -e "$WORK" ] && { echo "$WORK already exists: another drill running, or a stale one to remove"; exit 1; }
# shellcheck disable=SC1091
source /opt/backup/restic.env

cleanup() { docker rm -f "$SCRATCH" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT

now() { date +%s; }
step() { printf '\n== %s\n' "$*"; }
COUNTS_SQL="SELECT table_schema || '.' || table_name, (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text FROM information_schema.tables WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY 1"

T0=$(now)
step "1. Repository check (reads 5% of the data)"
restic check --read-data-subset=5% --no-lock 2>&1 | tail -2
T1=$(now)

step "2. Restore from the latest snapshot"
SNAP=$(restic snapshots --latest 1 --json | python3 -c 'import json,sys; s=json.load(sys.stdin)[-1]; print(s["short_id"], s["time"][:16].replace("T", " "), "UTC")')
echo "snapshot: $SNAP"
restic restore latest --target "$WORK" --include "$APP_DIR" --include "$(dirname "$KUMA_DB")" 2>&1 | tail -1
T2=$(now)
SIZE=$(du -sh "$WORK$APP_DIR" | cut -f1)
[ -s "$WORK$DUMP" ] || { echo "FAIL: restored dump missing or empty"; exit 1; }

step "3. Load the dump into a throwaway database (no network)"
IMAGE=$(docker inspect -f '{{.Config.Image}}' "$LIVE_DB")
docker run -d --name "$SCRATCH" --network none -e POSTGRES_USER="$DB_USER" \
  -e POSTGRES_PASSWORD=drill -e POSTGRES_DB="$DB_NAME" "$IMAGE" >/dev/null
# The entrypoint starts Postgres twice (init, then for real): wait for the second.
for _ in $(seq 120); do
  [ "$(docker logs "$SCRATCH" 2>&1 | grep -c 'ready to accept connections')" -ge 2 ] && break
  sleep 1
done
docker exec "$SCRATCH" pg_isready -U "$DB_USER" -d "$DB_NAME" -q
T3=$(now)
docker exec -i "$SCRATCH" psql -q -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" >/dev/null < "$WORK$DUMP"
T4=$(now)
docker exec "$SCRATCH" psql -At -F '|' -U "$DB_USER" -d "$DB_NAME" -c "$COUNTS_SQL" | LC_ALL=C sort > "$WORK/restored.txt"
docker exec "$LIVE_DB" psql -At -F '|' -U "$DB_USER" -d "$DB_NAME" -c "$COUNTS_SQL" | LC_ALL=C sort > "$WORK/live.txt"
read -r TABLES ROWS_R < <(awk -F'|' '{n++; s+=$2} END {print n, s}' "$WORK/restored.txt")
read -r TABLES_L ROWS_L < <(awk -F'|' '{n++; s+=$2} END {print n, s}' "$WORK/live.txt")
echo "tables: restored $TABLES, live $TABLES_L · rows: restored $ROWS_R, live $ROWS_L"
if ! diff <(cut -d'|' -f1 "$WORK/restored.txt") <(cut -d'|' -f1 "$WORK/live.txt") >/dev/null; then
  echo "FAIL: restored and live table lists differ"; diff <(cut -d'|' -f1 "$WORK/restored.txt") <(cut -d'|' -f1 "$WORK/live.txt") || true; exit 1
fi
[ "$ROWS_R" -gt 0 ] || { echo "FAIL: restored database is empty"; exit 1; }
LC_ALL=C join -t'|' "$WORK/restored.txt" "$WORK/live.txt" | awk -F'|' '$2 != $3 {printf "  changed since the snapshot: %s %s -> %s\n", $1, $2, $3}'

step "4. Restored Kuma database integrity"
KUMA=$(python3 -c 'import sqlite3,sys; print(sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True).execute("PRAGMA integrity_check").fetchone()[0])' "$WORK$KUMA_DB")
echo "kuma.db: $KUMA"
[ "$KUMA" = ok ] || { echo "FAIL: Kuma database integrity"; exit 1; }
T5=$(now)

printf '\nDRILL OK %s · snapshot %s · check %ss · restore %s in %ss · database up %ss, dump loaded in %ss · %s tables, %s rows · Kuma ok · total %ss\n' \
  "$(date -u +%Y-%m-%d)" "$SNAP" $((T1 - T0)) "$SIZE" $((T2 - T1)) $((T3 - T2)) $((T4 - T3)) "$TABLES" "$ROWS_R" $((T5 - T0))
