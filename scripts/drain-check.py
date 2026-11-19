#!/usr/bin/env python3
"""Before draining a node: what moves, where it fits, and what stays down.

Read-only. Uses kubectl's current context. For each pod on the node (DaemonSet
pods and finished pods aside) it reports one of:

  fits <node>      the scheduler has room for its memory and CPU requests there
  preempts <pods>  no room, but its priority class evicts lower-priority pods there
  PENDING          no room and nothing it may preempt: down until the node is back
  PINNED           its volume is local-path on this node: down until the node is back

It places pods highest priority first, as the scheduler will when they are all
Pending at once, and only counts requests (as the scheduler does), not real usage.
It is an estimate: it ignores CPU-only shortfalls being preempted and pod
affinity. Runbook: docs/runbooks/node-maintenance.md (5.38).

  scripts/drain-check.py k3s-worker-01
"""
import json
import subprocess
import sys

UNITS = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40,
         "k": 10**3, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12, "m": 1e-3}


def qty(s):
    if not s:
        return 0.0
    for u in sorted(UNITS, key=len, reverse=True):
        if s.endswith(u):
            return float(s[: -len(u)]) * UNITS[u]
    return float(s)


def kget(*args):
    out = subprocess.run(["kubectl", "get", *args, "-o", "json"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)["items"]


def requests(pod):
    """Effective requests: containers summed, or the largest init container if bigger."""
    def one(c, k):
        return qty(c.get("resources", {}).get("requests", {}).get(k))
    spec = pod["spec"]
    res = {}
    for k in ("memory", "cpu"):
        main = sum(one(c, k) for c in spec["containers"])
        init = max([one(c, k) for c in spec.get("initContainers", [])] or [0])
        res[k] = max(main, init)
    return res


def owner_kind(pod):
    refs = pod["metadata"].get("ownerReferences") or [{}]
    return refs[0].get("kind", "")


def mib(b):
    return f"{b / 2**20:.0f}Mi"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    node = sys.argv[1]

    nodes = {n["metadata"]["name"]: n for n in kget("nodes")}
    if node not in nodes:
        sys.exit(f"no node {node}")
    prio_policy = {p["metadata"]["name"]: p.get("preemptionPolicy", "PreemptLowerPriority")
                   for p in kget("priorityclasses")}
    pv_node = {}
    for pv in kget("pv"):
        if pv["spec"].get("storageClassName") != "local-path":
            continue
        terms = pv["spec"].get("nodeAffinity", {}).get("required", {}).get("nodeSelectorTerms", [])
        claim = pv["spec"].get("claimRef", {})
        if terms and claim:
            pv_node[(claim["namespace"], claim["name"])] = terms[0]["matchExpressions"][0]["values"][0]

    pods = [p for p in kget("pods", "-A")
            if p["status"].get("phase") not in ("Succeeded", "Failed") and p["spec"].get("nodeName")]

    def schedulable(n):
        spec = nodes[n]["spec"]
        hard = [t for t in spec.get("taints", []) if t["effect"] in ("NoSchedule", "NoExecute")]
        return not spec.get("unschedulable") and not hard

    targets = [n for n in nodes if n != node and schedulable(n)]
    free, victims = {}, {}
    for n in targets:
        alloc = nodes[n]["status"]["allocatable"]
        free[n] = {"memory": qty(alloc["memory"]), "cpu": qty(alloc["cpu"])}
        victims[n] = []
    for p in pods:
        n = p["spec"]["nodeName"]
        if n in free:
            r = requests(p)
            for k in free[n]:
                free[n][k] -= r[k]
            if owner_kind(p) != "DaemonSet":
                victims[n].append((p.get("spec", {}).get("priority", 0), p, r))

    moving = [p for p in pods if p["spec"]["nodeName"] == node and owner_kind(p) != "DaemonSet"]
    moving.sort(key=lambda p: -p["spec"].get("priority", 0))

    print(f"Draining {node}. Free requests elsewhere before the drain:")
    for n in targets:
        print(f"  {n}: {mib(free[n]['memory'])} memory, {free[n]['cpu']:.2f} CPU")
    if not targets:
        print("  (no other schedulable node)")
    print()
    rows, down = [], 0
    for p in moving:
        md = p["metadata"]
        name = f"{md['namespace']}/{md['name']}"
        r = requests(p)
        prio = p["spec"].get("priority", 0)
        pclass = p["spec"].get("priorityClassName", "-")
        claims = [v["persistentVolumeClaim"]["claimName"] for v in p["spec"].get("volumes", [])
                  if "persistentVolumeClaim" in v]
        if any(pv_node.get((md["namespace"], c)) == node for c in claims):
            rows.append((name, pclass, r, "PINNED (local-path volume on this node)"))
            down += 1
            continue
        verdict = None
        for n in targets:
            if all(free[n][k] >= r[k] for k in r):
                for k in r:
                    free[n][k] -= r[k]
                verdict = f"fits {n}"
                break
        if verdict is None and prio_policy.get(pclass, "PreemptLowerPriority") != "Never":
            for n in targets:
                lower = sorted([v for v in victims[n] if v[0] < prio], key=lambda v: v[0])
                gain, chosen = dict(free[n]), []
                for vp, vpod, vr in lower:
                    if all(gain[k] >= r[k] for k in r):
                        break
                    chosen.append((vp, vpod, vr))
                    for k in gain:
                        gain[k] += vr[k]
                if chosen and all(gain[k] >= r[k] for k in r):
                    for v in chosen:
                        victims[n].remove(v)
                    free[n] = {k: gain[k] - r[k] for k in r}
                    names = ", ".join(v[1]["metadata"]["name"] for v in chosen)
                    verdict = f"fits {n} by preempting {names}"
                    break
        if verdict is None:
            verdict = "PENDING until the node is back"
            down += 1
        rows.append((name, pclass, r, verdict))

    w = max([len(x[0]) for x in rows] or [10])
    for name, pclass, r, verdict in rows:
        print(f"  {name:<{w}}  {pclass:<24} {mib(r['memory']):>7} {r['cpu']:5.2f}  {verdict}")
    print()
    print(f"{len(rows)} pods to move, {down} stay down until {node} is uncordoned"
          + (" (plus any preempted pods above)." if any("preempting" in x[3] for x in rows) else "."))


if __name__ == "__main__":
    main()
