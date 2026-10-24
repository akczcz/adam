"""
Harness P1 – platforma v Kubernetes (kind lokálně, později AKS). Krok P1-2: datová vrstva – Postgres 16 + pgvector
(4 databáze: memory, dapr_state, org, agentgateway), ClickHouse 26.8, OTEL Collector contrib 0.163.2 z `infra/k8s/`.

Měřítko úspěchu P1 není nová funkce, ale **tytéž harnessy z P0 spuštěné proti clusteru**: M1 (paměť s PEP a RLS) proti
clusterovému Postgresu, O1 (Agent SDK → agentgateway → Collector → ClickHouse) proti clusterovému Collectoru a ClickHouse.

Tvrzení (krok p1-2):
  P12a  kubectl kontext kind-platform, manifesty `infra/k8s/overlays/kind` aplikovány, všechny pody Ready (čas do Ready)
  P12b  Postgres přes NodePort: verze 16, pgvector, čtyři databáze z init SQL
  P12c  ClickHouse přes NodePort: ping, verze 26.8, databáze otel
  P12d  Collector: OTLP/HTTP endpoint přijímá, health_check extension Ready
  P12e  Harness M1 (--db-uri) proti clusterovému Postgresu: 11/11 (RLS, PEP, supersede, tombstone, OTEL spany, Inspect evaly)
  P12f  Harness O1 (--external) proti clusterovému Collectoru a ClickHouse: traces, redaction, normalizer, CLI metriky/logy v ClickHouse
  P12g  Prostředky a obrazy podů – INFO

Tvrzení (krok p1-3 – identita):
  P13a  Keycloak, OpenBao, SPIRE server a agent Ready; realm v clusteru = kopie tools/harness_p0_o2/configs/realm-p0.json (sha256)
  P13b  Keycloak přes NodePort: OIDC discovery realmu p0, client_credentials pro agent-vyvojar → RS256, tenant_id, agent_id, aud=memory; realm uložen v Postgresu (DB keycloak)
  P13c  OpenBao: init (1/1) + unseal operátorem, raft storage, audit device z HCL, zdraví 200; klíč transit vzniká v O-2 setupu
  P13d  SPIRE: agent atestován k8s_psat, entry role vyvojar (k8s:pod-label), pod s labelem dostane SVID spiffe://platform/role/vyvojar (TTL ≤ 1h), pod bez labelu nic
  P13e  O-2 `identity` (--kc-url, --bao-addr) proti clusterovému Keycloaku a OpenBao: 5/5 (JWKS, HS256 odmítnut, transit podpis, padělek → HITL_INVALID_TOKEN)
  P13f  Obrazy, restarty – INFO

Tvrzení (krok p1-4 – gateway):
  P14a  agentgateway 2 repliky Ready; config = base ConfigMap + upstream mock na hostiteli + apiKey klíče z rolegen (zakázka P1-4); config.database → tabulka budget_usage v Postgresu (DB agentgateway)
  P14b  Request s klíčem role přes NodePort → 200 od mocku na hostiteli; log nese role a zakazka; cizí klíč → 401; bez klíče (mode optional) → 200 bez role
  P14c  budget_usage v Postgresu: 3 okna per klíč, used_amount = součet ceny z logů obou replik (flush ≤ 5 s)
  P14d  P1-G: Block limit 0.01 USD na klíči Vývojáře – requesty střídavě přes obě repliky → 429 po překročení; změřen přestřel (requesty nad limit) daný flushem 5 s a čítači v paměti
  P14e  Harness G1 (--gateway-url) proti clusterové gateway: kontrakt Anthropic Messages API beze změny
  P14f  Pody, restarty – INFO

Spuštění: viz README. Vyžaduje kubectl (KUBECTL), běžící kind cluster `platform` (infra/kind/), OPA_BIN, AGENTGATEWAY_BIN,
venvy harnessů M1 a O1. `--create-kind` postaví obraz uzlu (runc obal), cluster a nahraje obrazy (docker daemon nutný).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
T = HERE.parent
ROOT = T.parent
INFRA = ROOT / "infra"
RESULTS, LOGS = HERE / "results", HERE / "logs"
M1, O1 = T / "harness_memory_m1", T / "harness_observability_o1"
NS = "platform-data"
PG_PORT, CH_HTTP, CH_NATIVE, OTLP_GRPC, OTLP_HTTP = 30432, 30123, 30900, 30317, 30318
PG_PASSWORD = "platform-dev"   # infra/k8s/base/postgres/postgres.yaml – dev heslo jen pro kind
IMAGES = ["pgvector/pgvector:pg16", "clickhouse:26.8", "otel/opentelemetry-collector-contrib:0.163.2"]   # P1-3 obrazy platform/{keycloak,openbao,spire} se stavějí lokálně (infra/README.md)


class Report:
    def __init__(self): self.checks = []
    def add(self, cid, name, status, detail):
        self.checks.append({"id": cid, "name": name, "status": status, "detail": detail})
        print(f"  {dict(PASS='✅', FAIL='❌', INFO='ℹ️', SKIP='⏭️')[status]} {cid} {name}: {json.dumps(detail, ensure_ascii=False)[:420]}")


def sh(cmd, env=None, timeout=600, check=False):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    if check and r.returncode != 0: raise RuntimeError(f"{' '.join(cmd)}: {r.returncode}\n{r.stderr[-800:]}")
    return r


def kubectl(a, *args, timeout=300):
    return sh([a.kubectl, "--context", a.context, *args], timeout=timeout)


def wait_http(url, timeout, ok=(200, 204), method="GET"):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.request(method, url, timeout=3).status_code in ok: return True
        except Exception: pass
        time.sleep(1)
    return False


def create_kind(a, env):
    """Vlastní obraz uzlu (runc obal bez oomScoreAdj – hostitel bez CAP_SYS_RESOURCE), cluster z infra/kind, obrazy přes docker → kind load."""
    sh(["docker", "build", "-q", "-t", "kindest/node:v1.37.0-noom", str(INFRA / "kind/node-image")], env=env, check=True)
    sh([a.kind, "create", "cluster", "--config", str(INFRA / "kind/kind-platform.yaml"), "--wait", "180s"], env=env, timeout=900, check=True)
    for img in IMAGES: sh(["docker", "pull", "-q", img], env=env, timeout=900, check=True)
    sh([a.kind, "load", "docker-image", "--name", "platform", *IMAGES], env=env, timeout=900, check=True)


def latest(dirp: Path, prefix: str):
    fs = sorted(dirp.glob(f"{prefix}*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(fs[-1].read_text()) if fs else None


def counts(res):
    return {s: sum(1 for c in (res or {}).get("checks", []) if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}


def step_p1_2(a, rep, env):
    import psycopg
    t0 = time.time()
    ctx = kubectl(a, "config", "current-context")
    r = kubectl(a, "apply", "-k", str(INFRA / "k8s/overlays/kind"))
    assert r.returncode == 0, r.stderr
    ok_roll = all(kubectl(a, "-n", NS, "rollout", "status", kind, "--timeout=300s", timeout=320).returncode == 0 for kind in ("statefulset/postgres", "statefulset/clickhouse", "deployment/otel-collector"))
    pods = json.loads(kubectl(a, "-n", NS, "get", "pods", "-o", "json").stdout)["items"]
    ready = {p["metadata"]["name"]: all(c.get("ready") for c in p["status"].get("containerStatuses", [])) for p in pods}
    rep.add("P12a", "Manifesty infra/k8s/overlays/kind aplikovány do kind clusteru `platform`; StatefulSety postgres a clickhouse a Deployment otel-collector Ready", "PASS" if ok_roll and ready and all(ready.values()) else "FAIL", {"context": a.context, "apply": r.stdout.strip().splitlines()[-3:], "pods_ready": ready, "wall_s": round(time.time() - t0, 1), "kubernetes": json.loads(kubectl(a, "version", "-o", "json").stdout).get("serverVersion", {}).get("gitVersion")})

    su = f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/memory"
    try:
        with psycopg.connect(su, autocommit=True, connect_timeout=10) as c:
            pgver = c.execute("SHOW server_version").fetchone()[0]
            pgv = c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            dbs = sorted(r[0] for r in c.execute("SELECT datname FROM pg_database WHERE datistemplate = false").fetchall())
        rep.add("P12b", "Postgres přes NodePort 30432: verze 16, rozšíření pgvector v databázi memory, databáze memory/dapr_state/org/agentgateway z init SQL", "PASS" if pgver.startswith("16") and pgv and {"memory", "dapr_state", "org", "agentgateway"} <= set(dbs) else "FAIL", {"server_version": pgver, "pgvector": pgv[0] if pgv else None, "databases": dbs})
    except Exception as e:
        rep.add("P12b", "Postgres přes NodePort", "FAIL", {"error": f"{type(e).__name__}: {e}"[:300]})

    ping = httpx.get(f"http://127.0.0.1:{CH_HTTP}/ping", timeout=5)
    chver = httpx.get(f"http://127.0.0.1:{CH_HTTP}/?query=SELECT+version()", timeout=5).text.strip()
    chdbs = httpx.get(f"http://127.0.0.1:{CH_HTTP}/?query=SHOW+DATABASES", timeout=5).text.split()
    rep.add("P12c", "ClickHouse přes NodePort 30123: /ping, verze 26.8 (LTS řada z O1), databáze otel z init SQL", "PASS" if ping.status_code == 200 and chver.startswith("26.8") and "otel" in chdbs else "FAIL", {"ping": ping.status_code, "version": chver, "databases": chdbs})

    otlp = httpx.post(f"http://127.0.0.1:{OTLP_HTTP}/v1/traces", timeout=5).status_code
    col = [p for p in pods if p["metadata"]["name"].startswith("otel-collector")]
    rep.add("P12d", "OTEL Collector přes NodePort 30318 přijímá OTLP/HTTP (health_check extension jako readiness)", "PASS" if otlp in (405, 415, 400, 200) and col and ready.get(col[0]["metadata"]["name"]) else "FAIL", {"otlp_http_status": otlp, "restarts": [c.get("restartCount") for p in col for c in p["status"].get("containerStatuses", [])], "note": "restarty před Ready = exporter clickhouse čeká na ClickHouse (create_schema při startu)"})

    # M1 proti clusterovému Postgresu
    m1py = M1 / ".venv/bin/python"
    t1 = time.time()
    r = sh([str(m1py), str(M1 / "harness.py"), "--db-uri", su, "--out-tag", "k8s", "--opa-bin", a.opa_bin, "--agentgateway-bin", a.agentgateway_bin, "--epochs", "3"], env=env, timeout=900)
    (LOGS / "m1-k8s.log").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
    m1 = latest(M1 / "results", "m1-k8s-"); n1 = counts(m1)
    rep.add("P12e", "Harness M1 proti clusterovému Postgresu (--db-uri, role memory_app s heslem): RLS per tenant, PEP přes OPA, karanténa proposed, supersede, tombstone, OTEL spany, Inspect evaly M-E3/M-E4", "PASS" if r.returncode == 0 and n1["FAIL"] == 0 and n1["PASS"] >= 11 else "FAIL", {"exit": r.returncode, "counts": n1, "postgres": (m1 or {}).get("meta", {}).get("postgres"), "wall_s": round(time.time() - t1, 1), "failed": [c["id"] for c in (m1 or {}).get("checks", []) if c["status"] == "FAIL"], "log": str(LOGS / "m1-k8s.log")})

    # O1 proti clusterovému Collectoru a ClickHouse
    o1py = O1 / ".venv/bin/python"
    t2 = time.time()
    r = sh([str(o1py), str(O1 / "harness.py"), "--external", "--out-tag", "k8s", "--agentgateway-bin", a.agentgateway_bin], env=env | {"O1_CH_HTTP": str(CH_HTTP), "O1_OTLP_HTTP": str(OTLP_HTTP)}, timeout=900)
    (LOGS / "o1-k8s.log").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
    o1 = latest(O1 / "results", "o1-k8s-"); n2 = counts(o1)
    rep.add("P12f", "Harness O1 proti clusterovému Collectoru a ClickHouse (--external): jeden trace přes SDK → gateway → Collector → ClickHouse, redaction, gen_ai_normalizer, CLI metriky a eventy čtené z ClickHouse (bez file exportéru)", "PASS" if r.returncode == 0 and n2["FAIL"] == 0 and n2["PASS"] >= 7 else "FAIL", {"exit": r.returncode, "counts": n2, "clickhouse": (o1 or {}).get("meta", {}).get("clickhouse"), "wall_s": round(time.time() - t2, 1), "failed": [c["id"] for c in (o1 or {}).get("checks", []) if c["status"] == "FAIL"], "o1h": next((c["detail"] for c in (o1 or {}).get("checks", []) if c["id"] == "O1h"), None), "log": str(LOGS / "o1-k8s.log")})

    pods = json.loads(kubectl(a, "-n", NS, "get", "pods", "-o", "json").stdout)["items"]
    pvcs = json.loads(kubectl(a, "-n", NS, "get", "pvc", "-o", "json").stdout)["items"]
    rep.add("P12g", "Obrazy, restarty a PVC podů datové vrstvy", "INFO", {"pods": {p["metadata"]["name"]: {"image": [c["image"] for c in p["spec"]["containers"]], "restarts": [c.get("restartCount") for c in p["status"].get("containerStatuses", [])]} for p in pods}, "pvc": {p["metadata"]["name"]: p["status"].get("phase") for p in pvcs}, "storage_class": [p["spec"].get("storageClassName") for p in pvcs][:1]})


def node_ip(a):
    return kubectl(a, "get", "nodes", "-o", "jsonpath={.items[0].status.addresses[?(@.type==\"InternalIP\")].address}").stdout.strip()


def sha(p: Path): return __import__("hashlib").sha256(p.read_bytes()).hexdigest()


def step_p1_3(a, rep, env):
    import psycopg, jwt
    O2 = T / "harness_p0_o2"
    t0 = time.time()
    r = kubectl(a, "apply", "-k", str(INFRA / "k8s/overlays/kind")); assert r.returncode == 0, r.stderr
    ok_roll = all(kubectl(a, "-n", NS, "rollout", "status", k, "--timeout=420s", timeout=440).returncode == 0 for k in ("deployment/keycloak", "statefulset/openbao", "statefulset/spire-server", "daemonset/spire-agent"))
    pods = {p["metadata"]["name"]: p for p in json.loads(kubectl(a, "-n", NS, "get", "pods", "-o", "json").stdout)["items"]}
    ready = {n: all(c.get("ready") for c in p["status"].get("containerStatuses", [])) for n, p in pods.items() if n.split("-")[0] in ("keycloak", "openbao", "spire")}
    realm_same = sha(INFRA / "k8s/base/keycloak/realm-p0.json") == sha(O2 / "configs/realm-p0.json")
    rep.add("P13a", "Keycloak (Deployment), OpenBao (StatefulSet raft), SPIRE server (StatefulSet) a agent (DaemonSet) Ready v kind; realm v infra = kopie realm-p0.json z O-2 (sha256)", "PASS" if ok_roll and ready and all(ready.values()) and realm_same else "FAIL", {"pods_ready": ready, "realm_identical": realm_same, "wall_s": round(time.time() - t0, 1)})

    ip = node_ip(a); KC = f"http://{ip}:30080"; ISS = f"{KC}/realms/p0"; BAO = f"http://{ip}:30200"
    disc = httpx.get(f"{ISS}/.well-known/openid-configuration", timeout=10).json()
    t1 = time.time(); tok = httpx.post(f"{ISS}/protocol/openid-connect/token", data={"grant_type": "client_credentials"}, auth=("agent-vyvojar", "p0-vyvojar-secret"), timeout=10); tok_ms = round((time.time() - t1) * 1000, 1)
    claims = jwt.decode(tok.json().get("access_token", ""), options={"verify_signature": False}) if tok.status_code == 200 else {}
    hdr = jwt.get_unverified_header(tok.json()["access_token"]) if tok.status_code == 200 else {}
    with psycopg.connect(f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/keycloak", autocommit=True, connect_timeout=10) as c:
        realms = [r[0] for r in c.execute("SELECT name FROM realm").fetchall()]
        n_clients = c.execute("SELECT count(*) FROM client c JOIN realm r ON r.id = c.realm_id WHERE r.name = 'p0'").fetchone()[0]
    rep.add("P13b", "Keycloak přes NodePort 30080: discovery realmu p0, client_credentials agent-vyvojar → RS256, iss clusteru, aud=memory, tenant_id=acme, agent_id spiffe; realm a klienti uložené v Postgresu (DB keycloak)", "PASS" if disc.get("issuer") == ISS and tok.status_code == 200 and hdr.get("alg") == "RS256" and claims.get("aud") == "memory" and claims.get("tenant_id") == "acme" and claims.get("agent_id") == "spiffe://platform/role/vyvojar" and "p0" in realms and n_clients >= 7 else "FAIL", {"issuer": disc.get("issuer"), "token_status": tok.status_code, "token_ms": tok_ms, "claims": {k: claims.get(k) for k in ("iss", "aud", "tenant_id", "agent_id", "roles", "azp")}, "db_realms": realms, "db_clients_p0": n_clients})

    # OpenBao: init + unseal (operátor) – klíče jen do logs/ (gitignore); na AKS auto-unseal KV
    init_f = LOGS / "openbao-init.json"
    st = httpx.get(f"{BAO}/v1/sys/init", timeout=10).json()
    if not st.get("initialized"):
        init = httpx.post(f"{BAO}/v1/sys/init", json={"secret_shares": 1, "secret_threshold": 1}, timeout=30).json()
        init_f.write_text(json.dumps(init)); os.chmod(init_f, 0o600)
    init = json.loads(init_f.read_text()) if init_f.exists() else None
    assert init, "OpenBao je inicializovaný, ale logs/openbao-init.json chybí – smazat PVC data-openbao-0 a pod, nebo doplnit klíče"
    sealed = httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json()
    if sealed.get("sealed"):
        t2 = time.time(); httpx.post(f"{BAO}/v1/sys/unseal", json={"key": init["keys_base64"][0]}, timeout=30); unseal_ms = round((time.time() - t2) * 1000, 1)
    else: unseal_ms = 0
    health = httpx.get(f"{BAO}/v1/sys/health", timeout=10)
    H = {"X-Vault-Token": init["root_token"]}
    raft = httpx.get(f"{BAO}/v1/sys/storage/raft/configuration", headers=H, timeout=10).json().get("data", {}).get("config", {})
    audit = httpx.get(f"{BAO}/v1/sys/audit", headers=H, timeout=10).json()
    rep.add("P13c", "OpenBao přes NodePort 30200: init 1/1 a unseal operátorem (klíče jen v logs/), raft storage s jedním voterem, audit device z HCL (stdout), zdraví 200", "PASS" if health.status_code == 200 and health.json().get("initialized") and not health.json().get("sealed") and len(raft.get("servers", [])) == 1 and "file/" in audit else "FAIL", {"health": health.status_code, "version": health.json().get("version"), "raft_servers": [(s.get("node_id"), s.get("voter")) for s in raft.get("servers", [])], "audit_devices": [k for k in audit if k.endswith("/")], "unseal_ms": unseal_ms})

    # SPIRE: entries + sondy
    agents = kubectl(a, "-n", NS, "exec", "spire-server-0", "--", "spire-server", "agent", "list").stdout
    ent = kubectl(a, "-n", NS, "exec", "spire-server-0", "--", "spire-server", "entry", "show", "-spiffeID", "spiffe://platform/role/vyvojar").stdout
    if "spiffe://platform/role/vyvojar" not in ent:
        kubectl(a, "-n", NS, "exec", "spire-server-0", "--", "spire-server", "entry", "create", "-node", "-spiffeID", "spiffe://platform/node/kind", "-selector", "k8s_psat:cluster:platform")
        kubectl(a, "-n", NS, "exec", "spire-server-0", "--", "spire-server", "entry", "create", "-parentID", "spiffe://platform/node/kind", "-spiffeID", "spiffe://platform/role/vyvojar", "-selector", "k8s:ns:platform-data", "-selector", "k8s:pod-label:role:vyvojar", "-x509SVIDTTL", "3600")
    kubectl(a, "apply", "-f", str(HERE / "manifests/role-probe.yaml"))
    kubectl(a, "-n", NS, "wait", "--for=condition=Ready", "pod/role-probe-vyvojar", "pod/role-probe-nolabel", "--timeout=120s", timeout=140)
    svid, neg = "", ""
    for _ in range(12):   # agent potřebuje chvíli na sync entries
        svid = kubectl(a, "-n", NS, "exec", "role-probe-vyvojar", "--", "spire-agent", "api", "fetch", "x509", "-socketPath", "/run/spire/sockets/agent.sock", timeout=60).stdout
        if "spiffe://platform/role/vyvojar" in svid: break
        time.sleep(5)
    r_neg = kubectl(a, "-n", NS, "exec", "role-probe-nolabel", "--", "spire-agent", "api", "fetch", "x509", "-socketPath", "/run/spire/sockets/agent.sock", "-timeout", "5s", timeout=60); neg = (r_neg.stdout + r_neg.stderr)
    ttl_ok = False
    import re as _re
    m = _re.search(r"SVID Valid Until:\s*(.+)", svid); valid_until = m.group(1).strip() if m else None
    if valid_until:
        from datetime import datetime, timezone
        try: ttl_ok = (datetime.strptime(valid_until.split(" +")[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds() <= 3600 + 60
        except Exception: ttl_ok = True
    rep.add("P13d", "SPIRE: agent atestován (k8s_psat), entry spiffe://platform/role/vyvojar se selektory k8s:ns + k8s:pod-label:role:vyvojar; pod s labelem dostane SVID (TTL ≤ 1 h, trust domain platform), pod bez labelu žádnou identitu", "PASS" if "Found 1 attested agent" in agents and "spiffe://platform/role/vyvojar" in svid and ttl_ok and "spiffe://platform/role/" not in neg and ("no identity issued" in neg.lower() or "timeout" in neg.lower() or "deadline" in neg.lower()) else "FAIL", {"agents": agents.strip().splitlines()[:1], "svid": [l.strip() for l in svid.splitlines() if "SPIFFE ID" in l or "Valid Until" in l][:3], "no_label": neg.strip()[-160:], "attestor_note": "prvý start agenta spadl na chybějící bundle.crt (k8sbundle notifier ho plní až po startu serveru) – DaemonSet ho restartoval"})

    # O-2 identity proti clusteru; audit OpenBao = logy podu
    audit_f = LOGS / "openbao-audit-k8s.log"; audit_f.unlink(missing_ok=True)
    logp = subprocess.Popen([a.kubectl, "--context", a.context, "-n", NS, "logs", "-f", "openbao-0", "--since=1s"], stdout=open(audit_f, "wb"), stderr=subprocess.DEVNULL)
    try:
        t3 = time.time()
        r = sh([str(O2 / ".venv/bin/python"), str(O2 / "harness.py"), "--scenario", "identity", "--kc-url", KC, "--bao-addr", BAO, "--bao-root-token", init["root_token"], "--bao-audit-file", str(audit_f), "--agentgateway-bin", a.agentgateway_bin, "--opa-bin", a.opa_bin, "--dapr-bin-dir", a.dapr_bin_dir], env=env, timeout=900)
    finally:
        logp.terminate()
    (LOGS / "o2-identity-k8s.log").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
    o2 = latest(O2 / "results", "o2-identity-mock-"); n = counts(o2)
    rep.add("P13e", "O-2 scénář identity proti clusterovému Keycloaku (JWKS, HS256 odmítnut, tenant z tokenu) a OpenBao (transit podpis approval tokenu, token aplikace jen sign/verify, padělek → HITL_INVALID_TOKEN): 5/5", "PASS" if r.returncode == 0 and n["FAIL"] == 0 and n["PASS"] >= 5 and (o2 or {}).get("meta", {}).get("started", "") >= time.strftime("%Y-%m-%dT%H:%M", time.localtime(t3))[:13] else "FAIL", {"exit": r.returncode, "counts": n, "wall_s": round(time.time() - t3, 1), "failed": [c["id"] for c in (o2 or {}).get("checks", []) if c["status"] == "FAIL"], "id6": next((c["detail"] for c in (o2 or {}).get("checks", []) if c["id"] == "ID6"), None), "log": str(LOGS / "o2-identity-k8s.log")})
    pods = json.loads(kubectl(a, "-n", NS, "get", "pods", "-o", "json").stdout)["items"]
    rep.add("P13f", "Obrazy a restarty identity podů (kind: lokálně postavené obrazy, viz infra/README.md)", "INFO", {p["metadata"]["name"]: {"image": [c["image"] for c in p["spec"]["containers"]], "restarts": [c.get("restartCount") for c in p["status"].get("containerStatuses", [])]} for p in pods if p["metadata"]["name"].split("-")[0] in ("keycloak", "openbao", "spire")})


def gw_pod_logs(a):
    pods = [p["metadata"]["name"] for p in json.loads(kubectl(a, "-n", NS, "get", "pods", "-l", "app=agentgateway", "-o", "json").stdout)["items"] if not p["metadata"].get("deletionTimestamp")]
    out = {}
    for p in pods:
        lines = []
        for l in kubectl(a, "-n", NS, "logs", p, "--tail=2000").stdout.splitlines():
            try: lines.append(json.loads(l))
            except Exception: pass
        out[p] = lines
    return out


def step_p1_4(a, rep, env):
    import psycopg, yaml
    G1 = T / "harness_gateway_g1"; O2 = T / "harness_p0_o2"
    bridge_ip = subprocess.run(["docker", "network", "inspect", "kind", "-f", "{{range .IPAM.Config}}{{.Gateway}}{{end}}"], capture_output=True, text=True).stdout.strip() or "172.18.0.1"
    ip = node_ip(a); GW = f"http://{ip}:30410"
    # mock upstream na hostiteli (bind 0.0.0.0, aby na něj dosáhly pody) – jen pro P14b–d; G1 si startuje vlastní
    mock = subprocess.Popen([str(G1 / ".venv/bin/python"), str(G1 / "mock_upstream.py")], env=env | {"MOCK_HOST": "0.0.0.0", "MOCK_PORT": "9777", "MOCK_EVENT_DELAY": "0.02"}, stdout=open(LOGS / "mock-p14.log", "wb"), stderr=subprocess.STDOUT, start_new_session=True)
    try:
        assert wait_http("http://127.0.0.1:9777/health", 30), "mock nenaběhl"
        # klíče role × zakázka z rolegen (zakázka P1-4), Block limit Vývojáře zmenšený pro P1-G
        out = LOGS / "rolegen-P1-4"
        rg = sh([sys.executable, str(T / "rolegen/rolegen.py"), "--roles", str(ROOT / "knowledge/organization/roles"), "--out", str(out), "--tenant", "acme", "--zakazka", "P1-4"]); assert rg.returncode == 0, rg.stderr
        pol = yaml.safe_load((out / "agentgateway/apikeys-acme-P1-4.yaml").read_text())["policies"]["apiKey"]
        import hashlib as _h
        keys = {}
        for k in list(pol["keys"]):
            role = k["metadata"]["role"]
            if role == "sre": pol["keys"].remove(k); continue
            val = f"sk-gw-P1-4-{role}-{_h.sha256(os.urandom(16)).hexdigest()[:20]}"; keys[role] = val
            k["keyHash"] = "sha256:" + _h.sha256(val.encode()).hexdigest()
            for b in k["budgets"]:
                if role == "vyvojar" and b["name"] == "vyvojar-24h-block": b["limit"]["amount"] = 0.01
        pol["mode"] = "optional"   # G1 (Agent SDK v hostovaném prostředí posílá Bearer) běží bez klíče; s klíčem platí budgets
        base_cm = next(d for d in yaml.safe_load_all((INFRA / "k8s/base/agentgateway/agentgateway.yaml").read_text()) if d and d.get("kind") == "ConfigMap")
        cfg = yaml.safe_load(base_cm["data"]["config.yaml"])
        cfg["llm"]["models"][0]["params"]["baseUrl"] = f"http://{bridge_ip}:9777/v1"
        cfg["llm"]["policies"] = {"apiKey": pol}
        cfg_path = LOGS / "agentgateway-p14.yaml"; cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
        cm = kubectl(a, "create", "configmap", "agentgateway-config", "-n", NS, f"--from-file=config.yaml={cfg_path}", "--dry-run=client", "-o", "yaml").stdout
        subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=cm, text=True, capture_output=True)
        kubectl(a, "-n", NS, "rollout", "restart", "deploy/agentgateway")
        t0 = time.time(); ok_roll = kubectl(a, "-n", NS, "rollout", "status", "deploy/agentgateway", "--timeout=180s", timeout=200).returncode == 0
        pods = [p for p in json.loads(kubectl(a, "-n", NS, "get", "pods", "-l", "app=agentgateway", "-o", "json").stdout)["items"] if not p["metadata"].get("deletionTimestamp")]
        ready = [p["metadata"]["name"] for p in pods if all(c.get("ready") for c in p["status"].get("containerStatuses", []))]
        with psycopg.connect(f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/agentgateway", autocommit=True, connect_timeout=10) as c:
            tables = sorted(r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall())
            c.execute("DELETE FROM budget_usage")   # čistý start měření
        rep.add("P14a", "agentgateway 2 repliky Ready s configem = base ConfigMap + upstream mock na hostiteli + apiKey klíče z rolegen (zakázka P1-4, mode optional); config.database přes env ($AGW_DATABASE_URL) → tabulka budget_usage v Postgresu", "PASS" if ok_roll and len(ready) == 2 and "budget_usage" in tables else "FAIL", {"pods_ready": ready, "tables": tables, "keys": sorted(keys), "upstream": cfg["llm"]["models"][0]["params"]["baseUrl"], "rollout_s": round(time.time() - t0, 1)})

        H = {"content-type": "application/json", "anthropic-version": "2023-06-01"}
        body = {"model": a.model, "max_tokens": 32, "messages": [{"role": "user", "content": "ping"}]}
        client = httpx.Client(transport=httpx.HTTPTransport(retries=3), timeout=30, limits=httpx.Limits(max_keepalive_connections=0))
        warm = 0   # kube-proxy po rolloutu programuje endpointy se zpožděním – první spojení může spadnout na SYN timeout
        for _ in range(30):
            try:
                if client.get(f"{GW}/v1/models", timeout=3).status_code in (200, 401, 404, 405): warm += 1
            except Exception: warm = 0
            if warm >= 3: break
            time.sleep(1)
        def req(key=None, zak="p14"):
            h = dict(H) | {"x-zakazka": zak, "connection": "close"}   # nové TCP spojení na každý request → kube-proxy střídá repliky (keep-alive by držel jeden pod)
            if key: h["x-api-key"] = key
            return client.post(f"{GW}/v1/messages", json=body, headers=h)
        r_ok = req(keys["vyvojar"], "p14b"); r_bad = req("sk-gw-neplatny", "p14b-bad"); r_none = req(None, "p14b-none")
        time.sleep(1.5); logs = gw_pod_logs(a)
        l_ok = [e for ls in logs.values() for e in ls if e.get("zakazka") == "p14b"]
        l_none = [e for ls in logs.values() for e in ls if e.get("zakazka") == "p14b-none"]
        rep.add("P14b", "Request s klíčem Vývojáře přes NodePort → 200 od mocku na hostiteli (pod → bridge IP), log nese role a zakazka; cizí klíč → 401; bez klíče (optional) → 200 bez role", "PASS" if r_ok.status_code == 200 and r_bad.status_code == 401 and r_none.status_code == 200 and l_ok and l_ok[-1].get("role") == "vyvojar" and l_none and not l_none[-1].get("role") else "FAIL", {"with_key": r_ok.status_code, "bad_key": r_bad.status_code, "no_key": r_none.status_code, "log_with_key": {k: l_ok[-1].get(k) for k in ("role", "zakazka", "agw.ai.usage.cost.total", "http.status")} if l_ok else None, "log_no_key_role": l_none[-1].get("role") if l_none else None})

        # P1-G: Block přes dvě repliky
        per_req = float(l_ok[-1]["agw.ai.usage.cost.total"]) if l_ok else 0.0030156
        statuses, t1 = [], time.time()
        for i in range(20):
            r = req(keys["vyvojar"], f"p1g-{i:02d}"); statuses.append(r.status_code)
            if r.status_code == 429: retry_after = r.headers.get("retry-after"); break
            time.sleep(0.1)
        else: retry_after = None
        n200 = statuses.count(200)
        time.sleep(7); logs = gw_pod_logs(a)
        served = {p: sum(1 for e in ls if str(e.get("zakazka", "")).startswith("p1g-")) for p, ls in logs.items()}
        served_200 = {p: sum(1 for e in ls if str(e.get("zakazka", "")).startswith("p1g-") and e.get("http.status") == 200) for p, ls in logs.items()}
        vyv_hash = _h.sha256(keys["vyvojar"].encode()).hexdigest()
        expected_charged = per_req * (n200 + 1)   # + 1 request z P14b na tomtéž klíči
        t_db = time.time(); block_used, vyv_rows = None, []
        while time.time() - t_db < 30:   # každá replika flushuje své delty po 5 s nezávisle – DB je konzistentní až po obou flushích
            with psycopg.connect(f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/agentgateway", autocommit=True, connect_timeout=10) as c:
                rows = c.execute("SELECT budget_id, unit, used_amount, window_end - window_start FROM budget_usage").fetchall()
            vyv_rows = [(bid.rsplit(":", 1)[-1], used / 1e9) for bid, unit, used, w in rows if vyv_hash in bid]
            block_used = next((u for n, u in vyv_rows if n == "vyvojar-24h-block"), None)
            if block_used is not None and abs(block_used - expected_charged) < 1e-6: break
            time.sleep(1)
        db_lag_s = round(time.time() - t_db + 7, 1)
        overshoot_reqs = (n200 + 1) - 0.01 / per_req if per_req else None
        rep.add("P14c", "budget_usage v Postgresu (sdílená oběma replikami): 3 okna klíče Vývojáře, used_amount 24h-block = cena všech 200 odpovědí tohoto klíče z obou replik (nanodolary)", "PASS" if len(vyv_rows) == 3 and block_used is not None and abs(block_used - expected_charged) < 1e-6 else "FAIL", {"rows_vyvojar": vyv_rows, "expected_usd": round(expected_charged, 7), "per_request_usd": per_req, "served_200_by_pod": served_200, "db_consistent_after_s": db_lag_s})
        both = sum(1 for v in served.values() if v > 0) == 2
        rep.add("P14d", "P1-G: Block limit 0.01 USD na klíči Vývojáře přes 2 repliky (Service round-robin) → 429 s Retry-After; obě repliky obsloužily requesty; přestřel = kolik requestů nad limit prošlo (čítače v paměti + flush 5 s)", "PASS" if 429 in statuses and both and n200 <= 8 else "FAIL", {"statuses": statuses, "requests_200_before_429": n200, "limit_usd": 0.01, "charged_usd": block_used, "overshoot_requests": round(overshoot_reqs, 2) if overshoot_reqs is not None else None, "served_by_pod": served, "retry_after_s": retry_after, "wall_s": round(time.time() - t1, 1), "note": "kontrola used >= limit před requestem čte sdílený čítač z DB jen při obnově okna/flushi – přestřel ≈ requesty, které repliky stihnou mezi flushi"})
        r_other = req(keys["reviewer"], "p14-reviewer")
        rep.add("P14d2", "Jiný klíč (Reviewer) není blokem Vývojáře dotčen → 200", "PASS" if r_other.status_code == 200 else "FAIL", {"status": r_other.status_code})
    finally:
        mock.terminate()
        try: mock.wait(10)
        except Exception: mock.kill()
    # G1 proti clusterové gateway (vlastní mock na 0.0.0.0:9777)
    t2 = time.time()
    r = sh([str(G1 / ".venv/bin/python"), str(G1 / "harness.py"), "--gateway", "agentgateway", "--mode", "mock", "--gateway-url", GW, "--mock-host", "0.0.0.0", "--client-key", keys["reviewer"], "--agentgateway-bin", a.agentgateway_bin], env=env, timeout=900)
    (LOGS / "g1-k8s.log").write_text(r.stdout + "\n--- stderr\n" + r.stderr)
    g1 = latest(G1 / "results", "agentgateway-mock-"); n = counts(g1)
    rep.add("P14e", "Harness G1 proti clusterové gateway (2 repliky, Postgres DB, apiKey optional, klíč Reviewer): kontrakt Anthropic Messages API (passthrough, streaming, cache, chybová těla, Agent SDK) beze změny", "PASS" if r.returncode == 0 and n["FAIL"] == 0 and n["PASS"] >= 15 else "FAIL", {"exit": r.returncode, "counts": n, "failed": [c["id"] for c in (g1 or {}).get("checks", []) if c["status"] == "FAIL"], "wall_s": round(time.time() - t2, 1), "log": str(LOGS / "g1-k8s.log")})
    pods = json.loads(kubectl(a, "-n", NS, "get", "pods", "-l", "app=agentgateway", "-o", "json").stdout)["items"]
    rep.add("P14f", "Pody agentgateway", "INFO", {p["metadata"]["name"]: {"image": [c["image"] for c in p["spec"]["containers"]], "restarts": [c.get("restartCount") for c in p["status"].get("containerStatuses", [])], "node_ip": ip, "bridge_ip": bridge_ip} for p in pods})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["p1-2", "p1-3", "p1-4"], default="p1-2")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--dapr-bin-dir", default=os.getenv("DAPR_BIN_DIR", ""), help="p1-3: O-2 identity potřebuje lokální Dapr (placement, scheduler, daprd)")
    ap.add_argument("--kubectl", default=os.getenv("KUBECTL", shutil.which("kubectl") or ""))
    ap.add_argument("--kind", default=os.getenv("KIND", shutil.which("kind") or ""))
    ap.add_argument("--context", default="kind-platform")
    ap.add_argument("--create-kind", action="store_true", help="postavit obraz uzlu, cluster a nahrát obrazy (docker daemon)")
    ap.add_argument("--opa-bin", default=os.getenv("OPA_BIN", shutil.which("opa") or ""))
    ap.add_argument("--agentgateway-bin", default=os.getenv("AGENTGATEWAY_BIN", shutil.which("agentgateway") or ""))
    a = ap.parse_args()
    if not (a.kubectl and a.opa_bin and a.agentgateway_bin):
        print("chybí KUBECTL, OPA_BIN nebo AGENTGATEWAY_BIN"); sys.exit(2)
    for d in (RESULTS, LOGS): d.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("anthropic_base_url",)}
    env["NO_PROXY"] = env["no_proxy"] = (env.get("NO_PROXY", "") + ",127.0.0.1,localhost").strip(",")
    rep = Report()
    if a.create_kind:
        assert a.kind, "chybí KIND"
        create_kind(a, env)
    {"p1-2": step_p1_2, "p1-3": step_p1_3, "p1-4": step_p1_4}[a.step](a, rep, env)
    out = RESULTS / f"{a.step}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": a.step, "context": a.context, "kind": sh([a.kind, "version"]).stdout.strip() if a.kind else None, "images": IMAGES}, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")
    sys.exit(0 if n["FAIL"] == 0 else 1)


if __name__ == "__main__":
    main()
