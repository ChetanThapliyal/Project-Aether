# Homelab server: sudden shutdown and fan noise

| Field | Value |
|---|---|
| Host | `homelab` (Proxmox VE `9.2.20`, kernel `7.0.14-17-pve`) |
| Hardware | HP Notebook, board `80C1`, version `96.31` |
| BIOS | Insyde `F.11`, dated `2015-07-23` |
| CPU | i3-5005U (Broadwell-U, 15 W, 2C/4T) |
| Memory | 12 GB |
| Storage | 250 GB SSD + 500 GB HDD |
| Physical setup | Display removed, no lid, chassis sits in a Thermaltake case, ambient about 20 °C |
| Workloads | k3s cluster, three nodes (VMs 101, 102, 103) |

## Current state

Both faults are understood well enough to act on. The fan has no working OS-level control path and
never had one, which is a firmware limitation rather than a fault. The noise turned out to be
mechanical, and cleaning and re-seating the fan fixed the behaviour. The shutdown is a hard power
loss, and the machine has been doing it for at least eleven months. Nothing is overheating.

## The two faults

1. Sudden shutdown: the machine powers off with no shutdown sequence recorded.
2. Fan noise: loud from boot, loud under load, and (before cleaning) loud at idle too.

## What the firmware exposes, and what it does not

Every boot logs this from the kernel:

```
hp-wmi hp-wmi: Failed to apply initial fan settings: -22
```

`-22` is `EINVAL`. HP's `hp-wmi` driver cannot hand the embedded controller a fan curve. Reloading
the module reproduces the error exactly, so it is a persistent firmware and driver mismatch rather
than a one-off glitch. `sensors` agrees: `hp-isa-0000` reports `pwm1: N/A`.

The underlying cause is in the ACPI tables. The SSDTs reference an HP embedded controller device at
`\_SB.PCI0.LPCB.H_EC`, with fields such as `CPUP`, `PCAP`, `PECC`, `PRFC`, `TER1` through `TER3`, and
methods `ECMD` and `ECWT`. No ACPI table ever defines that device. It is declared `External`, so
every AML method that dereferences it fails to resolve. Since all OS fan control on an HP notebook
routes through `H_EC`, the OS has no path to the fan at all. This is the same class of defect as the
`_TZ.TZ00._TMP` and `_TZ.TZ01._TMP` `AE_NOT_FOUND` aborts.

The ACPI EC that is present (`\_SB.PCI0.LPCB.EC0` on standard ports `0x62`/`0x66`) is readable, but it
exposes only generic helpers: `FANG(n)` and `FANW(n,v)` for raw byte access, and the `ERIB`/`ERBD`
extended-register indirection at `0x5D` through `0x5F`. It holds no fan curve and no fan command
register.

## Control paths I tried

| # | Path | Result |
|---|---|---|
| 1 | `hp_wmi` module reload | Same `-22` at boot and on reload. |
| 2 | `/sys/firmware/acpi/platform_profile` | Does not exist. This firmware predates ACPI platform profiles. |
| 3 | `hp_bioscfg` BIOS attributes | Only `Sure_Start` is exposed. No fan or thermal toggle is reachable from the OS on a 2015 BIOS. |
| 4 | nbfc config for this board | None exists. I checked all 313 configs in `nbfc-linux/configs`; no `80C1` match and no prior art in the nbfc issue tracker. |
| 5 | nbfc `ReadRegister/WriteRegister = 0x2E/0x2F`, the pair used by every Broadwell-era HP ProBook, EliteBook and ZBook config | `0x2F` silently discards writes. Readback stays `0x00`. |
| 6 | EC `0x58`, used by nbfc configs for `HP Omen 15 dc-00xxxx`, `HP Pavilion Gaming 15-ec1xxx` and `HP Pavilion 17-ab240nd` | Writable and holds a meaningful `103`, but proven not to be the fan register. See the load test below. |
| 7 | Extended EC space via `ERIB`/`ERBD`, indices `0x0000` through `0x07FF` | No live registers and no plausible fan or RPM values. Effectively unimplemented here. |
| 8 | HP EC shared-memory window at physical `0xFF000000` (the `ECMP` map with `FRPM`, `FNMX`, `FNMN`, `FWPM` at `+0x811` through `+0x814`) | `/dev/mem` is readable, but the window returns an unrelated repeating `1C D4 1E FA` pattern, so it is not the EC block on this platform. |
| 9 | DPTF fan cooling devices (`cooling_device3` through `7`, backed by `PNP0C0B:00` through `04`) | Registered, but the AML shows they are power resources whose `_ON` and `_OFF` call the undefined `H_EC.ECMD(0x1A)`. Writing `cur_state=0` versus `1` moved CPU temperature by 1 °C, which is noise. One device rejected the write outright. |

The load test for `0x58` deserves a note, because it is the measurement that closed off the last
plausible register. With no tachometer anywhere on the board, "did the fan change" had to be answered
thermally. Identical single-core-pinned load, register forced to each extreme, watchdog armed to
restore maximum at 82 °C:

```
PHASE 1  0x58 = 103 (BIOS max) + load -> plateau 64 °C
PHASE 2  0x58 =   0 (min/off)  + load -> plateau 64 °C
delta = 0 °C
```

A register that genuinely commanded the fan could not produce a zero delta under sustained load, so
`0x58` is an unrelated writable config or telemetry byte.

## The fan after cleaning and re-seating

On 2026-09-27 I cleaned the fan and reconnected it. The behaviour changed immediately, and it now
matches a working fan curve: loud during startup, then it slows down at idle. Before the clean it
stayed loud regardless of load.

That rules out a control fault as the cause of the noise, and points at the mechanism instead. The fan
is 12 years old. Cleaning restores airflow but cannot restore bearing play, so a bearing that has
worn out will still rumble once the airflow around it is good. The fan is responding correctly to
temperature; it was the sound that was wrong.

No RPM readout exists on this machine (`pwm1: N/A`, and no `fan1_input` on any hwmon device).
Replacing the fan will not change that, because the missing `H_EC` binding is a firmware defect
rather than a property of the fan. There will be no software confirmation after the swap, so the
result has to be judged by ear.

## Temperatures

| State | Load | CPU package | EC sensor `B0D4` | `acpitz` |
|---|---|---|---|---|
| Idle baseline | 0.62 to 0.73 | 50 to 53 °C | 50 °C | 27.8 °C |
| Two threads pinned | rising 0.51 to 1.82 | 55 to 58 °C | 56 to 59 °C | 27.8 °C |
| After load removed | ~1.8 and falling | 58 down to 54 °C | 59 down to 55 °C | 27.8 °C |
| Earlier single-core pin test | sustained | 63 to 64 °C | not sampled | not sampled |
| Normal k3s working load | ~1.2 | 54 to 57 °C | not sampled | not sampled |

58 °C under a pinned two-thread load on a 15 W part is unremarkable, and the critical threshold is
105 °C. There is no thermal problem here, which is consistent with the fan never having been a
cooling emergency.

One sensor correction: `acpitz` (`thermal_zone0`) sat at exactly 27.8 °C through the entire ramp and
did not move by a tenth of a degree while the package climbed nine degrees. It is either dead or
pointing at a location that does not change. Ignore it. `B0D4` (`thermal_zone4`) is the EC CPU
sensor that matters; it tracked the package faithfully from 50 °C to 59 °C. `thermal_zone3`
(`x86_pkg_temp`) agrees with `coretemp`.

## The shutdown is a hard power loss, and it is not new

The signature is a log that simply stops. No `systemd-shutdown`, no `Reached target
poweroff.target`, no `Syncing filesystems`, no kernel messages. Clean shutdowns *are* recorded on this
machine when they happen, so the absence means something.

The part I got wrong originally was assuming this was recent. It is not. The journal reaches back to
November 2025, and boots from July, August and early September all end the same way: truncated
between ordinary ten-second `pvestatd` log lines, with zero shutdown markers.

```
boot -20   Sep 01 19:44 -> Sep 03 10:37 (46 h)   ends mid-stream, 0 shutdown markers
boot -11   Sep 11 16:35 -> Sep 11 18:25           ends mid-stream, 0 shutdown markers
boot -30   Aug 25 10:12 -> Aug 25 14:45           ends mid-stream, 0 shutdown markers
boot -50   Jul 18 12:51 -> Jul 18 12:52           clean poweroff, 2 shutdown markers
```

Those boots have thousands of journal lines each, so this is not an artifact of log rotation. Boot
`-50` is a genuine clean poweroff of the same system on the same firmware, and it records two
shutdown markers, which confirms the check works.

k3s did not cause this. It was installed on 2026-09-17, inside boot `-3`. The machine then sat
powered off for seven days (2026-09-18 19:47 to 2026-09-26 07:21) before coming back. Both recent
abrupt events happened on 2026-09-26, immediately after that gap. What k3s changed is the duty cycle,
which is why the fault started costing running VMs rather than an idle host.

I ruled out the Proxmox watchdog. `pve-guests.service` (PVE 9's renamed watchdog, note it is not
`pve-guest.service`) is enabled and active, and the three VMs were running. A watchdog trip panics and
reboots, which would be logged, and there is no such record.

## Why a brick failure would look exactly like this

The kernel says it outright:

```
ACPI: AC: AC Adapter [ACAD] (on-line)
ACPI: battery: Slot [BAT1] (battery absent)
```

There is no battery. The only power supply the kernel sees is `ACAD`, of type Mains. A laptop running
this way has nothing between the wall and the CPU, so when the adapter dips there is no ride-through
and the machine dies instantly with nothing written to disk. That is exactly the signature in the
logs.

An adapter that coped with an idle host may not hold up under sustained VM load. That makes power
delivery the leading suspect, and it also means the fault has been present and harmless for most of
the machine's life as a homelab, only becoming visible once there was unsaved work to lose.

The log signature cannot separate the brick from the DC connector from the board, because all three
produce the same truncation. AC-side monitoring is the only way to narrow it.

## Log noise that does not matter

- DMAR/IOMMU DMA faults on device `00:16.7`
- TPM CRB probe timeout and failure
- `postfix` failing to open `/etc/aliases.db` (local MTA misconfiguration)
- NFS `blkmapd` pipe warning
- `pvestatd` complaining that `/mnt/pve/media-storage` is not a mount point
- ACPI BIOS bugs `_TZ.TZ00._TMP` and `_TZ.TZ01._TMP` aborting with `AE_NOT_FOUND`

## Plan

The fan is 12 years old and worn, and the user is replacing it. Doing the thermal paste in the same
teardown makes sense, since original TIM on a machine this age is often pumped out or crusty, and it
may account for part of any temperature rise.

Shut the three VMs down cleanly before starting the teardown. There is no battery and the power
supply is known to be unreliable, and an accidental loss during the work would kill them the same
ungraceful way. While the machine is open, also blow out the heatsink fins and check the fan duct,
because if the replacement fan is *also* loud then the suspect moves to clogged fins or a blocked
duct. Reseat the connector properly at the same time.

The BIOS remains the only fix for the missing `H_EC` binding, and it would fix `hp-wmi` fan control
along with the `TZ00`/`TZ01` aborts. Board ID `080C1` selects the image, and HP shipped refreshes for
2015 notebook platforms as late as 2023. This should not be attempted remotely: a failed flash on a
headless box with no display is a brick, and there is no IPMI. Schedule it for physical access with a
USB recovery stick ready.

For the power fault, in priority order: fit a UPS or at minimum a logged AC-side meter, which is the
only way to tell "wall lost power" from "machine dropped power"; try a different brick and outlet;
reseat the DC connector; and capture `journalctl -b -1 -e` immediately after any recurrence, before
the next boot overwrites useful context.

There is a cheaper mitigation available now. A short journald unit watching the `ACAD` ACPI event
could bring the VMs down cleanly on AC loss, which would limit the damage from a fault that is already
confirmed. Worth considering while the replacement fan ships.

## Machine state left behind

`ec_sys` is unloaded, as it was at boot. `nbfc_service` is `disabled` and `inactive` with no config,
and no EC register is left modified. EC backups, scan CSVs and probe scripts are retained in
`/root/fanprobe/` on the host.

`nbfc-linux` 0.5.3 and `acpica-tools` are installed but inert. `nbfc` cannot help without a fan
register that this firmware does not expose. The `acpi-call` DKMS source was added as a dependency of
`nbfc-linux` and never built, because matching kernel headers are not available.
