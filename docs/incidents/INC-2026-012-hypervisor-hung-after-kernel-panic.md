# INC-2026-012: The hypervisor panicked overnight and stayed frozen for nine hours

| Field | Value |
|-------|-------|
| Date found | 2026-11-11 |
| Severity | SEV3 |
| Found by | Alert (fired at night), then the operator in the morning |
| Duration | 2026-11-10 21:09 to 2026-11-11 06:01 UTC (about 9 hours, the whole homelab) |
| Status | Fixed and verified (the host now reboots itself after a panic). Hardware cause not yet confirmed |

## Summary

The hypervisor, a 2015 laptop that runs all three cluster VMs, hit a kernel panic at 02:39 local time. Nothing tells the kernel to reboot after a panic by default, so it stopped with a blank screen and no network until someone held the power button nine hours later. The VMs, the cluster and every service on it were down for that time.

The kernel saved its last messages to firmware storage. They show a general protection fault in the CPU idle loop, which points to the hardware rather than to anything that changed recently. The host now reboots 10 seconds after any panic, oops or hard lockup.

## Impact

No data was lost. The cluster, its VMs and the hypervisor's own services were unreachable for about 9 hours. Nothing on the cluster serves users yet, so the cost was lost monitoring and nine hours without a recovery point.

The nightly DR chain lost two of its three stages for the night. The snapshot pull had finished nine minutes before the crash. The encrypted local copy and the offsite upload ran when the host came back, about eight hours late, and both succeeded.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| 2026-11-09 11:04 | The hypervisor boots. Its kernel has been installed since September. The print service starts a restart loop every 90 seconds that lasts for the whole boot |
| 2026-11-10 21:00 | The nightly snapshot pull succeeds |
| 2026-11-10 21:09:43 | A general protection fault on one CPU in the idle loop. The kernel panics 0.4 seconds later and stops. The VMs' logs end mid-stream with nothing unusual before them |
| 2026-11-10 21:12 to 21:13 | Five alerts fire: the hypervisor, all three nodes and kube-state-metrics are down |
| 2026-11-10 21:30, 22:00 | The local encrypted copy and the offsite upload don't run |
| 2026-11-11 ~05:20 | The operator can't SSH in, and the tailnet shows every homelab node offline. From outside: no ARP reply on the LAN, and metrics and logs stop abruptly. The machine is powered but shows no video |
| 2026-11-11 06:01 | Hard reset. The host boots and the VMs start on their own |
| 2026-11-11 06:03 to 06:05 | The missed DR stages catch up and succeed, and the alerts resolve |
| 2026-11-11 | The crash record is read from firmware storage. The host is set to reboot after a panic |

## Root cause

Two separate things went wrong.

First, the crash. The CPU took a general protection fault inside the kernel's idle loop (`tick_nohz_next_event`). A register held a garbage value right after the code had loaded a fixed constant into it. The idle task can't be killed, so the kernel panicked. A fault like that in idle code, with nothing running, usually comes from the hardware: a memory bit flip, or a CPU coming back from a deep sleep state in a bad state. A kernel bug is possible but less likely. The kernel had run for two months without a fault, and the last package change was nine hours before the crash. One crash isn't enough to prove which it was.

Second, the nine hours. Proxmox ships with `kernel.panic = 0`, which means "after a panic, wait forever". The host has no remote power control or management controller, so nothing short of a person at the machine could bring it back.

## Contributing factors

- All three cluster nodes are VMs on one physical host, so one hypervisor crash takes down the whole cluster.
- The crash happened at 02:39 local time. The alerts fired within four minutes, but nobody was awake to act on them.
- A print service the hypervisor doesn't need was crash-looping every 90 seconds and writing AppArmor denials to the kernel log. Most of the saved crash record was this noise. The fault trace survived, but a noisier loop could have pushed it out.

## What went well

- The kernel's crash record in firmware storage (pstore) survived the hard reset. Without it, this review would have nothing but "the screen was black".
- The DR timers are `Persistent=true`, so the stages the crash skipped ran on their own at boot and succeeded.
- The VMs kept their SSH host keys across the unclean restart. The fix from [INC-2026-010](INC-2026-010-host-keys-regenerated-on-reboot.md) held, so the DR chain didn't break the way it did then.
- The alerts fired within four minutes and matched what had happened.

## Where we got lucky

The crash came nine minutes after the nightly snapshot pull had finished, not partway through it. The storage pool and both disks came through the hard power-off clean.

## Fix

- New playbook `infrastructure/ansible/playbooks/proxmox-base.yml` (`task ansible:proxmox:base`) sets `kernel.panic = 10`, `kernel.panic_on_oops = 1` and `kernel.hardlockup_panic = 1`. A panic, an oops or a hard lockup caught by the NMI watchdog now reboots the host after 10 seconds, and the VMs start on their own. `softlockup_panic` is left off, because a busy host could trip it falsely.
- The same playbook stops and masks the print service and the IPMI service. This hardware has no IPMI controller, so that service failed on every boot.

## Guardrails added

- The playbook reads the live sysctls back and fails unless all three hold.
- Follow-up: run memtest86+ overnight. Errors would confirm the memory as the cause.
- Follow-up: if another panic lands in the idle path, limit the CPU's sleep states (`intel_idle.max_cstate=1`), a known workaround for this CPU generation.
- Follow-up: hardware that has out-of-band management, or a second hypervisor, would remove the need for someone to be at the machine.

## Lessons

- Check what a host does after a panic before you rely on it. Proxmox's default is to wait for a human.
- Keep the kernel log quiet on hosts you run. Crash records are small, and log noise competes with the trace for space.
- `Persistent=true` on backup timers turned a missed night into a late one.
