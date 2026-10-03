#!/bin/bash
# Pre/post k3s comparison collector for homelab (k3s installed 2026-09-17).
# Run as root. Produces a report at /root/k3s-compare-report.txt and a bundle
# at /root/k3s-compare-bundle.tar.gz containing the raw journal slices.
set -u
CUTOFF="2026-09-17 00:00:00"   # k3s install date
OUT=/root/k3s-compare-report.txt
RAW=/root/k3s-compare-raw
mkdir -p $RAW
exec > >(tee "$OUT") 2>&1

echo "===================================================================="
echo " k3s pre/post comparison - homelab"
echo " generated: $(date -Is)"
echo " k3s installed: 2026-09-17 (cutoff below)"
echo "===================================================================="

echo
echo "### 1. BOOT INVENTORY (chronological, oldest first)"
journalctl --list-boots --no-pager 2>/dev/null | tac | nl -ba

echo
echo "### 2. CLEAN vs ABRUPT shutdown classification per boot"
echo "(abrupt = log has no 'Reached target poweroff.target' / 'Journal stopped')"
printf "%-6s %-22s %-22s %-11s %-9s %s\n" "BOOT" "START" "END" "DURATION" "KIND" "PRE/POST k3s"
for b in $(journalctl --list-boots --no-pager 2>/dev/null | tac | awk '{print $1}'); do
  start=$(journalctl -b $b --no-pager 2>/dev/null | head -1 | cut -c1-15)
  endline=$(journalctl -b $b --no-pager 2>/dev/null | tail -1 | cut -c1-15)
  [ -z "$start" ] && continue
  dur=$(journalctl -b $b --no-pager -o short-unix 2>/dev/null | awk 'NR==1{f=$1} {l=$1} END{printf "%dm", (l-f)/60}')
  if journalctl -b $b --no-pager 2>/dev/null | grep -qE "Reached target (poweroff|reboot)\.target|Journal stopped"; then
    kind="clean"
  else
    kind="ABRUPT"
  fi
  if [[ "$start" < "${CUTOFF:0:10}" ]]; then pre="PRE"; else pre="POST"; fi
  printf "%-6s %-22s %-22s %-11s %-9s %s\n" "$b" "$start" "$endline" "$dur" "$kind" "$pre"
  # save the tail for eyeballing
  journalctl -b $b --no-pager 2>/dev/null | tail -25 > $RAW/boot_${b}_tail.txt
done

echo
echo "### 3. Abrupt-shutdown detail: last 12 lines of every ABRUPT boot"
for b in $(journalctl --list-boots --no-pager 2>/dev/null | tac | awk '{print $1}'); do
  if ! journalctl -b $b --no-pager 2>/dev/null | grep -qE "Reached target (poweroff|reboot)\.target|Journal stopped"; then
    echo "--- boot $b last 12 lines ---"
    journalctl -b $b --no-pager 2>/dev/null | tail -12
    echo
  fi
done

echo
echo "### 4. CPU TEMPERATURE per boot (coretemp package_id_0)"
echo "idle  = min of boot, loaded = max of boot, samples = count"
printf "%-6s %-22s %-9s %-9s %-9s %s\n" "BOOT" "START" "IDLE_C" "MAX_C" "SAMPLES" "PRE/POST"
for b in $(journalctl --list-boots --no-pager 2>/dev/null | tac | awk '{print $1}'); do
  stats=$(journalctl -b $b --no-pager -o short-unix 2>/dev/null \
    | grep -oE "Package id 0: *\+[0-9]+" | grep -oE "[0-9]+")
  [ -z "$stats" ] && continue
  start=$(journalctl -b $b --no-pager 2>/dev/null | head -1 | cut -c1-16)
  mn=$(echo "$stats" | sort -n | head -1)
  mx=$(echo "$stats" | sort -n | tail -1)
  n=$(echo "$stats" | wc -l)
  if [[ "$start" < "${CUTOFF:0:10}" ]]; then pre="PRE"; else pre="POST"; fi
  printf "%-6s %-22s %-9s %-9s %-9s %s\n" "$b" "$start" "$mn" "$mx" "$n" "$pre"
done

echo
echo "### 5. k3s / VM timeline (from Proxmox task log)"
grep -iE "qmstart|qmstop|qmcreate|vzstart|vzstop" /var/log/pve/tasks/index 2>/dev/null \
  | awk '{print $6, $7, $8, $NF}' | tail -40

echo
echo "### 6. Full wtmp / last -x  (shutdown records = graceful poweroffs)"
last -x 2>/dev/null | head -60

echo
echo "### 7. Per-boot error fingerprint (new errors post-k3s?)"
for b in $(journalctl --list-boots --no-pager 2>/dev/null | tac | awk '{print $1}'); do
  start=$(journalctl -b $b --no-pager 2>/dev/null | head -1 | cut -c1-16)
  [ -z "$start" ] && continue
  if [[ "$start" < "${CUTOFF:0:10}" ]]; then pre="PRE"; else pre="POST"; fi
  n=$(journalctl -b $b -p err --no-pager 2>/dev/null | wc -l)
  printf "boot %-4s %-5s err_lines=%-6s " "$b" "$pre" "$n"
  journalctl -b $b -p err --no-pager 2>/dev/null | sed -E 's/^[A-Z][a-z]{2} [0-9]+ [0-9:]+ [^ ]+ //' \
    | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -3 | tr '\n' '|'
  echo
done

echo
echo "### 8. Fan / thermal / power kernel messages across ALL boots"
journalctl -k --no-pager 2>/dev/null | grep -iE "hp-wmi|hp_wmi|fan|thermal|temperature|throttl|mce|hardware error|watchdog|power" \
  | sed -E 's/^[A-Z][a-z]{2} +[0-9]+ [0-9:]+ //' | sort | uniq -c | sort -rn | head -30

echo
echo "### 9. MCE / hardware error check (would indicate board fault)"
journalctl -k --no-pager 2>/dev/null | grep -icE "hardware error|mce:|machine check|edac" | sed 's/^/mce_lines=/'
journalctl --no-pager 2>/dev/null | grep -icE "hardware error|mce:|machine check" | sed 's/^/total_mce_lines=/'

echo
echo "### 10. Disk health (power-loss / spin-down correlation)"
command -v smartctl >/dev/null && for d in /dev/sda /dev/sdb; do
  [ -b "$d" ] || continue
  echo "--- $d ---"
  smartctl -A "$d" 2>/dev/null | grep -iE "Power_On|Start_Stop|Unexpected|194|Temperature_Cel" | head
done

echo
echo "### 11. sar / sysstat history if available (load + temp over time)"
if [ -d /var/log/sysstat ]; then
  sar -q 2>/dev/null | tail -20
  sar -m TEMP 2>/dev/null | tail -20
else
  echo "no /var/log/sysstat - load history unavailable"
  echo "current: $(uptime)"
fi

echo
echo "### 12. UPS / AC monitoring present?"
command -v upsc >/dev/null && echo "NUT/upsc present" || echo "no NUT (no UPS telemetry -> cannot confirm AC-side loss)"
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "no serial/USB power meters attached"

echo
echo "### 13. BATTERY + AC ADAPTER STATE  (key: is there any power buffering?)"
echo "--- power supplies ---"
for p in /sys/class/power_supply/*; do
  n=$(basename $p)
  echo "[$n] type=$(cat $p/type 2>/dev/null)  online=$(cat $p/online 2>/dev/null)  status=$(cat $p/status 2>/dev/null)"
  [ -f $p/capacity ] && echo "     capacity=$(cat $p/capacity)%  energy_now=$(cat $p/energy_now 2>/dev/null)  energy_full=$(cat $p/energy_full 2>/dev/null)  power_now=$(cat $p/power_now 2>/dev/null)"
  [ -f $p/charge_now ] && echo "     charge_now=$(cat $p/charge_now)  charge_full=$(cat $p/charge_full)  charge_control=$(cat $p/charge_control 2>/dev/null)"
done
echo "--- battery present at all? ---"
ls -d /sys/class/power_supply/BAT* 2>/dev/null || echo "NO BATTERY -> machine runs directly off the AC brick, zero ride-through"
echo "--- acpi battery detail ---"
for b in /proc/acpi/battery/BAT*; do
  [ -e "$b" ] || continue
  echo "[$b]"; grep -E "state|present|percentage|capacity|status" "$b" 2>/dev/null | head
done
echo "--- kernel battery/AC messages ---"
journalctl -k --no-pager 2>/dev/null | grep -iE "battery|ACPI: AC Adapter|power supply|charger|ACAD|axp|ADP" | head -20
echo "--- estimated brick wattage from DSDT/ACPI ---"
grep -oE "[0-9]+ ?W" /proc/acpi/acpi_video/info 2>/dev/null | head -3
grep -riE "adapter|ACAD" /sys/class/power_supply/ACAD/ 2>/dev/null | head -5
cat /sys/class/power_supply/ACAD/uevent 2>/dev/null


echo
echo "===================================================================="
echo " raw journal tails saved in $RAW"
tar czf /root/k3s-compare-bundle.tar.gz -C / $RAW 2>/dev/null
echo " bundle: /root/k3s-compare-bundle.tar.gz"
echo " report: $OUT"
echo "===================================================================="
