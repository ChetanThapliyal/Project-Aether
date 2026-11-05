# INC-2026-007: The local backup copies were on the disk they were meant to protect against

| Field | Value |
|-------|-------|
| Date found | 2026-11-02 |
| Severity | SEV2 |
| Found by | Audit |
| Duration | From the start of the homelab DR pipeline to 2026-11-05 |
| Status | Fixed and verified; the old copy is deleted after the first unattended night |

## Summary

The K3s control plane's etcd snapshots follow a 3-2-1 plan: the live copy on the control VM, a snapshot mirror and an encrypted restic repo on the hypervisor's HDD, and an offsite copy in Backblaze B2. The mirror and the restic repo were never on the HDD. The jobs wrote to `/mnt/aether-pool/`, a plain directory on the hypervisor's SSD, which also holds every VM disk. The ZFS pool on the HDD was mounted somewhere else and held 1.48 MiB. Each DR path is now its own ZFS dataset on the HDD, mounted where the jobs already write, and the jobs refuse to run if a dataset isn't mounted.

## Impact

No data was lost and no restore was needed. The risk was in what one disk failure would take. If the SSD had failed, the VMs, the live etcd, the snapshot mirror and the local restic repo would all have gone together, leaving only the offsite B2 copy. The docs and the architecture decision record claimed two local media, so a restore plan built on them would have reached for copies that weren't there.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| Pipeline setup | The DR jobs create `/mnt/aether-pool/...` with `mkdir -p` and Ansible `file: state=directory`. Nothing checks what filesystem the path is on |
| 2026-11-02 | A re-audit runs `findmnt` on the DR path and gets `ext4` on the root volume. `zfs list` shows the HDD pool mounted at `/aether-pool`, nearly empty |
| 2026-11-05 15:01 | The three DR timers are stopped. Two ZFS datasets are created, the data is copied with `rsync -aHAX`, and the old directory is moved aside. `diff -rq` shows the copies are identical |
| 2026-11-05 | The ZFS cache cap is lowered to 512 MiB, since the hypervisor has about 1 GiB of memory free |
| 2026-11-05 15:15 | The playbooks are re-applied with mount guards. Each job runs once and succeeds. The local repo passes `restic check` |
| 2026-11-05 | Guard test: with the snapshot dataset unmounted, the sync job exits 1 and writes nothing to the SSD |

## Root cause

The DR paths were defined as directories, not as mounts. The pool was created with its default mountpoint, `/aether-pool`, while the jobs were written against `/mnt/aether-pool`. When the first job ran, `mkdir -p` and Ansible's directory task created the path on the root filesystem, and every job after that worked normally. From the job's point of view, a directory on the SSD and a dataset on the HDD look the same.

## Contributing factors

- The jobs checked that files arrived, never where they landed.
- Ansible's `file: state=directory` creates a missing mount point silently, so a wrong or missing mount can't make it fail.
- The design said "the ZFS HDD mirror pool". The pool is a single-disk vdev, and nobody checked the claim against `zpool status`.

## What went well

- The audit checked the filesystem under the path instead of trusting the path's name.
- The migration copied first and kept the old data in place until the new copies were verified, so no step was destructive.

## Where we got lucky

The SSD didn't fail. The offsite copy in B2 was healthy the whole time, so even the worst case had one copy left.

## Fix

Commit `785274a`, plus a one-time migration on the hypervisor.

- Two datasets, `aether-pool/k3s-etcd-snapshots` and `aether-pool/restic-k3s-etcd`, mounted at the original paths with `lz4`, `atime=off` and `copies=2`. On a single disk, `copies=2` repairs bad sectors; it doesn't survive losing the disk.
- Each of the three DR playbooks fails before touching the host unless both paths are mounted from their exact `aether-pool` datasets.
- Each deployed script runs the same check first, because a dataset can fail to mount after a reboot.
- The ZFS cache is capped at 512 MiB.

## Guardrails added

- The mount guards make "wrong disk" a failed job instead of a silent success. Once the planned backup heartbeats exist, a guard that trips also pages.
- The DR scenario for homelab hardware loss now checks that both datasets are mounted before restoring.
- Addenda to the storage and 3-2-1 decision records state the actual media and the single-disk limit.

## Lessons

- A path is not a disk. Any job that writes a backup should check the mount source of its target before it writes.
- Tools that create missing directories for you will also hide a missing mount.
