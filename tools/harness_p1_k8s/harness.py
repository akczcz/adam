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

Tvrzení (krok p1-5 – workflow, paměť, bridge v clusteru):
  P15a  OPA, Dapr placement + scheduler, aplikace zakázky (app + daprd sidecar), server paměti, mock GitHub a bridge Ready; Dapr state store = Postgres (DB dapr_state)
  P15b  Zakázka end-to-end v clusteru se schvalováním přes GitHub (mock): /schvaluji → H1, review APPROVED na head SHA → H4 → merge executor → Dokonceno;
        čtyři role přes Agent SDK uvnitř podu s tokeny z clusterového Keycloaku, paměť v clusteru, approval tokeny z clusterového OpenBao
  P15c  Durabilita: pod aplikace smazán uprostřed zakázky (čeká na H2) → nový pod obnoví workflow ze stavu v Postgresu a zakázka doběhne
  P15d  Paměť: fakta rolí v clusterovém serveru paměti jako proposed; člověk (Keycloak password grant) je vidí s include_unverified
  P15e  FinOps: budget_usage v Postgresu nese útratu klíčů role × zakázka P1-5 (requesty rolí šly přes clusterovou gateway)
  P15f  Bridge: /schvaluji od bota a cizího člověka odmítnuto, od člověka z allow-listu předáno; review cizího odmítnuta
  P15g  Pody, restarty – INFO

--step p2-1 (AKS; `p1-6` je alias – od P2-1 je konfigurace gateway a rolegen build z Gitu přes Flux, klíče role × zakázka vydává aplikace):
  P21a  Flux Ready na HEAD; ConfigMapy agentgateway-config a rolegen-build == render overlay aks z HEAD; harness dodal jen tajemství
  P21b2 Klíče role × zakázka vydala aplikace (ConfigMap agentgateway-keys + Secret), rozpočty == roles/*.yaml, gateway klíč přijala
  P21b–h jako P16b–h (zakázka end-to-end s rolemi jako Kata pody, izolace, egress, časy, paměť, FinOps podle hashů z ConfigMapy)

--step p2-2 = p2-1 + obrazy rolí (P2-2): P22a roles/<role>:<verze> v ACR, P22b pod ze šablony rolegen (jen povolené doplňky běhu), P22c obsah obrazu (bez cloud CLI)

--step p2-5 = p2-2 + eval gate a registr (P2-5): P25a eval-status.json Git == ConfigMap, ROLE_GATE v ledgeru; P25b org.role_definitions/eval_gates/agents v DB org; P25c negativní kontrola gate

--step p2-3 = p2-5 + identita (P2-3): P23a OpenBao auto-unseal (Key Vault, workload identity) přežije restart podu; P23b auth kubernetes aplikace (bez tokenu v Secretu);
  P23c SVID podu role (sidecar spire-agent, JWT-SVID → paměť); P23d SPIRE OIDC provider + registrace z rolegen

--step p1-6 (původní znění checků P16, dnes alias p2-1):
  P16a  Flux Ready; platforma (vč. mock-upstream v clusteru) Ready; OpenBao init do Secretu openbao-init + unseal; paměť na Flexible Serveru
  P16b  Zakázka end-to-end jako P15b, role běží jako pody: 4× ROLE_POD Succeeded s výsledkem, AGENT_RUN z podu (via=pod), Dokonceno
  P16c  Izolace podů rolí: uzel poolu kata, RuntimeClass kata-vm-isolation, uid 1000, bez SA tokenu, srt v podu, po běhu uklizeno
  P16d  Egress podu role: internet blokován (NetworkPolicy), gateway/paměť/aplikace průchozí
  P16e  Časy podu role: schedule (vč. scale-up poolu kata z 0), start, běh – INFO
  P16f  Paměť: fakta rolí z podů jako proposed, člověk je vidí
  P16g  FinOps: budget_usage nese útratu klíčů role × zakázka P1-6 (requesty z podů přes clusterovou gateway)
  P16h  Pody, uzly – INFO

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
ROLE_CLIENTS = ("account", "architekt", "vyvojar", "reviewer")   # modelové role P0 (klienti agent-<role> v realmu p0)
IMAGES = ["pgvector/pgvector:pg16", "clickhouse:26.8", "otel/opentelemetry-collector-contrib:0.163.2"]   # P1-3 obrazy platform/{keycloak,openbao,spire} se stavějí lokálně (infra/README.md)


class Report:
    def __init__(self): self.checks = []
    def add(self, cid, name, status, detail):
        self.checks.append({"id": cid, "name": name, "status": status, "detail": detail})
        print(f"  {dict(PASS='✅', FAIL='❌', INFO='ℹ️', SKIP='⏭️')[status]} {cid} {name}: {json.dumps(detail, ensure_ascii=False)[:420 if status != 'FAIL' else 6000]}")   # FAIL celý detail (CI log)


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
    rep.add("P13b", "Keycloak přes NodePort 30080: discovery realmu p0 (issuer = KC_HOSTNAME http://keycloak:8080, stejný zevnitř i přes NodePort), client_credentials agent-vyvojar → RS256, iss = discovery issuer, aud=memory, tenant_id=acme, agent_id spiffe; realm a klienti uložené v Postgresu (DB keycloak)", "PASS" if disc.get("issuer") and claims.get("iss") == disc.get("issuer") and tok.status_code == 200 and hdr.get("alg") == "RS256" and claims.get("aud") == "memory" and claims.get("tenant_id") == "acme" and claims.get("agent_id") == "spiffe://platform/role/vyvojar" and "p0" in realms and n_clients >= 7 else "FAIL", {"issuer": disc.get("issuer"), "token_status": tok.status_code, "token_ms": tok_ms, "claims": {k: claims.get(k) for k in ("iss", "aud", "tenant_id", "agent_id", "roles", "azp")}, "db_realms": realms, "db_clients_p0": n_clients})

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


def kc_token_ext(ip, client_id, secret=None, user=None, password=None):
    data = {"grant_type": "client_credentials"} if secret else {"grant_type": "password", "client_id": client_id, "username": user, "password": password}
    r = httpx.post(f"http://{ip}:30080/realms/p0/protocol/openid-connect/token", data=data, auth=((client_id, secret) if secret else None), timeout=15)
    assert r.status_code == 200, f"Keycloak token {client_id}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def restart_pods(a, *apps):
    """Nové pody se stejnou šablonou (smazání podů podle labelu app=…): nemění spec Deploymentu, takže se nehádá s Fluxem (SSA by `rollout restart` anotaci vrátilo)."""
    for app in apps: kubectl(a, "-n", NS, "delete", "pod", "-l", f"app={app}", "--wait=false")


def render_gateway(a, zids, patch=None, mock_upstream="http://172.18.0.1:9777/v1"):
    """ConfigMap agentgateway = base config + upstream + apiKey klíče z rolegen pro dané zakázky (hodnoty vydá harness). Vrací {zid: {role: key}}."""
    import yaml, hashlib as _h
    pol, keys = None, {}
    for zid in zids:
        out = LOGS / f"rolegen-{zid}"
        rg = sh([sys.executable, str(T / "rolegen/rolegen.py"), "--roles", str(ROOT / "knowledge/organization/roles"), "--out", str(out), "--tenant", "acme", "--zakazka", zid]); assert rg.returncode == 0, rg.stderr
        p = yaml.safe_load((out / f"agentgateway/apikeys-acme-{zid}.yaml").read_text())["policies"]["apiKey"]
        keys[zid] = {}
        for k in list(p["keys"]):
            role = k["metadata"]["role"]
            if role == "sre": p["keys"].remove(k); continue
            val = f"sk-gw-{zid}-{role}-{_h.sha256(os.urandom(16)).hexdigest()[:20]}"; keys[zid][role] = val
            k["keyHash"] = "sha256:" + _h.sha256(val.encode()).hexdigest()
            for b in k["budgets"]:
                if patch and (zid, role, b["name"]) in patch: b["limit"]["amount"] = patch[(zid, role, b["name"])]
        if pol is None: pol = p
        else: pol["keys"] += p["keys"]
    pol["mode"] = "optional"
    base_cm = next(d for d in yaml.safe_load_all((INFRA / "k8s/base/agentgateway/agentgateway.yaml").read_text()) if d and d.get("kind") == "ConfigMap")
    cfg = yaml.safe_load(base_cm["data"]["config.yaml"])
    cfg["llm"]["models"][0]["params"]["baseUrl"] = mock_upstream
    cfg["llm"]["policies"] = {"apiKey": pol}
    cfg_path = LOGS / f"agentgateway-{'-'.join(zids)}.yaml"; cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    cm = kubectl(a, "create", "configmap", "agentgateway-config", "-n", NS, f"--from-file=config.yaml={cfg_path}", "--dry-run=client", "-o", "yaml").stdout
    subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=cm, text=True, capture_output=True)
    restart_pods(a, "agentgateway")   # ne `rollout restart`: Flux by anotaci restartedAt vrátil a Deployment znovu přerolloval (AKS 2026-10-25)
    assert kubectl(a, "-n", NS, "rollout", "status", "deploy/agentgateway", "--timeout=180s", timeout=200).returncode == 0
    return keys


def step_p1_5(a, rep, env):
    import psycopg, jwt
    O2 = T / "harness_p0_o2"; G1 = T / "harness_gateway_g1"; M1 = T / "harness_memory_m1"
    o2 = __import__("importlib.util").util.spec_from_file_location("o2h", O2 / "harness.py"); o2m = __import__("importlib.util").util.module_from_spec(o2); o2.loader.exec_module(o2m)
    m1 = __import__("importlib.util").util.spec_from_file_location("m1h", M1 / "harness.py"); m1m = __import__("importlib.util").util.module_from_spec(m1); m1.loader.exec_module(m1m)
    ip = node_ip(a); APP = f"http://{ip}:30810"; MEM = f"http://{ip}:30990"; GHM = f"http://{ip}:30801/repos/akczcz/adam"; GHS = f"http://{ip}:30801/_debug/state"; BAO = f"http://{ip}:30200"
    bridge_ip = subprocess.run(["docker", "network", "inspect", "kind", "-f", "{{range .IPAM.Config}}{{.Gateway}}{{end}}"], capture_output=True, text=True).stdout.strip() or "172.18.0.1"
    t_all = time.time()
    # mock model na hostiteli pro clusterovou gateway (port 9777 musí být volný – po přerušeném běhu zabít starý mock_upstream.py)
    import socket as _s
    with _s.socket() as _sock: assert _sock.connect_ex(("127.0.0.1", 9777)) != 0, "port 9777 obsazen (starý mock_upstream.py?) – pkill -f mock_upstream.py"
    mock = subprocess.Popen([str(G1 / ".venv/bin/python"), str(G1 / "mock_upstream.py")], env=env | {"MOCK_HOST": "0.0.0.0", "MOCK_PORT": "9777", "MOCK_EVENT_DELAY": "0.02"}, stdout=open(LOGS / "mock-p15.log", "wb"), stderr=subprocess.STDOUT, start_new_session=True)
    try:
        assert wait_http("http://127.0.0.1:9777/health", 30), "mock nenaběhl"
        # OpenBao: unseal (klíče z P1-3), transit + token aplikace
        init_f = LOGS / "openbao-init.json"; assert init_f.exists(), "chybí logs/openbao-init.json – nejdřív --step p1-3"
        init = json.loads(init_f.read_text())
        if httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json().get("sealed"): httpx.post(f"{BAO}/v1/sys/unseal", json={"key": init["keys_base64"][0]}, timeout=30)
        o2m.BAO = BAO; bao_app = o2m.bao_setup(init["root_token"], LOGS / "openbao-audit-k8s.log")
        # paměť: schéma M1 + seed v clusterovém Postgresu, role memory_app s heslem
        su = f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/memory"
        with psycopg.connect(su, autocommit=True, connect_timeout=10) as c:
            c.execute(m1m.SCHEMA); c.execute("ALTER ROLE memory_app PASSWORD 'memory_app'")
            txt = "ACME konvence: každý endpoint má test a vrací JSON; splatnost faktur 30 dní."
            c.execute("""INSERT INTO memory_records (id,tenant_id,scope,type,content,content_hash,sources,created_by,created_at,verification,confidence,valid_from,status,sensitivity,pipeline_version,embedding)
                         VALUES ('seed-acme','acme','zakaznik','fakt',%s,'h','[{"ref":"doc://acme/konvence","kind":"document"}]','{"sub":"seed"}',now(),'{"method":"human","by":"adam"}',0.95,now(),'approved','internal','seed',%s::vector)""", (txt, m1m._embed_sql(txt)))
        # nejdřív base manifesty (Secret s placeholdery, base ConfigMap gateway), pak hodnoty z harnessu – apply po renderu by je přepsal (gateway hot-reloaduje config)
        r = kubectl(a, "apply", "-k", str(INFRA / "k8s/overlays/kind")); assert r.returncode == 0, r.stderr
        keys = render_gateway(a, ["P1-5"], mock_upstream=f"http://{bridge_ip}:9777/v1")   # gateway klíče role × zakázka + restart gateway
        rb = LOGS / "rolegen-P1-5"
        cm1 = subprocess.run([a.kubectl, "--context", a.context, "-n", NS, "create", "configmap", "rolegen-build", *[f"--from-file={f}" for f in (rb / "agent_sdk").glob("*.json")], f"--from-file=roles.json={rb / 'registry/roles.json'}", "--dry-run=client", "-o", "yaml"], capture_output=True, text=True).stdout
        subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=cm1, text=True, capture_output=True)
        sec = subprocess.run([a.kubectl, "--context", a.context, "-n", NS, "create", "secret", "generic", "zakazka-secrets",
                              "--from-literal=P0_ROLE_CLIENT_SECRETS=" + json.dumps({r: f"p0-{r}-secret" for r in ROLE_CLIENTS}), f"--from-literal=P0_BAO_TOKEN={bao_app}",
                              "--from-literal=P0_ROLE_KEYS=" + json.dumps({"*": keys["P1-5"]}), "--from-literal=P0_API_KEY=sk-ant-harness-mock", "--from-literal=BRIDGE_WEBHOOK_SECRET=bridge-webhook-secret",
                              "--dry-run=client", "-o", "yaml"], capture_output=True, text=True).stdout
        subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=sec, text=True, capture_output=True)
        kubectl(a, "-n", NS, "rollout", "restart", "deploy/zakazka", "deploy/memory", "deploy/bridge", "deploy/mock-github")
        t0 = time.time()
        rolls = {k: kubectl(a, "-n", NS, "rollout", "status", k, "--timeout=420s", timeout=440).returncode == 0 for k in ("deployment/keycloak", "deployment/opa", "statefulset/placement", "statefulset/scheduler", "deployment/memory", "deployment/mock-github", "deployment/bridge", "deployment/zakazka")}
        with psycopg.connect(f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/dapr_state", autocommit=True, connect_timeout=10) as c:
            dapr_tables = sorted(r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall())
        health = {"app": httpx.get(f"{APP}/health", timeout=10).status_code, "memory": httpx.get(f"{MEM}/health", timeout=10).status_code, "mock_github": httpx.get(f"http://{ip}:30801/health", timeout=10).status_code, "bridge": httpx.get(f"http://{ip}:30802/health", timeout=10).status_code}
        rep.add("P15a", "OPA, Dapr placement + scheduler, aplikace zakázky (app + daprd sidecar, komponenty z ConfigMapy), server paměti, mock GitHub a bridge Ready; Dapr state store Postgres (DB dapr_state) má tabulky", "PASS" if all(rolls.values()) and all(v == 200 for v in health.values()) and dapr_tables else "FAIL", {"rollouts": rolls, "health": health, "dapr_state_tables": dapr_tables, "rollout_s": round(time.time() - t0, 1)})

        def led(): return httpx.get(f"{APP}/_debug/ledger", timeout=15).json()
        def hash_of(zid, typ):
            for e in reversed(led()):
                if e.get("kind") == "HANDOFF" and e.get("zakazka") == zid and str(e.get("artifact", "")).startswith(typ): return e["hash"]
        def wait_handoff(zid, typ, timeout=300):
            t = time.time()
            while time.time() - t < timeout:
                h = hash_of(zid, typ)
                if h: return h
                time.sleep(1)
        def pub(zid, kind, timeout=300):
            t = time.time()
            while time.time() - t < timeout:
                e = next((e for e in led() if e["kind"] == "PUBLISHED" and e["zakazka"] == zid and e.get("publish_kind") == kind), None)
                if e: return e
                time.sleep(1)
        def status(zid):
            r = httpx.get(f"{APP}/zakazky/{zid}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
        def wait_status(zid, want, timeout=120):
            t = time.time()
            while time.time() - t < timeout:
                st = status(zid)
                if st.get("status") in want: return st
                time.sleep(1)
            return status(zid)
        def approve(zid, bod, hh): httpx.post(f"{APP}/zakazky/{zid}/approve/{bod}", json={"by": "adam", "by_kind": "human", "artifact_hash": hh, "exp_s": 86400}, timeout=15)
        def gh_post(path, payload, user): return httpx.post(f"{GHM}{path}", json=payload, headers={"X-Mock-User": user}, timeout=15).json()
        def bridge_log():
            r = kubectl(a, "-n", NS, "exec", "deploy/bridge", "--", "cat", "/data/bridge.jsonl"); return [json.loads(l) for l in r.stdout.splitlines() if l.strip()]

        # P15b – zakázka přes GitHub HITL v clusteru
        run_tag = time.strftime("%H%M%S"); zid = f"P15-{run_tag}-1"; t1 = time.time()   # unikátní: stav workflow (Postgres) i ledger (PVC) přežívají běhy
        httpx.post(f"{APP}/zakazky", json={"id": zid, "poptavka": f"Přidej do repa platformy soubor zakazky/{zid}/NOTES.md s poznámkou, že zakázka proběhla v Kubernetes.", "hitl_timeout_s": 3600}, timeout=15)
        issue = pub(zid, "issue"); assert issue, "issue nebylo publikováno (ledger app)"
        gh_post(f"/issues/{issue['number']}/comments", {"body": "/schvaluji"}, "platform-bot"); gh_post(f"/issues/{issue['number']}/comments", {"body": "/schvaluji"}, "stranger")
        time.sleep(5); adr_early = hash_of(zid, "adr://")
        gh_post(f"/issues/{issue['number']}/comments", {"body": "/schvaluji – zadání odpovídá"}, "adam")
        adr = wait_handoff(zid, "adr://", 240); assert adr, "Architekt nedodal ADR"
        approve(zid, "H2", adr)
        pr = pub(zid, "pull_request", 400); assert pr, "PR nebyl publikován"
        wait_handoff(zid, "review://", 240)
        gh_post(f"/pulls/{pr['number']}/reviews", {"event": "APPROVE", "commit_id": pr["head_sha"]}, "stranger")
        gh_post(f"/pulls/{pr['number']}/reviews", {"event": "APPROVE", "commit_id": pr["head_sha"], "body": "LGTM"}, "adam")
        t = time.time(); merged = False
        while time.time() - t < 120 and not merged:
            merged = httpx.get(GHS, timeout=10).json()["pulls"][str(pr["number"])]["merged"]; time.sleep(1)
        approve(zid, "H5", hash_of(zid, "pr://")); st = wait_status(zid, {"COMPLETED", "FAILED"}, 120)
        L = led(); runs = {e["role"]: e for e in L if e["kind"] == "AGENT_RUN" and e["zakazka"] == zid}
        mem_calls = [e for e in L if e["kind"] == "TOOL" and e["zakazka"] == zid and e["tool"] in ("search_memory", "create_memory")]
        signs = [e for e in L if e["kind"] == "SIGN" and e["zakazka"] == zid]
        rep.add("P15b", "Zakázka v clusteru end-to-end přes GitHub HITL (mock GitHub v clusteru): issue → /schvaluji → ADR → H2 → PR → review APPROVED na head SHA → merge executor → H5 → Dokonceno; 4 role přes Agent SDK v podu s tokeny z clusterového Keycloaku, paměť v clusteru (200), approval tokeny z clusterového OpenBao", "PASS" if (st.get("output") or {}).get("stav") == "Dokonceno" and merged and not adr_early and set(runs) == set(ROLE_CLIENTS) and not any(r.get("error") for r in runs.values()) and mem_calls and all(c.get("http") == 200 for c in mem_calls) and signs and all(s["backend"] == "openbao-transit" for s in signs) else "FAIL", {"output": st.get("output"), "merged_in_mock_github": merged, "issue": issue.get("number"), "pr": pr.get("number"), "roles": {k: {"tools": r.get("tool_uses"), "error": r.get("error"), "cost_usd": r.get("cost_usd")} for k, r in runs.items()}, "memory_calls_200": sum(1 for c in mem_calls if c.get("http") == 200), "signs": len(signs), "wall_s": round(time.time() - t1, 1)})

        # P15c – durabilita: smazat pod uprostřed (čeká na H2)
        zid2 = f"P15-{run_tag}-2"; t2 = time.time()
        httpx.post(f"{APP}/zakazky", json={"id": zid2, "poptavka": "Přidej endpoint /version do služby ACME (test durability).", "hitl_timeout_s": 3600}, timeout=15)
        issue2 = pub(zid2, "issue"); assert issue2, "issue 2 nebylo publikováno"
        gh_post(f"/issues/{issue2['number']}/comments", {"body": "/schvaluji"}, "adam")
        adr2 = wait_handoff(zid2, "adr://", 240); assert adr2, "ADR 2 nevzniklo"
        old_pod = kubectl(a, "-n", NS, "get", "pods", "-l", "app=zakazka", "-o", "jsonpath={.items[0].metadata.name}").stdout.strip()
        kubectl(a, "-n", NS, "delete", "pod", old_pod, "--wait=true", timeout=120)
        assert kubectl(a, "-n", NS, "rollout", "status", "deploy/zakazka", "--timeout=300s", timeout=320).returncode == 0
        new_pod = kubectl(a, "-n", NS, "get", "pods", "-l", "app=zakazka", "-o", "jsonpath={.items[0].metadata.name}").stdout.strip()
        for _ in range(30):
            try:
                if httpx.get(f"{APP}/health", timeout=3).status_code == 200: break
            except Exception: pass
            time.sleep(2)
        st_after = status(zid2)
        approve(zid2, "H2", adr2)
        pr2 = pub(zid2, "pull_request", 400)
        if pr2:
            wait_handoff(zid2, "review://", 240)
            gh_post(f"/pulls/{pr2['number']}/reviews", {"event": "APPROVE", "commit_id": pr2["head_sha"]}, "adam")
            t = time.time()
            while time.time() - t < 120 and not httpx.get(GHS, timeout=10).json()["pulls"][str(pr2["number"])]["merged"]: time.sleep(1)
            approve(zid2, "H5", hash_of(zid2, "pr://"))
        st2 = wait_status(zid2, {"COMPLETED", "FAILED"}, 120)
        L = led(); runs2 = {e["role"]: e for e in L if e["kind"] == "AGENT_RUN" and e["zakazka"] == zid2}
        rep.add("P15c", "Durabilita workflow: pod aplikace smazán, když zakázka čeká na H2 (po ADR) → nový pod (jiné jméno) obnoví instanci ze stavu v Postgresu (Dapr Workflow replay), schválení H2 doručeno novému podu, Vývojář a Reviewer běží v novém podu, zakázka Dokonceno", "PASS" if old_pod != new_pod and st_after.get("status") in ("RUNNING", "SUSPENDED", "PENDING") and (st2.get("output") or {}).get("stav") == "Dokonceno" and {"vyvojar", "reviewer"} <= set(runs2) else "FAIL", {"old_pod": old_pod, "new_pod": new_pod, "status_after_restart": st_after.get("status"), "output": st2.get("output"), "roles_after": sorted(runs2), "wall_s": round(time.time() - t2, 1)})

        # P15d – paměť: fakta rolí jako proposed, člověk vidí
        human = kc_token_ext(ip, "harness-human", user="adam", password="adam")
        unv = httpx.post(f"{MEM}/tools/search_memory", json={"query": "ACME endpoint", "include_unverified": True, "limit": 20}, headers={"Authorization": f"Bearer {human}"}, timeout=15)
        recs = unv.json().get("records", []) if unv.status_code == 200 else []
        proposed = [r for r in recs if r.get("status") == "proposed" or r.get("unverified")]
        rep.add("P15d", "Paměť v clusteru: zápisy rolí (Keycloak service-account tokeny, aud=memory, iss keycloak:8080) uložené jako proposed; člověk (password grant, token z NodePortu se stejným iss) je vidí s include_unverified; seed approved", "PASS" if unv.status_code == 200 and recs and proposed else "FAIL", {"http": unv.status_code, "records": len(recs), "proposed": len(proposed), "iss": jwt.decode(human, options={"verify_signature": False}).get("iss")})

        # P15e – FinOps z Postgresu gateway
        import hashlib as _h
        with psycopg.connect(f"postgresql://postgres:{PG_PASSWORD}@127.0.0.1:{PG_PORT}/agentgateway", autocommit=True, connect_timeout=10) as c:
            rows = c.execute("SELECT budget_id, used_amount FROM budget_usage").fetchall()
        spend = {}
        for role, val in keys["P1-5"].items():
            h = _h.sha256(val.encode()).hexdigest()
            spend[role] = next((used / 1e9 for bid, used in rows if h in bid and bid.endswith("24h-block")), 0.0)
        rep.add("P15e", "FinOps v clusteru: requesty rolí šly přes clusterovou gateway s klíči role × zakázka P1-5 → budget_usage v Postgresu nese útratu každé role (zdroj pravdy pro cenu zakázky místo logu na disku)", "PASS" if all(v > 0 for v in spend.values()) else "FAIL", {"spend_usd_by_role": spend, "total_usd": round(sum(spend.values()), 6)})

        # P15f – bridge
        bl = bridge_log()
        rej = [e for e in bl if e["kind"] == "REJECTED"]; fwd = [e for e in bl if e["kind"] == "APPROVAL_FORWARDED"]
        rep.add("P15f", "Bridge v clusteru jako PEP: /schvaluji od bota a cizího člověka odmítnuto, review cizího odmítnuta; schválení od člověka z allow-listu předáno pro H1 i H4 (poll i webhook v clusteru)", "PASS" if {e["by"] for e in rej if e.get("bod") == "H1"} >= {"platform-bot", "stranger"} and any(e.get("bod") == "H4" for e in rej) and {e["bod"] for e in fwd} >= {"H1", "H4"} else "FAIL", {"rejected": [(e.get("bod"), e.get("by"), e.get("reason")) for e in rej][:6], "forwarded": [(e["bod"], e.get("by")) for e in fwd][:6]})
        pods = json.loads(kubectl(a, "-n", NS, "get", "pods", "-o", "json").stdout)["items"]
        rep.add("P15g", "Pody P1-5", "INFO", {p["metadata"]["name"]: {"image": [c["image"].split("/")[-1] for c in p["spec"]["containers"]], "restarts": [c.get("restartCount") for c in p["status"].get("containerStatuses", [])]} for p in pods if p["metadata"]["name"].split("-")[0] in ("zakazka", "memory", "bridge", "mock", "opa", "placement", "scheduler")} | {"wall_s": round(time.time() - t_all, 1)})
    finally:
        mock.terminate()
        try: mock.wait(10)
        except Exception: mock.kill()


class PortForward:
    """kubectl port-forward na Service (AKS bez NodePortů); při pádu (restart podu) se znovu spustí."""
    def __init__(self, a, svc, local, remote, ns=NS):
        self.a, self.svc, self.local, self.remote, self.ns, self.p = a, svc, local, remote, ns, None
        self.start()
    def start(self):
        if self.p and self.p.poll() is None: self.p.terminate()
        self.p = subprocess.Popen([self.a.kubectl, "--context", self.a.context, "-n", self.ns, "port-forward", f"svc/{self.svc}", f"{self.local}:{self.remote}"], stdout=subprocess.DEVNULL, stderr=open(LOGS / f"pf-{self.svc}.log", "ab"))
        import socket as _s
        for _ in range(60):
            with _s.socket() as so:
                if so.connect_ex(("127.0.0.1", self.local)) == 0: return True
            time.sleep(0.5)
        return False
    def stop(self):
        if self.p: self.p.terminate()


def step_p2_1(a, rep, env, images=False, registry=False, identity=False):
    """P2-1 na AKS (nahrazuje p1-6): konfigurace gateway a rolegen build z Gitu přes Flux (infra/k8s/rolegen), klíče role × zakázka vydává aplikace;
    harness dodává jen tajemství. Checky P21a–h = P16a–h + ověření původu konfigurace a vydaných klíčů."""
    import psycopg, jwt, hashlib as _h, base64 as _b
    O2 = T / "harness_p0_o2"; M1 = T / "harness_memory_m1"
    o2 = __import__("importlib.util").util.spec_from_file_location("o2h", O2 / "harness.py"); o2m = __import__("importlib.util").util.module_from_spec(o2); o2.loader.exec_module(o2m)
    m1 = __import__("importlib.util").util.spec_from_file_location("m1h", M1 / "harness.py"); m1m = __import__("importlib.util").util.module_from_spec(m1); m1.loader.exec_module(m1m)
    RNS = "platform-roles"; t_all = time.time()
    def kj(*args):
        r = kubectl(a, *args, "-o", "json"); return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
    def secret(name, key, ns=NS):
        v = kubectl(a, "-n", ns, "get", "secret", name, "-o", f"jsonpath={{.data.{key}}}").stdout.strip(); return _b.b64decode(v).decode() if v else None
    # Flux: obě kustomizations Ready a mock-upstream (nový objekt overlay) existuje
    want_sha = os.environ.get("GITHUB_SHA") or sh(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    t0 = time.time(); flux = {}
    while time.time() - t0 < 600:
        ks = kj("-n", "flux-system", "get", "kustomizations").get("items", [])
        flux = {k["metadata"]["name"]: next((c["status"] for c in k.get("status", {}).get("conditions", []) if c["type"] == "Ready"), "?") for k in ks}
        revs = [(k.get("status", {}).get("lastAppliedRevision") or "") for k in ks]
        if flux and all(v == "True" for v in flux.values()) and all(r.endswith(want_sha) for r in revs) and kubectl(a, "-n", NS, "get", "deploy/mock-upstream").returncode == 0 and kubectl(a, "get", "ns", RNS).returncode == 0: break
        time.sleep(10)   # Flux sync 120 s + rollout po změně manifestů; měříme vždy stav z aktuálního commitu
    flux_rev = {k["metadata"]["name"]: (k.get("status", {}).get("lastAppliedRevision") or "")[:60] for k in kj("-n", "flux-system", "get", "kustomizations").get("items", [])}
    # OpenBao: init (klíče do Secretu openbao-init – runner CI nemá trvalé logs/) + unseal + transit/policy/token aplikace
    pf_bao = PortForward(a, "openbao", 18200, 8200); BAO = "http://127.0.0.1:18200"
    seal0 = httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json(); seal_type = seal0.get("type")
    st = httpx.get(f"{BAO}/v1/sys/init", timeout=10).json()
    if not st.get("initialized"):
        body = {"recovery_shares": 1, "recovery_threshold": 1} if seal_type and seal_type != "shamir" else {"secret_shares": 1, "secret_threshold": 1}   # auto-unseal (P2-3): recovery klíče místo unseal klíčů
        init = httpx.post(f"{BAO}/v1/sys/init", json=body, timeout=30).json(); assert "root_token" in init, f"init selhal: {init}"
        sec = subprocess.run([a.kubectl, "--context", a.context, "-n", NS, "create", "secret", "generic", "openbao-init", f"--from-literal=init.json={json.dumps(init)}", "--dry-run=client", "-o", "yaml"], capture_output=True, text=True).stdout
        subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=sec, text=True, capture_output=True)
    init_s = secret("openbao-init", "init\\.json"); assert init_s, "OpenBao je inicializovaný, ale Secret openbao-init chybí – smazat PVC data-openbao-0 a pod openbao-0, nebo Secret doplnit"
    init = json.loads(init_s); bao_migrated = False
    seal = httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json()
    if seal.get("sealed"):
        if seal.get("type") not in (None, "shamir") and init.get("keys_base64"):   # storage z shamir, config už s azurekeyvault → migrace (klíče se stanou recovery klíči)
            httpx.post(f"{BAO}/v1/sys/unseal", json={"key": init["keys_base64"][0], "migrate": True}, timeout=60); bao_migrated = True
        elif init.get("keys_base64"): httpx.post(f"{BAO}/v1/sys/unseal", json={"key": init["keys_base64"][0]}, timeout=30)
        for _ in range(30):
            if not httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json().get("sealed"): break
            time.sleep(2)
    seal = httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json()
    o2m.BAO = BAO; bao_app = o2m.bao_setup(init["root_token"], LOGS / "openbao-audit-aks.log")
    # P2-3: auth metoda kubernetes pro aplikaci (SA zakazka) – žádný token OpenBao v Secretu; TokenReview vlastním SA tokenem OpenBao (auth-delegator)
    Hb = {"X-Vault-Token": init["root_token"]}
    if "kubernetes/" not in httpx.get(f"{BAO}/v1/sys/auth", headers=Hb, timeout=10).json(): httpx.post(f"{BAO}/v1/sys/auth/kubernetes", json={"type": "kubernetes"}, headers=Hb, timeout=10)
    httpx.post(f"{BAO}/v1/auth/kubernetes/config", json={"kubernetes_host": "https://kubernetes.default.svc:443"}, headers=Hb, timeout=10)
    httpx.post(f"{BAO}/v1/auth/kubernetes/role/zakazka", json={"bound_service_account_names": ["zakazka"], "bound_service_account_namespaces": [NS], "token_policies": ["approval-signer"], "token_ttl": "1h", "token_max_ttl": "4h"}, headers=Hb, timeout=10)
    # Postgres = Flexible Server: admin `platform`, heslo ze Secretu postgres-auth (Flux substitute), TLS; z runneru přímo (pravidlo Allow Azure services),
    # jinak přes socat pod + port-forward
    pg_host = kubectl(a, "-n", NS, "get", "svc", "postgres", "-o", "jsonpath={.spec.externalName}").stdout.strip(); pg_pw = secret("postgres-auth", "POSTGRES_PASSWORD")
    assert pg_host and pg_pw, "chybí svc postgres (ExternalName) nebo Secret postgres-auth"
    pg_via = "direct"; pf_pg = None
    def dsn(db, host=pg_host, port=5432): return f"postgresql://platform:{pg_pw}@{host}:{port}/{db}?sslmode=require"
    try:
        psycopg.connect(dsn("memory"), connect_timeout=10).close()
    except Exception as e:
        pg_via = f"socat-forward ({type(e).__name__})"
        kubectl(a, "-n", NS, "delete", "pod", "pgfwd", "--ignore-not-found", "--wait=true")
        assert a.acr, "přímé spojení na Flexible Server selhalo a chybí --acr pro socat pod"
        kubectl(a, "-n", NS, "run", "pgfwd", f"--image={a.acr}/sandbox-s1:p1", "--restart=Never", "--", "socat", "TCP-LISTEN:5432,fork,reuseaddr", f"TCP:{pg_host}:5432")
        kubectl(a, "-n", NS, "wait", "--for=condition=Ready", "pod/pgfwd", "--timeout=120s", timeout=130)
        pf_pg = subprocess.Popen([a.kubectl, "--context", a.context, "-n", NS, "port-forward", "pod/pgfwd", "15432:5432"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(3)
        dsn = lambda db, host="127.0.0.1", port=15432: f"postgresql://platform:{pg_pw}@{host}:{port}/{db}?sslmode=require"
    with psycopg.connect(dsn("memory"), autocommit=True, connect_timeout=10) as c:
        c.execute(m1m.SCHEMA); c.execute("ALTER ROLE memory_app PASSWORD 'memory_app'")
        txt = "ACME konvence: každý endpoint má test a vrací JSON; splatnost faktur 30 dní."
        c.execute("""INSERT INTO memory_records (id,tenant_id,scope,type,content,content_hash,sources,created_by,created_at,verification,confidence,valid_from,status,sensitivity,pipeline_version,embedding)
                     VALUES ('seed-acme','acme','zakaznik','fakt',%s,'h','[{"ref":"doc://acme/konvence","kind":"document"}]','{"sub":"seed"}',now(),'{"method":"human","by":"adam"}',0.95,now(),'approved','internal','seed',%s::vector)
                     ON CONFLICT (id) DO NOTHING""", (txt, m1m._embed_sql(txt)))
        pg_ver = c.execute("SHOW server_version").fetchone()[0]
    # P2-1: konfigurace gateway (agentgateway-config) a rolegen build (rolegen-build) jsou z Gitu přes Flux – harness je NErenderuje, jen ověří shodu s renderem HEAD
    import yaml as _y
    rendered = [d for d in _y.safe_load_all(sh([a.kubectl, "kustomize", str(INFRA / "k8s/overlays/aks")]).stdout) if d]
    def cm_data(name, docs): return next((d.get("data") or {} for d in docs if d.get("kind") == "ConfigMap" and d["metadata"]["name"] == name), None)
    cfg_git = {n: cm_data(n, rendered) for n in ("rolegen-build", "agentgateway-config")}
    cfg_cluster = {n: (kj("-n", NS, "get", "configmap", n).get("data") or None) for n in ("rolegen-build", "agentgateway-config")}
    config_from_git = {n: cfg_git[n] is not None and cfg_git[n] == cfg_cluster[n] for n in cfg_git}
    import difflib
    config_diff = {}
    for n in cfg_git:
        g, c = cfg_git[n] or {}, cfg_cluster[n] or {}
        for k in sorted(set(g) | set(c)):
            if g.get(k) != c.get(k):
                d = [l for l in difflib.unified_diff((g.get(k) or "").splitlines(), (c.get(k) or "").splitlines(), "git", "cluster", lineterm="", n=0) if not l.startswith(("---", "+++"))]
                config_diff[f"{n}/{k}"] = d[:6] if d else "jen whitespace/konec řádku"
    gw_cfg = _y.safe_load((cfg_cluster["agentgateway-config"] or {}).get("config.yaml") or "{}")
    gw_env = {e["name"]: e.get("value") for e in (kj("-n", NS, "get", "deploy", "agentgateway").get("spec", {}).get("template", {}).get("spec", {}).get("containers") or [{}])[0].get("env", [])}
    sec = subprocess.run([a.kubectl, "--context", a.context, "-n", NS, "create", "secret", "generic", "zakazka-secrets",
                          "--from-literal=P0_ROLE_CLIENT_SECRETS=" + json.dumps({r: f"p0-{r}-secret" for r in ROLE_CLIENTS}), *([] if identity else [f"--from-literal=P0_BAO_TOKEN={bao_app}"]),   # P2-3: token OpenBao si aplikace bere auth kubernetes
                          "--from-literal=P0_API_KEY=sk-ant-harness-mock", "--from-literal=BRIDGE_WEBHOOK_SECRET=bridge-webhook-secret",   # bez P0_ROLE_KEYS – klíče vydá aplikace (gateway_keys.py)
                          "--dry-run=client", "-o", "yaml"], capture_output=True, text=True).stdout
    # P2-3: registrace SPIRE z rolegen (ConfigMap rolegen-build/spire-entries.json): alias uzlu per role (sidecar agent podu) + workload entry
    spire_applied = []
    if identity:
        import yaml as _ys
        ents = json.loads((kj("-n", NS, "get", "configmap", "rolegen-build").get("data") or {}).get("spire-entries.json") or "[]")
        for e in ents:
            show = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", "spire-server", "entry", "show", "-spiffeID", e["spiffe_id"], "-socketPath", "/tmp/spire-server/private/api.sock").stdout
            if e["spiffe_id"] in show: continue
            args = ["spire-server", "entry", "create", "-socketPath", "/tmp/spire-server/private/api.sock", "-spiffeID", e["spiffe_id"]] + (["-node"] if e.get("node") else ["-parentID", e["parent_id"]])
            for sel in e["selectors"]: args += ["-selector", sel]
            if e.get("x509_svid_ttl"): args += ["-x509SVIDTTL", str(e["x509_svid_ttl"])]
            if e.get("jwt_svid_ttl"): args += ["-jwtSVIDTTL", str(e["jwt_svid_ttl"])]
            r = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", *args); spire_applied.append((e["spiffe_id"], r.returncode, (r.stderr or r.stdout)[-120:]))
    subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=sec, text=True, capture_output=True)
    restart_pods(a, "zakazka", "memory", "bridge", "mock-github"); time.sleep(5)
    t0 = time.time()
    rolls = {k: kubectl(a, "-n", NS, "rollout", "status", k, "--timeout=600s", timeout=620).returncode == 0 for k in ("deployment/keycloak", "deployment/opa", "statefulset/placement", "statefulset/scheduler", "deployment/agentgateway", "deployment/mock-upstream", "deployment/memory", "deployment/mock-github", "deployment/bridge", "deployment/zakazka")}
    for n, p in (("zakazka", 8010), ("memory", 9900), ("mock-github", 9801), ("bridge", 9802)):
        kubectl(a, "-n", NS, "wait", "--for=condition=Ready", "pod", "-l", f"app={n}", "--timeout=300s", timeout=320)
    pfs = {n: PortForward(a, n, lp, rp) for n, lp, rp in (("zakazka", 18010, 8010), ("memory", 19900, 9900), ("mock-github", 19801, 9801), ("bridge", 19802, 9802), ("keycloak", 18080, 8080))}
    APP, MEM, GHM, GHS, KC = "http://127.0.0.1:18010", "http://127.0.0.1:19900", "http://127.0.0.1:19801/repos/akczcz/adam", "http://127.0.0.1:19801/_debug/state", "http://127.0.0.1:18080"
    def http(method, url, **kw):
        for i in range(12):
            try: return httpx.request(method, url, **kw)
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError):
                if i == 11: raise
                time.sleep(5)
                for pf in pfs.values(): pf.start()
    try:
        health = {n: http("GET", f"http://127.0.0.1:{p}/health", timeout=10).status_code for n, p in (("app", 18010), ("memory", 19900), ("mock_github", 19801), ("bridge", 19802))}
        with psycopg.connect(dsn("dapr_state"), autocommit=True, connect_timeout=10) as c:
            dapr_tables = sorted(r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall())
        gw_ok = all(config_from_git.values()) and gw_cfg.get("llm", {}).get("models", [{}])[0].get("params", {}).get("baseUrl") == "$LLM_UPSTREAM_URL" and "apiKey" in (gw_cfg.get("llm", {}).get("policies") or {}) and "apikeys-template.yaml" in (cfg_cluster["rolegen-build"] or {}) and any(k.startswith("srt-") for k in (cfg_cluster["rolegen-build"] or {}))
        rep.add("P21a", "AKS: Flux kustomizations platform + roles Ready na HEAD; ConfigMapy agentgateway-config a rolegen-build v clusteru == render infra/k8s/overlays/aks z HEAD (konfigurace z Gitu, harness nic nerenderuje); gateway má apiKey policy a upstream z env LLM_UPSTREAM_URL; rolegen-build nese apikeys-template a srt; platforma vč. mock-upstream Ready; OpenBao init/unseal/transit; schéma paměti M1 na Flexible Serveru; harness dodal jen tajemství", "PASS" if all(v == "True" for v in flux.values()) and gw_ok and all(rolls.values()) and all(v == 200 for v in health.values()) and dapr_tables else "FAIL", {"flux": flux, "flux_rev": flux_rev, "config_from_git": config_from_git, "config_diff": config_diff, "gateway_upstream_env": gw_env.get("LLM_UPSTREAM_URL"), "rolegen_build_keys": sorted(cfg_cluster["rolegen-build"] or {}), "rollouts": rolls, "health": health, "pg": {"host": pg_host, "version": pg_ver, "via": pg_via}, "dapr_state_tables": dapr_tables, "rollout_s": round(time.time() - t0, 1)})

        def led(): return http("GET", f"{APP}/_debug/ledger", timeout=20).json()
        def hash_of(zid, typ):
            for e in reversed(led()):
                if e.get("kind") == "HANDOFF" and e.get("zakazka") == zid and str(e.get("artifact", "")).startswith(typ): return e["hash"]
        def wait_handoff(zid, typ, timeout=900):
            t = time.time()
            while time.time() - t < timeout:
                h = hash_of(zid, typ)
                if h: return h
                time.sleep(3)
        def pub(zid, kind, timeout=1200):
            t = time.time()
            while time.time() - t < timeout:
                e = next((e for e in led() if e["kind"] == "PUBLISHED" and e["zakazka"] == zid and e.get("publish_kind") == kind), None)
                if e: return e
                time.sleep(3)
        def status(zid):
            r = http("GET", f"{APP}/zakazky/{zid}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
        def wait_status(zid, want, timeout=300):
            t = time.time()
            while time.time() - t < timeout:
                st = status(zid)
                if st.get("status") in want: return st
                time.sleep(2)
            return status(zid)
        def approve(zid, bod, hh): http("POST", f"{APP}/zakazky/{zid}/approve/{bod}", json={"by": "adam", "by_kind": "human", "artifact_hash": hh, "exp_s": 86400}, timeout=15)
        def gh_post(path, payload, user): return http("POST", f"{GHM}{path}", json=payload, headers={"X-Mock-User": user}, timeout=15).json()

        # P21b – zakázka end-to-end, role jako pody (první pod čeká na scale-up poolu kata z 0 → dlouhé timeouty)
        run_tag = time.strftime("%H%M%S"); zid = f"{'P23' if identity else 'P25' if registry else 'P22' if images else 'P21'}-{run_tag}-1"; t1 = time.time()
        http("POST", f"{APP}/zakazky", json={"id": zid, "poptavka": f"Přidej do repa platformy soubor zakazky/{zid}/NOTES.md s poznámkou, že zakázka proběhla v AKS s konfigurací rolí z Gitu.", "hitl_timeout_s": 7200}, timeout=15)
        issue = pub(zid, "issue"); assert issue, f"issue nebylo publikováno; ledger: {[(e['kind'], e.get('role'), e.get('error') or e.get('phase')) for e in led() if e.get('zakazka') == zid][-8:]}"
        gh_post(f"/issues/{issue['number']}/comments", {"body": "/schvaluji"}, "stranger")
        time.sleep(5); adr_early = hash_of(zid, "adr://")
        gh_post(f"/issues/{issue['number']}/comments", {"body": "/schvaluji – zadání odpovídá"}, "adam")
        adr = wait_handoff(zid, "adr://", 900); assert adr, "Architekt nedodal ADR"
        approve(zid, "H2", adr)
        pr = pub(zid, "pull_request", 1500); assert pr, "PR nebyl publikován"
        wait_handoff(zid, "review://", 900)
        gh_post(f"/pulls/{pr['number']}/reviews", {"event": "APPROVE", "commit_id": pr["head_sha"], "body": "LGTM"}, "adam")
        t = time.time(); merged = False
        while time.time() - t < 180 and not merged:
            merged = http("GET", GHS, timeout=10).json()["pulls"][str(pr["number"])]["merged"]; time.sleep(2)
        approve(zid, "H5", hash_of(zid, "pr://")); st = wait_status(zid, {"COMPLETED", "FAILED"}, 300)
        L = led(); runs = {e["role"]: e for e in L if e["kind"] == "AGENT_RUN" and e["zakazka"] == zid}
        pods_led = {e["role"]: e for e in L if e["kind"] == "ROLE_POD" and e["zakazka"] == zid}
        pod_err = [e for e in L if e["kind"] == "ROLE_POD_ERROR" and e["zakazka"] == zid]
        mem_calls = [e for e in L if e["kind"] == "TOOL" and e["zakazka"] == zid and e["tool"] in ("search_memory", "create_memory")]
        signs = [e for e in L if e["kind"] == "SIGN" and e["zakazka"] == zid]
        ok_pods = set(pods_led) == set(ROLE_CLIENTS) and all(p.get("phase") == "Succeeded" and p.get("result_received") for p in pods_led.values())
        rep.add("P21b", "Zakázka na AKS end-to-end přes GitHub HITL (mock GitHub v clusteru): issue → /schvaluji → ADR → H2 → PR → review → merge → H5 → Dokonceno; 4 role jako pody v ns platform-roles (ROLE_POD Succeeded s výsledkem), AGENT_RUN z podu přeposlán do ledgeru aplikace (via=pod), paměť 200, approval tokeny z OpenBao", "PASS" if (st.get("output") or {}).get("stav") == "Dokonceno" and merged and not adr_early and set(runs) == set(ROLE_CLIENTS) and not any(r.get("error") for r in runs.values()) and all(r.get("via") == "pod" for r in runs.values()) and ok_pods and not pod_err and mem_calls and all(c.get("http") == 200 for c in mem_calls) and signs and all(s["backend"] == "openbao-transit" for s in signs) else "FAIL", {"output": st.get("output"), "merged_in_mock_github": merged, "issue": issue.get("number"), "pr": pr.get("number"), "roles": {k: {"tools": r.get("tool_uses"), "error": r.get("error"), "cost_usd": r.get("cost_usd"), "via": r.get("via")} for k, r in runs.items()}, "pods": {k: {"phase": p.get("phase"), "exit": p.get("exit_code"), "result": p.get("result_received"), "log_tail": p.get("log_tail")} for k, p in pods_led.items()}, "pod_errors": [e.get("error") for e in pod_err][:3], "memory_calls_200": sum(1 for c in mem_calls if c.get("http") == 200), "signs": len(signs), "wall_s": round(time.time() - t1, 1)})

        # P21b2 – klíče role × zakázka vydala aplikace (ledger GATEWAY_KEYS_ISSUED, ConfigMap agentgateway-keys, Secret zakazka-keys-<id>), rozpočty = roles/*.yaml
        issued = next((e for e in L if e["kind"] == "GATEWAY_KEYS_ISSUED" and e["zakazka"] == zid), None)
        keys_cm = _y.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
        mine = [k for k in keys_cm if (k.get("metadata") or {}).get("zakazka") == zid]
        want_block = {}
        for f in sorted((ROOT / "knowledge/organization/roles").glob("*.yaml")):
            r = _y.safe_load(f.read_text()); want_block[r["role"]] = next((b["amount"] for b in r.get("budget", {}).get("budgets", []) if b.get("window") == "24h" and b.get("action") == "Block"), None)
        got_block = {(k.get("metadata") or {}).get("role"): next((b["limit"]["amount"] for b in k.get("budgets", []) if b["name"].endswith("24h-block")), None) for k in mine}
        sec_keys = kubectl(a, "-n", NS, "get", "secret", f"zakazka-keys-{zid.lower()}", "-o", "jsonpath={.metadata.name}").stdout.strip()
        rep.add("P21b2", "Klíče gateway role × zakázka vydala aplikace při prvním běhu role (ne harness): hash + rozpočty z rolegen šablony do ConfigMapy agentgateway-keys (sidecar config-merge → hot reload), hodnoty do Secretu zakazka-keys-<id>; rozpočty Block 24h == knowledge/organization/roles/*.yaml; gateway klíč přijala (sonda 401 → 200)", "PASS" if issued and issued.get("probe_status") == 200 and set(ROLE_CLIENTS) <= set(issued.get("roles", [])) and len(mine) >= 4 and all(got_block.get(r) == want_block.get(r) for r in ROLE_CLIENTS) and sec_keys else "FAIL", {"issued": {k: issued.get(k) for k in ("roles", "propagation_s", "probe_status", "total_s", "hashes")} if issued else None, "keys_in_configmap_for_zakazka": len(mine), "budgets_block_24h": {"cluster": got_block, "roles_yaml": want_block}, "secret": sec_keys or None})

        if images:
            # P2-2 – obrazy rolí z rolegen (az acr build) a pod spec ze šablony rolegen
            import yaml as _y2
            versions = {}
            for f in sorted((ROOT / "knowledge/organization/roles").glob("*.yaml")):
                r = _y2.safe_load(f.read_text()); versions[r["role"]] = str(r["version"])
            acr_name = (a.acr or "").split(".")[0]; tags = {}
            for role in ROLE_CLIENTS:
                r = sh(["az", "acr", "repository", "show-tags", "-n", acr_name, "--repository", f"roles/{role}", "-o", "json"]) if acr_name and shutil.which("az") else None
                try: tags[role] = json.loads(r.stdout) if r and r.returncode == 0 else (r.stderr[-200:] if r else "az chybí")
                except Exception: tags[role] = r.stdout[-200:]
            pulled = {k: (p.get("image") or "") for k, p in pods_led.items() if p.get("phase") == "Succeeded"}   # záložní důkaz: pod roli z obrazu roles/<role>:<verze> skutečně stáhl a doběhl
            by_tags = all(isinstance(tags.get(r), list) and versions[r] in tags[r] for r in ROLE_CLIENTS)
            by_pods = all(pulled.get(r, "").startswith(f"{a.acr}/roles/{r}:{versions[r]}") for r in ROLE_CLIENTS)
            rep.add("P22a", "Obrazy rolí v ACR: roles/<role>:<verze z roles/*.yaml> pro každou roli (CI images.yml: az acr build vrstvy nad zakazka-app z infra/images/roles, které generuje rolegen – Dockerfile + devcontainer.json + etc/platform); důkaz = tagy z ACR (identita Actions s AcrPull) nebo aspoň pody, které obraz stáhly a doběhly", "PASS" if by_tags or by_pods else "FAIL", {"source": "acr_tags" if by_tags else ("pods" if by_pods else None), "tags": tags, "pulled": pulled, "versions_yaml": versions})
            ALLOWED = {"image.registry", "securityContext.seccompProfile", "securityContext.runAsGroup", "securityContext.fsGroup", "env+", "command", "envFrom", "imagePullPolicy", "volumeMounts", "nodeSelector", "tolerations", "restartPolicy", "activeDeadlineSeconds", "volumes"}
            tplinfo = {k: {"template": p.get("template"), "image": p.get("image"), "overrides": p.get("overrides"), "unexpected": sorted(set(p.get("overrides") or []) - ALLOWED), "resources": p.get("resources"), "image_role": p.get("image_role")} for k, p in pods_led.items()}
            ok_tpl = bool(tplinfo) and all(v["template"] and not v["unexpected"] and (v["image"] or "").startswith(f"{a.acr}/roles/{k}:{versions[k]}") and (v["image_role"] or {}).get("role") == k and (v["image_role"] or {}).get("version") == versions[k] and (v["image_role"] or {}).get("managed_settings") for k, v in tplinfo.items())
            rep.add("P22b", "Pod role ze šablony rolegen (pod-<role>.yaml z build/k8s): RuntimeClass, non-root, SA token off, drop ALL, resources, env a labels z definice role; aplikace doplní jen běh (jméno, Secret, env běhu, uzel, timeout, registry obrazu, seccomp Localhost → RuntimeDefault na Katě); obraz = roles/<role>:<verze> a /etc/platform/role.json v obrazu nese tutéž roli a verzi, managed settings zapečené", "PASS" if ok_tpl else "FAIL", tplinfo)
            tools_ok = bool(pods_led) and all((p.get("image_tools") or {}).get("present") and all((p["image_tools"]["present"]).values()) and all((p["image_tools"]["absent"]).values()) for p in pods_led.values())
            rep.add("P22c", "Obsah obrazu role (sonda z podu): git, node, python3, srt, bwrap, claude přítomny; az, gcloud, aws, kubectl, docker, helm, terraform nepřítomny (role.md: obraz role bez cloud CLI)", "PASS" if tools_ok else "FAIL", {k: p.get("image_tools") for k, p in pods_led.items()})

        if identity:
            # P2-3 – OpenBao auto-unseal + auth kubernetes, SVID podů rolí
            pf_bao2 = PortForward(a, "openbao", 18201, 8200); B2 = "http://127.0.0.1:18201"
            kubectl(a, "-n", NS, "delete", "pod", "openbao-0", "--wait=true", timeout=180)   # restart: musí naběhnout unsealed bez operátora
            t_un = time.time(); unsealed_after = None
            for _ in range(60):
                try:
                    pf_bao2.start(); hs = httpx.get(f"{B2}/v1/sys/seal-status", timeout=5).json()
                    if hs.get("initialized") and not hs.get("sealed"): unsealed_after = round(time.time() - t_un, 1); break
                except Exception: pass
                time.sleep(3)
            seal_after = httpx.get(f"{B2}/v1/sys/seal-status", timeout=10).json() if unsealed_after else {}
            pf_bao2.stop()
            rep.add("P23a", "OpenBao auto-unseal přes Azure Key Vault (seal azurekeyvault, klíč openbao-unseal, workload identity SA openbao přes UAMI + federated credential – žádné tajemství v podu): po smazání podu openbao-0 naběhne unsealed bez operátora; init s recovery klíči (Secret openbao-init), případně migrace z shamir", "PASS" if seal.get("type") == "azurekeyvault" and unsealed_after is not None and seal_after.get("type") == "azurekeyvault" and seal_after.get("recovery_seal") else "FAIL", {"seal_type": seal.get("type"), "recovery_seal": seal.get("recovery_seal"), "migrated_now": bao_migrated, "unsealed_after_restart_s": unsealed_after, "seal_after": {k: seal_after.get(k) for k in ("type", "sealed", "initialized", "recovery_seal", "version")}})
            bl = [e for e in L if e["kind"] == "BAO_LOGIN"]
            signs_ok = signs and all(s_["backend"] == "openbao-transit" for s_ in signs)
            sec_keys_app = kj("-n", NS, "get", "secret", "zakazka-secrets").get("data") or {}
            rep.add("P23b", "Aplikace zakázky bez tokenu OpenBao v Secretu: login auth/kubernetes projektovaným SA tokenem (role zakazka → policy approval-signer, TTL 1 h), approval tokeny podepsané transitem jako dřív (ledger SIGN backend openbao-transit)", "PASS" if bl and all(b.get("method") == "kubernetes" and "approval-signer" in (b.get("policies") or []) for b in bl) and signs_ok and "P0_BAO_TOKEN" not in sec_keys_app else "FAIL", {"bao_logins": [{k: b.get(k) for k in ("role", "policies", "ttl_s", "sa")} for b in bl][:3], "signs": len(signs), "secret_keys": sorted(sec_keys_app)})
            ids = {k: (p.get("identity") or {}) for k, p in pods_led.items()}
            ok_svid = bool(ids) and all(v.get("kind") == "svid" and v.get("spiffe_id") == f"spiffe://platform/role/{k}/acme" and v.get("iss") == "http://spire-oidc.platform-data.svc:8082" and p.get("svid_sidecar") for k, v in ids.items() for p in [pods_led[k]])
            rep.add("P23c", "Identita role v Kata podu = SVID: sidecar spire-agent (atestace k8s_psat projektovaným tokenem SA role, alias uzlu per role z rolegen entries, workload unix uid 1000) vydá X.509-SVID a JWT-SVID spiffe://platform/role/<role>/acme; role s ním volá paměť (server paměti ověřuje JWT-SVID přes spire-oidc /keys, tenant z cesty SPIFFE ID), Keycloak token ze Secretu nepoužit", "PASS" if ok_svid and mem_calls and all(c.get("http") == 200 for c in mem_calls) else "FAIL", {"identity": ids, "spire_entries_applied_now": spire_applied, "memory_calls_200": sum(1 for c in mem_calls if c.get("http") == 200)})
            pf_oidc = PortForward(a, "spire-oidc", 18082, 8082)
            try:
                jwks = http("GET", "http://127.0.0.1:18082/keys", headers={"Host": "spire-oidc"}, timeout=10); jk = jwks.json() if jwks.status_code == 200 else {}
                disc = http("GET", "http://127.0.0.1:18082/.well-known/openid-configuration", headers={"Host": "spire-oidc"}, timeout=10)
            finally: pf_oidc.stop()
            ents_now = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", "spire-server", "entry", "show", "-socketPath", "/tmp/spire-server/private/api.sock").stdout
            rep.add("P23d", "SPIRE OIDC discovery provider (sidecar serveru) vydává JWKS pro JWT-SVID; registrace z rolegen (alias uzlu + workload per role) v serveru", "PASS" if jk.get("keys") and disc.status_code == 200 and all(f"spiffe://platform/role/{r}/acme" in ents_now for r in ROLE_CLIENTS) else "FAIL", {"jwks_keys": len(jk.get("keys", [])), "discovery": disc.status_code, "entries": ents_now.count("Entry ID")})

        if registry:
            # P2-5 – eval gate (Git → ConfigMap → aplikace) a registr org.* na Flexible Serveru
            import yaml as _y3, hashlib as _h3
            es_git = json.loads((ROOT / "tools/role_evals/results/eval-status.json").read_text())
            es_cluster = json.loads((cfg_cluster["rolegen-build"] or {}).get("eval-status.json") or "{}")
            gates = {e["role"]: e for e in L if e["kind"] == "ROLE_GATE" and e["zakazka"] == zid}
            rep.add("P25a", "Eval gate: tools/role_evals/results/eval-status.json (CI rolegen.yml: evaly L0–L3 nad adversariálním mockem, gate z roles/*.yaml) == ConfigMap rolegen-build v clusteru; role zakázky mají passed a aplikace to před každým během ověřila (ledger ROLE_GATE passed=true); SRE unevaluated = aplikace by ji nespustila", "PASS" if es_git == es_cluster and all((es_cluster.get(r) or {}).get("status") == "passed" for r in ROLE_CLIENTS) and set(gates) == set(ROLE_CLIENTS) and all(g.get("passed") for g in gates.values()) and (es_cluster.get("sre") or {}).get("status") == "unevaluated" else "FAIL", {"status_equal": es_git == es_cluster, "roles": {r: (es_cluster.get(r) or {}).get("status") for r in es_cluster}, "role_gate_ledger": {r: {"passed": g.get("passed"), "layers": g.get("layers")} for r, g in gates.items()}})
            rg = __import__("importlib.util").util.spec_from_file_location("regm", ROOT / "tools/role_evals/registry.py"); rgm = __import__("importlib.util").util.module_from_spec(rg); rg.loader.exec_module(rgm)
            roles_yaml = {f.stem: _y3.safe_load(f.read_text()) for f in sorted((ROOT / "knowledge/organization/roles").glob("*.yaml"))}
            results = {f.stem: json.loads(f.read_text()) for f in (ROOT / "tools/role_evals/results").glob("*.json") if f.stem != "eval-status"}
            opa_rev = _h3.sha256(((cfg_cluster["rolegen-build"] or {}).get("opa-data.json") or "").encode()).hexdigest()[:16]
            with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
                rgm.ensure_schema(c)
                n_roles = rgm.seed_roles(c, roles_yaml, es_git, want_sha); n_gates = rgm.seed_eval_gates(c, results, want_sha)
                n_agents = rgm.seed_agents(c, L, zid, roles_yaml, opa_rev, os.environ.get("P0_MODEL", "claude-haiku-4-5"))
                summ = rgm.summary(c)
            st_roles = {r[0]: r[2] for r in summ["role_definitions"]}
            agents_z = [r for r in summ["agents"] if zid in r[0]]
            rep.add("P25b", "Registr agentů (metriky.md T12) v DB org na Flexible Serveru: org.role_definitions (verze, sha, commit, status active/suspended/proposed z eval gate), org.eval_gates (řádek per vrstva × role z CI evalů, čl. 15 evidence), org.agents (instance rolí zakázky z ledgeru: SPIFFE ID, model, klíč gateway, sandbox profil, obraz, uzel)", "PASS" if n_roles >= 5 and n_gates >= 12 and len(agents_z) == len(ROLE_CLIENTS) and all(st_roles.get(r) == "active" for r in ROLE_CLIENTS) and st_roles.get("sre") == "proposed" else "FAIL", {"role_definitions": st_roles, "eval_gates_inserted": n_gates, "eval_gates_total": len(summ["eval_gates"]), "agents_for_zakazka": [(r[1], r[3], r[4], (r[6] or "").split("/")[-1]) for r in agents_z]})
            nc = sh([sys.executable, str(ROOT / "tools/role_evals/evals.py"), "--negative-control", "--port", "9797"], timeout=900)
            try: ncj = json.loads(nc.stdout.strip().splitlines()[-1])
            except Exception: ncj = {"stdout": nc.stdout[-300:], "stderr": nc.stderr[-300:]}
            rep.add("P25c", "Negativní kontrola gate (na runneru): Vývojář L3 bez PEP paměti a egressu musí propadnout – gate měří obranu platformy (PEP, approval policy z rolegen), ne to, že mock injekci odmítne", "PASS" if nc.returncode == 0 and ncj.get("ok") else "FAIL", ncj)

        # P21c – izolace podů rolí
        nodes = {n["metadata"]["name"]: n["metadata"]["labels"].get("pool") for n in kj("get", "nodes").get("items", [])}
        tc = time.time()
        while time.time() - tc < 120:   # smazání podu je asynchronní (Terminating, Kata VM se vypíná) – počkat na zmizení
            left = [p["metadata"]["name"] for p in kj("-n", RNS, "get", "pods").get("items", [])]; left_sec = [s["metadata"]["name"] for s in kj("-n", RNS, "get", "secrets").get("items", []) if s["metadata"]["name"].startswith("role-")]
            if not left and not left_sec: break
            time.sleep(5)
        cleanup_s = round(time.time() - tc, 1)
        iso = {k: {"node": p.get("node"), "pool": nodes.get(p.get("node")), "runtime_class": p.get("runtime_class"), "uid": p.get("pod_uid"), "run_as_user": p.get("run_as_user"), "automount_sa": p.get("automount_sa"), "srt": p.get("pod_srt")} for k, p in pods_led.items()}
        rep.add("P21c", "Izolace podů rolí: každý pod role na uzlu poolu kata (autoscaler z 0), RuntimeClass kata-vm-isolation, běží jako uid 1000 bez SA tokenu, srt (weaker nested sandbox) v podu k dispozici; po běhu pod i Secret smazány", "PASS" if pods_led and all(v["pool"] == "kata" and v["runtime_class"] == "kata-vm-isolation" and v["uid"] == 1000 and v["run_as_user"] == 1000 and v["automount_sa"] is False and v["srt"] not in (None, "none") for v in iso.values()) and not left and not left_sec else "FAIL", {"pods": iso, "left_pods": left, "left_secrets": left_sec, "cleanup_wait_s": cleanup_s, "kata_nodes": [n for n, p in nodes.items() if p == "kata"]})

        # P21d – egress
        eg = {k: p.get("egress_probe") for k, p in pods_led.items()}
        def blocked(r): return bool(r) and r.get("result") != "open"
        ok_eg = bool(eg) and all(e and blocked(e.get("internet_1.1.1.1:443")) and blocked(e.get("internet_dns_github.com:443")) and all((e.get(n) or {}).get("result") == "open" for n in ("memory", "gateway", "app")) for e in eg.values())
        rep.add("P21d", "Egress podu role (NetworkPolicy ns platform-roles): internet (1.1.1.1:443, github.com:443) blokován, agentgateway, paměť a aplikace zakázky průchozí – model jen přes gateway", "PASS" if ok_eg else "FAIL", {"probe": eg})

        # P21e – časy
        tm = {k: {"schedule_s": p.get("t_schedule_s"), "start_s": p.get("t_start_s"), "run_s": p.get("t_run_s"), "total_s": p.get("t_total_s")} for k, p in pods_led.items()}
        rep.add("P21e", "Časy podů rolí: schedule = čekání na uzel (první role zahrnuje scale-up poolu kata z 0), start = tah obrazu + boot Kata VM, run = běh role", "INFO", tm)

        # P21f – paměť
        human = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "harness-human", "username": "adam", "password": "adam"}, timeout=15); assert human.status_code == 200, human.text[:200]
        human = human.json()["access_token"]
        unv = http("POST", f"{MEM}/tools/search_memory", json={"query": "ACME endpoint", "include_unverified": True, "limit": 20}, headers={"Authorization": f"Bearer {human}"}, timeout=15)
        recs = unv.json().get("records", []) if unv.status_code == 200 else []
        proposed = [r for r in recs if r.get("status") == "proposed" or r.get("unverified")]
        rep.add("P21f", "Paměť na Flexible Serveru: zápisy rolí z podů (Keycloak service-account tokeny) jako proposed; člověk (password grant přes port-forward, iss KC_HOSTNAME) je vidí s include_unverified", "PASS" if unv.status_code == 200 and recs and proposed else "FAIL", {"http": unv.status_code, "records": len(recs), "proposed": len(proposed), "iss": jwt.decode(human, options={"verify_signature": False}).get("iss")})

        # P16g – FinOps
        with psycopg.connect(dsn("agentgateway"), autocommit=True, connect_timeout=10) as c:
            rows = c.execute("SELECT budget_id, used_amount FROM budget_usage").fetchall()
        spend = {}
        for k in mine:
            role = (k.get("metadata") or {}).get("role"); h = k["keyHash"].split(":", 1)[1]
            if role in ROLE_CLIENTS: spend[role] = next((used / 1e9 for bid, used in rows if h in bid and bid.endswith("24h-block")), 0.0)
        rep.add("P21g", "FinOps na AKS: requesty rolí z podů šly přes clusterovou gateway s klíči vydanými aplikací → budget_usage na Flexible Serveru nese útratu každé role (hash klíče z ConfigMapy agentgateway-keys; obsahuje i sondu propagace)", "PASS" if set(spend) == set(ROLE_CLIENTS) and all(v > 0 for v in spend.values()) else "FAIL", {"spend_usd_by_role": spend, "total_usd": round(sum(spend.values()), 6)})

        pods = kj("-n", NS, "get", "pods").get("items", [])
        rep.add("P21h", "Pody P2-1 a uzly", "INFO", {p["metadata"]["name"]: {"image": [c["image"].split("/")[-1] for c in p["spec"]["containers"]], "restarts": [c.get("restartCount") for c in p["status"].get("containerStatuses", [])]} for p in pods if p["metadata"]["name"].split("-")[0] in ("zakazka", "memory", "bridge", "mock", "opa", "placement", "scheduler", "agentgateway")} | {"nodes": nodes, "wall_s": round(time.time() - t_all, 1)})
    finally:
        for pf in pfs.values(): pf.stop()
        pf_bao.stop()
        if pf_pg: pf_pg.terminate(); kubectl(a, "-n", NS, "delete", "pod", "pgfwd", "--ignore-not-found", "--wait=false")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["p1-2", "p1-3", "p1-4", "p1-5", "p1-6", "p2-1", "p2-2", "p2-5", "p2-3"], default="p1-2")
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--dapr-bin-dir", default=os.getenv("DAPR_BIN_DIR", ""), help="p1-3: O-2 identity potřebuje lokální Dapr (placement, scheduler, daprd)")
    ap.add_argument("--kubectl", default=os.getenv("KUBECTL", shutil.which("kubectl") or ""))
    ap.add_argument("--kind", default=os.getenv("KIND", shutil.which("kind") or ""))
    ap.add_argument("--context", default="kind-platform", help="p1-6: kontext AKS, např. aks-platform-dev-admin")
    ap.add_argument("--acr", default=os.getenv("ACR_LOGIN_SERVER", ""), help="p1-6: login server ACR (socat pod pro Postgres, když runner nedosáhne na Flexible Server)")
    ap.add_argument("--create-kind", action="store_true", help="postavit obraz uzlu, cluster a nahrát obrazy (docker daemon)")
    ap.add_argument("--opa-bin", default=os.getenv("OPA_BIN", shutil.which("opa") or ""))
    ap.add_argument("--agentgateway-bin", default=os.getenv("AGENTGATEWAY_BIN", shutil.which("agentgateway") or ""))
    a = ap.parse_args()
    if not a.kubectl or (a.step not in ("p1-6", "p2-1", "p2-2", "p2-5", "p2-3") and not (a.opa_bin and a.agentgateway_bin)):
        print("chybí KUBECTL, OPA_BIN nebo AGENTGATEWAY_BIN"); sys.exit(2)
    for d in (RESULTS, LOGS): d.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("anthropic_base_url",)}
    env["NO_PROXY"] = env["no_proxy"] = (env.get("NO_PROXY", "") + ",127.0.0.1,localhost").strip(",")
    rep = Report()
    if a.create_kind:
        assert a.kind, "chybí KIND"
        create_kind(a, env)
    {"p1-2": step_p1_2, "p1-3": step_p1_3, "p1-4": step_p1_4, "p1-5": step_p1_5, "p1-6": step_p2_1, "p2-1": step_p2_1, "p2-2": lambda a, rep, env: step_p2_1(a, rep, env, images=True), "p2-5": lambda a, rep, env: step_p2_1(a, rep, env, images=True, registry=True), "p2-3": lambda a, rep, env: step_p2_1(a, rep, env, images=True, registry=True, identity=True)}[a.step](a, rep, env)   # p1-6 = alias (od P2-1 je konfigurace z Gitu)
    out = RESULTS / f"{a.step}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": a.step, "context": a.context, "kind": sh([a.kind, "version"]).stdout.strip() if a.kind else None, "images": IMAGES}, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")
    sys.exit(0 if n["FAIL"] == 0 else 1)


if __name__ == "__main__":
    main()
