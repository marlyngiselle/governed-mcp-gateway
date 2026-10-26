---
title: Disk pressure on a Linux VM
service: compute
tags: [disk, linux, vm, alert]
---

# Disk pressure on a Linux VM

Alert: root filesystem above 90 percent for 10 minutes.

## Triage

1. Confirm the alert is still firing and note the mount point.
2. Find the largest directories: `sudo du -xh / --max-depth=2 | sort -h | tail -20`.
3. Check whether logs are rotating: `ls -lh /var/log` and `systemctl status logrotate.timer`.

## Mitigate

- Compress or remove rotated logs older than 7 days.
- If a batch job writes temporary files, stop the job before deleting them.
- Never delete files under `/var/lib` without the service owner.

## Escalate

Open a sev3 ticket for the owning service if usage does not drop below 80 percent within 30 minutes.
