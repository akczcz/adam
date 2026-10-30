#!/usr/bin/env python3
"""
rolegen – generátor konfigurací platformy z definic rolí (knowledge/organization/roles/*.yaml, schéma role.md §2).

Z jednoho zdroje pravdy (YAML role v gitu) vzniká:
  build/opa/data.json                  data.roles.<role> pro jednu Rego politiku (policies/roles.rego) – gateway extAuthz, hook Agent SDK, PEP paměti
  build/agentgateway/apikeys-<tenant>-<zakazka>.yaml   policies.apiKey.keys[] s rozpočty (schema agentgateway 1.6: budgets[].limit/window/onBudgetExceeded)
  build/agentgateway/egress.yaml                       CONNECT bind 3128, HTTPS listenery *.platform.internal (terminace, backendAuth, routy z authz.http), passthrough allow-list (P2-4)
  build/srt/<role>.json                ~/.srt-settings.json (schéma srt 0.0.81)
  build/claude/<role>-managed-settings.json            Claude Code managed settings (sandbox.*, permissions.deny)
  build/images/<role>/{Dockerfile,devcontainer.json,etc/platform/*}   obraz role (P2-2): vrstva nad obrazem platformy, options/srt/managed settings zapečené, bez cloud CLI
  build/k8s/<role>-pod.yaml            pod spec (RuntimeClass, non-root, SA token off, labely, limity)
  build/inspect/<role>-approval.yaml   approval policy; build/inspect/<role>-evals.json vrstvy a gate
  build/agent_sdk/<role>.json          ClaudeAgentOptions pro runtime role (tools=[], strict_mcp_config, setting_sources=[], cwd, mcp_servers) – nález O-2 live
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


TENANT_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")


def load_tenants(p: Path | None) -> list[dict]:
    """knowledge/organization/tenants.yaml (P3-2): id, name, profile, budget_usd, role_pods, humans. Bez souboru = jen acme (zpětná kompatibilita)."""
    if not p or not p.exists(): return [{"id": "acme", "name": "acme", "profile": "standard", "budget_usd": 100, "role_pods": True, "humans": []}]
    ts = (yaml.safe_load(p.read_text()) or {}).get("tenants") or []
    ids = set()
    for t in ts:
        if not TENANT_RE.match(str(t.get("id", ""))): raise SystemExit(f"{p.name}: tenant id musí být [a-z][a-z0-9-]{{1,30}}: {t.get('id')!r}")
        if t["id"] in ids: raise SystemExit(f"{p.name}: duplicitní tenant {t['id']}")
        ids.add(t["id"]); t.setdefault("profile", "standard"); t.setdefault("budget_usd", 0); t.setdefault("role_pods", False); t.setdefault("humans", [])
    return ts


def tenant_ns(tid): return f"tenant-{tid}"


KC_IDP_ALIAS = "aks"   # P3-6 E2: Keycloak identity provider typu kubernetes (projektovaný SA token podu role = client assertion klienta agent-<role>-<tenant>)


def tenant_k8s(tenants, agent_conf: str, roles=()):
    """Per tenant s pody rolí (P3-2): Namespace tenant-<id> (PSS restricted), NetworkPolicy default-deny + egress jen DNS/gateway/paměť/aplikace/SPIRE
    (žádný jiný tenant, žádný Postgres, žádný internet), SA `role-<role>` per role (P3-6 E2: projektovaný token SA = client assertion klienta
    Keycloaku agent-<role>-<tenant> – klient se hledá podle subjektu SA, proto SA per role; sidecar spire-agent; k8s_psat agent_ns = hranice tenanta),
    RBAC pro SA zakazka (pody a Secrety běhů jen v tomto ns), ConfigMap spire-agent-pod (agent.conf z infra/k8s/roles/spire-agent.conf)."""
    docs = []
    for t in tenants:
        if not t.get("role_pods"): continue
        ns = tenant_ns(t["id"]); lab = {"platform.tenant": t["id"]}
        def to(app, ports): return {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "platform-data"}}, "podSelector": {"matchLabels": {"app": app}}}], "ports": [{"protocol": "TCP", "port": p} for p in ports]}
        docs += [
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": lab | {"pod-security.kubernetes.io/enforce": "restricted", "pod-security.kubernetes.io/warn": "restricted", "platform.ca-bundle": "true"}}},   # platform.ca-bundle: trust-manager sem dá ConfigMap platform-ca (P3-6 E1)
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "default-deny", "namespace": ns}, "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "role-egress", "namespace": ns},
             "spec": {"podSelector": {"matchLabels": {"app": "role"}}, "policyTypes": ["Egress"], "egress": [
                 {"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}, "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]},
                 to("agentgateway", [4100, 3128]), to("memory", [9900]), to("zakazka", [8010]), to("spire-server", [8081]), to("keycloak", [8080, 8443])]}},   # keycloak: token exchange z podu (P3-6 E2; E7: 8443 https, 8080 jen kind)
            *[{"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": role_sa(r["role"]), "namespace": ns, "labels": lab | {"platform.role": r["role"]}}, "automountServiceAccountToken": False} for r in roles if r["sandbox"].get("pod")],
            {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "Role", "metadata": {"name": "role-pods", "namespace": ns}, "rules": [
                {"apiGroups": [""], "resources": ["pods"], "verbs": ["create", "get", "list", "watch", "delete"]},
                {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get"]},
                {"apiGroups": [""], "resources": ["secrets"], "verbs": ["create", "get", "list", "delete"]}]},
            {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "RoleBinding", "metadata": {"name": "zakazka-role-pods", "namespace": ns},
             "subjects": [{"kind": "ServiceAccount", "name": "zakazka", "namespace": "platform-data"}], "roleRef": {"kind": "Role", "name": "role-pods", "apiGroup": "rbac.authorization.k8s.io"}},
            {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "spire-agent-pod", "namespace": ns, "annotations": {"kustomize.toolkit.fluxcd.io/substitute": "disabled"}}, "data": {"agent.conf": agent_conf}},
        ]
    return docs


def sub(v, ctx):
    if isinstance(v, str):
        for k, val in ctx.items(): v = v.replace("{%s}" % k, val)
        return v
    if isinstance(v, list): return [sub(x, ctx) for x in v]
    if isinstance(v, dict): return {k: sub(x, ctx) for k, x in v.items()}
    return v


def opa_data(roles, tenants=None):
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
    return {"roles": out, "tenants": {t["id"]: {"profile": t["profile"], "budget_usd": t["budget_usd"], "role_pods": bool(t["role_pods"])} for t in (tenants or [])}}


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


def egress(roles, tenants=("acme",)):
    """Egress podů rolí přes agentgateway (P2-4): CONNECT bind 3128 → virtuální gateway `secure` (443). Interní hosty (*.platform.internal)
    terminuje HTTPS listener s certem gateway (Secret agentgateway-tls) – jen tam jde backendAuth (token vkládá gateway, pod ho nemá) a
    autorizace path/metoda z authz.http (CEL). Ostatní SNI z egress_allow jen passthrough allow-list (tcpRoute, dynamic backend).
    Backendy přes env gateway: $GIT_BACKEND_HOST, $MIRROR_BACKEND_HOST (Deployment: mock servery v clusteru; ostrý provoz: GitHub, Nexus)."""
    hosts = sorted({h for r in roles for h in r["sandbox"].get("egress_allow", [])})
    internal = [h for h in hosts if h.endswith(".platform.internal")]; public = [h for h in hosts if h not in internal]
    listeners = [{"name": h.split(".")[0], "hostname": h, "protocol": "HTTPS", "tls": {"cert": "/etc/platform-tls/tls.crt", "key": "/etc/platform-tls/tls.key"}} for h in internal]
    listeners.append({"name": "public-egress", "hostname": "*", "protocol": "TLS"})
    routes, by_route = [], {}
    for r in roles:   # routa gateway = sjednocení metod všech rolí (gateway dnes roli na CONNECT nerozezná – mTLS/SPIFFE na CONNECT bindu až P3);
        for h in r["authz"].get("http", []):   # per-role receive_pack (none/branches) vynucuje PEP role (OPA/approval) a git server (branch protection)
            if h["route"] in {l["name"] for l in listeners}: by_route.setdefault((h["route"], h["path_prefix"]), set()).update(h.get("methods", ["GET"]))
    for (route, prefix), methods in sorted(by_route.items()):
        for tenant in tenants:   # P3-2: routa per tenant – prefix /{tenant}/ ohraničuje repozitáře tenanta (gateway roli ani tenant na CONNECT nerozezná – cesta je hranice)
            allow = " || ".join(f'request.method == "{m}"' for m in sorted(methods))
            routes.append({"name": f"{route}-{tenant}", "gateways": f"secure/{route}", "matches": [{"path": {"pathPrefix": sub(prefix, {"tenant": tenant})}}],
                           "policies": {"authorization": {"rules": [{"allow": allow}]},   # push na chráněné větve (main/release) odmítá git server (branch protection) – ref je až v těle pkt-line, gateway ho nevidí
                                        "backendAuth": {"key": {"value": {"file": f"/etc/platform-egress/{route}/token"}, "location": {"header": {"name": "Authorization", "prefix": "Bearer "}}}}},
                           "backends": [{"host": f"${route.upper()}_BACKEND_HOST"}]})
    for l in listeners:   # terminovaný host bez authz.http (mirror): jen GET, bez tokenu, společný všem tenantům
        if l["name"] != "public-egress" and not any(rt["gateways"] == f"secure/{l['name']}" for rt in routes):
            routes.append({"name": f"{l['name']}-shared", "gateways": f"secure/{l['name']}", "matches": [{"path": {"pathPrefix": "/"}}],
                           "policies": {"authorization": {"rules": [{"allow": 'request.method == "GET"'}]}}, "backends": [{"host": f"${l['name'].upper()}_BACKEND_HOST"}]})
    out = {"binds": [{"port": 3128, "tunnelProtocol": "connect", "listeners": []}], "gateways": {"secure": {"port": 443, "listeners": listeners}}, "routes": routes}
    if public: out["tcpRoutes"] = [{"name": "roles-egress-allowlist", "gateways": "secure/public-egress", "hostnames": public, "backends": [{"dynamic": {}}]}]
    return out


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


def role_sa(role): return f"role-{role}"


def keycloak_clients(roles, tenants=("acme",)):
    """P3-6 E2: klienti Keycloaku agent-<role>-<tenant> – autentizace `federated-jwt` (Signed JWT - Federated) projektovaným tokenem SA role-<role>
    v ns tenanta (IdP `aks` typu kubernetes), zapnutý standard token exchange V2: pod role vymění access token schvalovatele (člověk z platform-gui)
    za token sub=člověk, azp=agent-<role>-<tenant>, aud=memory → „jedná jménem“ doložené podpisem Keycloaku, ne claimem aplikace. Bez service
    accountu (client_credentials nejsou potřeba). Aplikuje harness/operátor admin API (jako SPIRE entries); platform-gui dostane audience mappery."""
    clients, mappers = [], []
    for tenant in tenants:
        for r in roles:
            if not r["sandbox"].get("pod"): continue
            cid = f"agent-{r['role']}-{tenant}"
            clients.append({"clientId": cid, "name": f"role {r['role']} × tenant {tenant} (token exchange, SA {tenant_ns(tenant)}/{role_sa(r['role'])})", "enabled": True, "protocol": "openid-connect",
                            "publicClient": False, "standardFlowEnabled": False, "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False, "implicitFlowEnabled": False,
                            "clientAuthenticatorType": "federated-jwt",
                            "attributes": {"jwt.credential.issuer": KC_IDP_ALIAS, "jwt.credential.sub": f"system:serviceaccount:{tenant_ns(tenant)}:{role_sa(r['role'])}",
                                           "standard.token.exchange.enabled": "true", "access.token.lifespan": "1800"},
                            "defaultClientScopes": ["basic", "roles-flat", "tenant", "aud-memory"], "optionalClientScopes": []})
            mappers.append({"name": f"aud-{cid}", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                            "config": {"included.client.audience": cid, "access.token.claim": "true", "id.token.claim": "false", "introspection.token.claim": "true"}})
    return {"identity_provider": {"alias": KC_IDP_ALIAS, "providerId": "kubernetes"}, "clients": clients, "gui_mappers": mappers}


def spire_entries(roles, tenants=("acme",)):
    """Registrace SPIRE (P2-3, P3-2 per tenant): alias uzlu per role × tenant = sidecar agent podu role (k8s_psat selektory agent_ns tenant-<id>/SA/pod-label
    platform.role – namespace tenanta je atestovaná hranice, ne label od aplikace) a workload entry spiffe://platform/role/<role>/<tenant> přes
    unix uid 1000 (sdílený PID ns podu). Aplikuje harness/operátor přes `spire-server entry create`."""
    out = []
    for tenant in tenants:
        for r in roles:
            if not r["sandbox"].get("pod"): continue
            alias = f"spiffe://platform/agent-pod/role/{r['role']}/{tenant}"
            out.append({"spiffe_id": alias, "node": True, "selectors": ["k8s_psat:cluster:platform", f"k8s_psat:agent_ns:{tenant_ns(tenant)}", f"k8s_psat:agent_sa:{role_sa(r['role'])}", f"k8s_psat:agent_pod_label:platform.role:{r['role']}"]})
            out.append({"spiffe_id": f"spiffe://platform/role/{r['role']}/{tenant}", "parent_id": alias, "selectors": [f"unix:uid:{r['sandbox']['pod'].get('run_as_user', 1000)}"], "x509_svid_ttl": 3600, "jwt_svid_ttl": 1800})
    return out


def image_files(r, agent_sdk_json):
    """Obraz role (P2-2): vrstva nad obrazem platformy – ClaudeAgentOptions, srt settings a managed settings zapečené v /etc/platform,
    OCI labely s rolí/verzí/hashem zdroje, bez cloud CLI. Dockerfile je devcontainer-kompatibilní (devcontainer.json ukazuje na něj)."""
    s = r["sandbox"]; img = s.get("image", f"registry.platform.internal/roles/{r['role']}:{r['version']}")
    dockerfile = f"""# GENEROVÁNO rolegen z {r['_file']} (sha256 {r['_sha']}) – obraz role {r['role']} {r['version']}; cíl: {img}
ARG BASE_IMAGE=platform/zakazka-app:p1
FROM ${{BASE_IMAGE}}
LABEL org.opencontainers.image.title="platform role {r['role']}" org.opencontainers.image.version="{r['version']}" \
      platform.role="{r['role']}" platform.role.version="{r['version']}" platform.role.source_sha256_16="{r['_sha']}" platform.role.owner="{r['owner']}"
USER 0
COPY etc/platform/ /etc/platform/
RUN mkdir -p /etc/claude && cp /etc/platform/managed-settings.json /etc/claude/managed-settings.json \
 && for b in az gcloud aws kubectl docker helm terraform; do p=$(command -v "$b" 2>/dev/null) && rm -f "$p"; done; true   # žádný cloud CLI v obrazu role (role.md sandbox)
USER 1000
"""
    devc = {"name": f"role-{r['role']}", "build": {"dockerfile": "Dockerfile", "args": {"BASE_IMAGE": "platform/zakazka-app:p1"}}, "remoteUser": "app",
            "containerEnv": {k: str(v) for k, v in s.get("env", {}).items()}, "customizations": {"platform": {"role": r["role"], "version": r["version"], "image": img}}}
    etc = {"role.json": agent_sdk_json, "srt.json": json.dumps(s.get("srt_settings") or {}, indent=1, sort_keys=True), "managed-settings.json": json.dumps(s.get("claude_settings") or {}, indent=1, sort_keys=True)}
    return dockerfile, json.dumps(devc, ensure_ascii=False, indent=1), etc


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
    ap.add_argument("--out", default="build"); ap.add_argument("--tenant", default="acme", help="tenant pro šablonu klíčů a podu (CI: placeholder {tenant})"); ap.add_argument("--zakazka", default="Z1")
    ap.add_argument("--tenants", default=str(Path(__file__).resolve().parents[2] / "knowledge/organization/tenants.yaml"), help="P3-2: tenanti (namespace, SPIRE, routy, OPA, registr)")
    ap.add_argument("--spire-agent-conf", default=str(Path(__file__).resolve().parents[2] / "infra/k8s/roles/spire-agent.conf"))
    a = ap.parse_args()
    roles = load_roles(Path(a.roles)); out = Path(a.out); tenants = load_tenants(Path(a.tenants)); pod_tenants = [t["id"] for t in tenants if t.get("role_pods")]
    for d in ("opa", "agentgateway", "srt", "claude", "k8s", "inspect", "registry", "agent_sdk", "images"): (out / d).mkdir(parents=True, exist_ok=True)
    (out / "opa/data.json").write_text(json.dumps(opa_data(roles, tenants), ensure_ascii=False, indent=1, sort_keys=True))
    (out / f"agentgateway/apikeys-{a.tenant}-{a.zakazka}.yaml").write_text(yaml.safe_dump(gateway_keys(roles, a.tenant, a.zakazka), sort_keys=False, allow_unicode=True))
    (out / "agentgateway/egress.yaml").write_text(yaml.safe_dump(egress(roles, pod_tenants), sort_keys=False))
    (out / "spire").mkdir(exist_ok=True); (out / "spire/entries.json").write_text(json.dumps(spire_entries(roles, pod_tenants), ensure_ascii=False, indent=1))
    agent_conf = Path(a.spire_agent_conf).read_text() if Path(a.spire_agent_conf).exists() else ""
    (out / "k8s/tenants.yaml").write_text(yaml.safe_dump_all(tenant_k8s(tenants, agent_conf, roles), sort_keys=False))
    (out / "keycloak").mkdir(exist_ok=True); (out / "keycloak/clients.json").write_text(json.dumps(keycloak_clients(roles, pod_tenants), ensure_ascii=False, indent=1))   # P3-6 E2
    (out / "registry/tenants.json").write_text(json.dumps([{k: t[k] for k in ("id", "name", "profile", "budget_usd", "role_pods")} | {"namespace": tenant_ns(t["id"]) if t.get("role_pods") else None, "humans": [h["username"] for h in t.get("humans", [])]} for t in tenants], ensure_ascii=False, indent=1))
    registry = []
    for r in roles:
        srt = r["sandbox"].get("srt_settings")
        if srt: (out / f"srt/{r['role']}.json").write_text(json.dumps(srt, indent=1, sort_keys=True))
        cs = r["sandbox"].get("claude_settings")
        if cs: (out / f"claude/{r['role']}-managed-settings.json").write_text(json.dumps(cs, indent=1, sort_keys=True))
        p = pod(r, a.tenant)
        if p: (out / f"k8s/{r['role']}-pod.yaml").write_text(yaml.safe_dump(p, sort_keys=False))
        sdk = r["sandbox"].get("agent_sdk") or {}
        if sdk.get("tools", []) != []: raise SystemExit(f"{r['_file']}: sandbox.agent_sdk.tools musí být [] – vestavěné nástroje CLI běží mimo sandbox (O-2 live 2026-10-24)")
        sdk_json = json.dumps({"role": r["role"], "version": r["version"], "tools": [], "strict_mcp_config": True, "setting_sources": sdk.get("setting_sources", []),
                               "cwd": sdk.get("cwd", "/work"), "mcp_servers": sdk.get("mcp_servers", []), "permission_mode": "bypassPermissions",
                               "env": r["sandbox"].get("env", {}), "managed_settings": r["sandbox"].get("claude_settings", {})}, ensure_ascii=False, indent=1)
        (out / f"agent_sdk/{r['role']}.json").write_text(sdk_json)
        dockerfile, devc, etc = image_files(r, sdk_json)
        (out / f"images/{r['role']}/etc/platform").mkdir(parents=True, exist_ok=True)
        (out / f"images/{r['role']}/Dockerfile").write_text(dockerfile); (out / f"images/{r['role']}/devcontainer.json").write_text(devc)
        for n, c in etc.items(): (out / f"images/{r['role']}/etc/platform/{n}").write_text(c)
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
