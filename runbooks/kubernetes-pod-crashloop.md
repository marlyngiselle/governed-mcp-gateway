---
title: Pods in CrashLoopBackOff
service: platform
tags: [kubernetes, pods, crashloop, aks]
---

# Pods in CrashLoopBackOff

## Triage

1. `kubectl get pods -A --field-selector=status.phase!=Running`
2. `kubectl describe pod <pod> -n <namespace>` and read the last events.
3. `kubectl logs <pod> -n <namespace> --previous` for the crash output.

## Common causes

| Symptom | Likely cause | First action |
| --- | --- | --- |
| `OOMKilled` | Memory limit too low | Compare usage with limits, raise with the team |
| Exit code 1 at start | Bad config or missing secret | Check the last config change |
| Liveness probe failed | Slow start | Add a startup probe |

## Escalate

Open a sev2 ticket if a production namespace has more than one workload crashing.
