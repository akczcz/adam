#!/usr/bin/env python3
"""
rolegen – generátor konfigurací platformy z definic rolí (knowledge/organization/roles/*.yaml, schéma role.md §2).

Z jednoho zdroje pravdy (YAML role v gitu) vzniká:
  build/opa/data.json                  data.roles.<role> pro jednu Rego politiku (policies/roles.rego) – gateway extAuthz, hook Agent SDK, PEP paměti
  build/agentgateway/apikeys-<tenant>-<zakazka>.yaml   policies.apiKey.keys[] s rozpočty (schema agentgateway 1.6: budgets[].limit/window/onBudgetExceeded)
  build/agentgateway/egress-allowlist.yaml             tcpRoutes.hostnames = sjednocení sandbox.egress_allow
  build/srt/<role>.json                ~/.srt-settings.json (schéma srt 0.0.81)
  build/claude/<role>-managed-settings.json            Claude Code managed settings (sandbox.*, permissions.deny)
  build/k8s/<role>-pod.yaml            pod spec (RuntimeClass, non-root, SA token off, labely, limity)
  build/inspect/<role>-approval.yaml   approval policy; build/inspect/<role>-evals.json vrstvy a gate
  build/registry/roles.json            řádky org.role_definitions (registr agentů T12)

Použití: rolegen.py --roles knowledge/organization/roles --out build --tenant acme --zakazka Z1
Deterministický výstup (stejný vstup → stejné soubory), žádná tajemství: klíče gateway jsou jen názvy (`k-…`), hodnoty vydává OpenBao.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

REQUIRED = ["role", "version", "owner", "processes", "autonomy_max", "identity", "authz", "budget", "memory", "sandbox", "evals", "escalation", "disclosure"]


def load_roles(d: Path) -> list[dict]:
    roles = []
    for f in sorted(d.glob("*.yaml")):
        r = yaml.safe_load(f.read_text())
        missing = [k for k in REQUIRED if k not in r]
        if missing: raise SystemExit(f"{f.name}: chybí bloky {missing}")
        if not re.fullmatch(r"[a-z]+", r["role"]): raise SystemExit(f"{f.name}: role musí být [a-z]+")
        if r["identity"]["spiffe_id"].split("/")[4] != r["role"]: raise SystemExit(f"{f.name}: 5. segment SPIFFE ID ≠ role")
        r["_file"] = f.name; r["_sha"] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        roles.append(r)
    return roles


def sub(v, ctx):
    if isinstance(v, str):
        for k, val in ctx.items(): v = v.replace("{%s}" % k, val)
        return v
    if isinstance(v, list): return [sub(x, ctx) for x in v]
    if isinstance(v, dict): return {k: sub(x, ctx) for k, x in v.items()}
    return v


def opa_data(roles):
    out = {}
    for r in roles:
        a, m = r["authz"], r["memory"]
        out[r["role"]] = {
            "version": r["version"], "autonomy_max": r["autonomy_max"], "processes": r["processes"],
            "mcp": {srv: {"allow": v.get("allow", []), "deny": v.get("deny", []), "with_approval": v.get("with_approval", [])} for srv, v in a.get("mcp", {}).items()},
            "http": a.get("http", []), "scopes": a.get("token_exchange_scopes", []),
            "memory": {"read": m.get("read", []), "read_proposed": bool(m.get("read_proposed")), "write": m.get("write", {}),
                       "approve": m.get("approve", {"enabled": False}), "forget": bool(m.get("forget"))},
            "irreversible": [],  # žádná agentní role nemá merge/deploy – vykonává executor (autonomie.md)
            "deny_tool_inputs": r["sandbox"].get("approval", {}).get("deny_tool_inputs", []),
        }
    return {"roles": out}


def gateway_keys(roles, tenant, zakazka):
    keys = []
    for r in roles:
        b = r["budget"]
        if not b.get("budgets"): continue
        ctx = {"tenant": tenant, "zakazka": zakazka}
        keys.append({
            "keyHash": "sha256:{{" + sub(b["gateway_key"], ctx) + "}}",   # hodnotu vydá OpenBao; sem jde jen hash – placeholder pro CI
            "metadata": {"name": sub(b["gateway_key"], ctx)} | sub(b.get("metadata", {}), ctx) | {"role": r["role"], "tenant": tenant, "zakazka": zakazka},   # agentgateway: klíč s budgets musí mít metadata.name
            "budgets": [{"name": f"{r['role']}-{x['window']}-{x['action'].lower()}", "limit": {"unit": x["unit"].upper(), "amount": x["amount"]},
                         "window": {"rolling": x["window"]}, "onBudgetExceeded": x["action"]} for x in b["budgets"]],
        })
    return {"policies": {"apiKey": {"mode": "strict", "location": {"header": {"name": "x-api-key"}}, "keys": keys}}}


def egress(roles):
    hosts = sorted({h for r in roles for h in r["sandbox"].get("egress_allow", [])})
    return {"tcpRoutes": [{"name": "roles-egress-allowlist", "gateways": "secure/public-egress", "hostnames": hosts, "backends": [{"dynamic": {}}]}]}


def pod(r, tenant):
    s, p = r["sandbox"], r["sandbox"].get("pod", {})
    if not p: return None
    res = p.get("resources", {})
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"generateName": f"role-{r['role']}-", "labels": sub(p.get("labels", {}), {"tenant": tenant, "workflow_instance": "{{wf}}"})},
            "spec": {"runtimeClassName": s["runtime_class"][0] if isinstance(s.get("runtime_class"), list) else s.get("runtime_class"),
                     "automountServiceAccountToken": bool(p.get("automount_service_account_token", False)),
                     "securityContext": {"runAsNonRoot": bool(p.get("run_as_non_root", True)), "runAsUser": p.get("run_as_user", 1000),
                                         "seccompProfile": ({"type": "Localhost", "localhostProfile": p["seccomp_profile"].split(":", 1)[1]} if str(p.get("seccomp_profile", "")).startswith("Localhost:") else {"type": "RuntimeDefault"})},
                     "containers": [{"name": "role", "image": s["image"], "env": [{"name": k, "value": str(v)} for k, v in s.get("env", {}).items()],
                                     "resources": {"limits": res, "requests": res}, "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": p.get("capabilities_drop", ["ALL"])}}}],
                     "restartPolicy": "Never"}}


def inspect_files(r):
    approval = {"approvers": []}
    rules = r["sandbox"].get("approval", {}).get("inspect_approval_policy") or ["sandboxed_bash(cmd=*git-receive-pack*) → reject", "* → approve"]  # výchozí z autonomie.md: push/merge nikdy přes nástroj role
    for rule in rules:
        pat, _, decision = rule.partition("→"); pat, decision = pat.strip(), decision.strip()
        approval["approvers"].append({"name": "auto", "tools": pat, "decision": decision or "approve"} if pat != "*" else {"name": "auto", "tools": "*", "decision": decision or "approve"})
    evals = {"role": r["role"], "version": r["version"], "k": r["evals"].get("k", 3), "layers": r["evals"]["layers"], "on_fail": r["evals"].get("on_fail", {})}
    return approval, evals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", default=str(Path(__file__).resolve().parents[2] / "knowledge/organization/roles"))
    ap.add_argument("--out", default="build"); ap.add_argument("--tenant", default="acme"); ap.add_argument("--zakazka", default="Z1")
    a = ap.parse_args()
    roles = load_roles(Path(a.roles)); out = Path(a.out)
    for d in ("opa", "agentgateway", "srt", "claude", "k8s", "inspect", "registry"): (out / d).mkdir(parents=True, exist_ok=True)
    (out / "opa/data.json").write_text(json.dumps(opa_data(roles), ensure_ascii=False, indent=1, sort_keys=True))
    (out / f"agentgateway/apikeys-{a.tenant}-{a.zakazka}.yaml").write_text(yaml.safe_dump(gateway_keys(roles, a.tenant, a.zakazka), sort_keys=False, allow_unicode=True))
    (out / "agentgateway/egress-allowlist.yaml").write_text(yaml.safe_dump(egress(roles), sort_keys=False))
    registry = []
    for r in roles:
        srt = r["sandbox"].get("srt_settings")
        if srt: (out / f"srt/{r['role']}.json").write_text(json.dumps(srt, indent=1, sort_keys=True))
        cs = r["sandbox"].get("claude_settings")
        if cs: (out / f"claude/{r['role']}-managed-settings.json").write_text(json.dumps(cs, indent=1, sort_keys=True))
        p = pod(r, a.tenant)
        if p: (out / f"k8s/{r['role']}-pod.yaml").write_text(yaml.safe_dump(p, sort_keys=False))
        approval, evals = inspect_files(r)
        (out / f"inspect/{r['role']}-approval.yaml").write_text(yaml.safe_dump(approval, sort_keys=False))
        (out / f"inspect/{r['role']}-evals.json").write_text(json.dumps(evals, ensure_ascii=False, indent=1))
        registry.append({"role": r["role"], "version": r["version"], "owner": r["owner"], "processes": r["processes"], "autonomy_max": r["autonomy_max"],
                         "spiffe_id": r["identity"]["spiffe_id"], "image": r["sandbox"].get("image"), "source": r["_file"], "source_sha256_16": r["_sha"],
                         "disclosure": r["disclosure"].get("channels", {}), "evals_gate": [{"layer": l["layer"], "gate": l.get("gate")} for l in r["evals"]["layers"]]})
    (out / "registry/roles.json").write_text(json.dumps(registry, ensure_ascii=False, indent=1))
    print(json.dumps({"roles": [r["role"] for r in roles], "files": sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
