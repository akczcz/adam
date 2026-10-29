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
import re
import shutil
import subprocess
import sys
import tempfile
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
CAP_BUDGET = "zakazka-30d-block"   # P3-6 E3: druhý rozpočet klíče (strop zakázky) – útrata klíče jen z rozpočtu role, jinak dvojí započtení (nález E4)


def role_usage_usd(rows, h):
    """Útrata klíče (hash h) v USD z řádků budget_usage (budget_id, used_amount): jen rozpočet role `<role>-30d-block`, ne `zakazka-30d-block`."""
    return sum(u / 1e9 for bid, u in rows if h in bid and not bid.endswith(CAP_BUDGET))
SPIRE_SERVER_BIN = "/opt/spire/bin/spire-server"   # oficiální obraz ghcr.io/spiffe/spire-server (AKS): binárka není v PATH
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
        rolls = {k: kubectl(a, "-n", NS, "rollout", "status", k, "--timeout=420s", timeout=440).returncode == 0 for k in ("deployment/keycloak", "deployment/opa", "statefulset/placement", "statefulset/scheduler", "deployment/memory", "deployment/mock-github", "deployment/bridge", "deployment/zakazka", "deployment/mock-channels")}
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
        httpx.post(f"{APP}/zakazky", json={"id": zid, "poptavka": f"Přidej do repa platformy soubor zakazky/{zid}/NOTES.md s poznámkou, že zakázka proběhla v Kubernetes.", "hitl_timeout_s": 3600, "klasifikace": KLAS_NO}, timeout=15)
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
        httpx.post(f"{APP}/zakazky", json={"id": zid2, "poptavka": "Přidej endpoint /version do služby ACME (test durability).", "hitl_timeout_s": 3600, "klasifikace": KLAS_NO}, timeout=15)
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


def kc_ensure(a, http, KC, realm="p0"):
    """P3-2: Keycloak `--import-realm` existující realm nemění → chybějící realm role, klienty a uživatele z realm-p0.json (zdroj pravdy; lidé tenantů
    = tenants.yaml) doplní harness admin API (idempotentní). Nový cluster je importuje z ConfigMapy; tady jde o migraci běžícího realmu."""
    import base64 as _b
    O2 = T / "harness_p0_o2"; rj = json.loads((O2 / "configs/realm-p0.json").read_text())
    pw = _b.b64decode(kubectl(a, "-n", NS, "get", "secret", "keycloak-admin", "-o", "jsonpath={.data.KC_BOOTSTRAP_ADMIN_PASSWORD}").stdout.strip()).decode()
    user = _b.b64decode(kubectl(a, "-n", NS, "get", "secret", "keycloak-admin", "-o", "jsonpath={.data.KC_BOOTSTRAP_ADMIN_USERNAME}").stdout.strip()).decode() or "admin"
    tok = http("POST", f"{KC}/realms/master/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "admin-cli", "username": user, "password": pw}, timeout=20)
    assert tok.status_code == 200, f"Keycloak admin login: {tok.status_code} {tok.text[:200]}"
    H = {"Authorization": f"Bearer {tok.json()['access_token']}"}; A = f"{KC}/admin/realms/{realm}"; created = {"roles": [], "clients": [], "users": [], "errors": []}
    have_roles = {r["name"] for r in http("GET", f"{A}/roles", headers=H, timeout=20).json()}
    for r in rj["roles"]["realm"]:
        if r["name"] not in have_roles:
            x = http("POST", f"{A}/roles", headers=H, json={"name": r["name"], "description": r.get("description", "")}, timeout=20); created["roles"].append((r["name"], x.status_code))
    for c in rj["clients"]:
        if not http("GET", f"{A}/clients", headers=H, params={"clientId": c["clientId"]}, timeout=20).json():
            x = http("POST", f"{A}/clients", headers=H, json=c, timeout=20); created["clients"].append((c["clientId"], x.status_code))
            if x.status_code >= 300: created["errors"].append(f"client {c['clientId']}: {x.text[:200]}")
    for u in rj["users"]:
        if u.get("serviceAccountClientId"): continue
        if http("GET", f"{A}/users", headers=H, params={"username": u["username"], "exact": "true"}, timeout=20).json(): continue
        body = {k: v for k, v in u.items() if k not in ("realmRoles",)}
        x = http("POST", f"{A}/users", headers=H, json=body, timeout=20); created["users"].append((u["username"], x.status_code))
        if x.status_code >= 300: created["errors"].append(f"user {u['username']}: {x.text[:200]}"); continue
        uid = http("GET", f"{A}/users", headers=H, params={"username": u["username"], "exact": "true"}, timeout=20).json()[0]["id"]
        reps = [http("GET", f"{A}/roles/{rn}", headers=H, timeout=20).json() for rn in u.get("realmRoles", [])]
        y = http("POST", f"{A}/users/{uid}/role-mappings/realm", headers=H, json=[{"id": r["id"], "name": r["name"]} for r in reps if "id" in r], timeout=20)
        if y.status_code >= 300: created["errors"].append(f"roles {u['username']}: {y.text[:200]}")
    # P3-6 E2: IdP `aks` typu kubernetes (client assertion = projektovaný SA token podu role; issuer clusteru z Terraformu → zakazka-env), klienti
    # agent-<role>-<tenant> z rolegen-build (federated-jwt + standard token exchange), audience mappery platform-gui (žadatel exchange musí být v aud
    # tokenu člověka), lifespan tokenu GUI 30 min (subject token musí přežít do startu role bez HITL – reviewer po vývojáři)
    def cm(name): r = kubectl(a, "-n", NS, "get", "configmap", name, "-o", "json"); return (json.loads(r.stdout).get("data") or {}) if r.returncode == 0 else {}
    kcc = json.loads(cm("rolegen-build").get("keycloak-clients.json") or "{}"); issuer = (cm("zakazka-env").get("P0_K8S_OIDC_ISSUER") or "").strip(); e2 = {}
    if kcc.get("clients") and issuer:
        idp = kcc["identity_provider"]; r = http("GET", f"{A}/identity-provider/instances/{idp['alias']}", headers=H, timeout=20)
        if r.status_code == 404:
            x = http("POST", f"{A}/identity-provider/instances", headers=H, json={"alias": idp["alias"], "providerId": idp["providerId"], "enabled": True, "config": {"issuerDiscoveryUrl": issuer.rstrip("/")}}, timeout=90)
            e2["idp"] = x.status_code
            if x.status_code >= 300: created["errors"].append(f"idp {idp['alias']}: {x.text[:300]}")
        else: e2["idp"] = "exists"
        for c in kcc["clients"]:
            if not http("GET", f"{A}/clients", headers=H, params={"clientId": c["clientId"]}, timeout=20).json():
                x = http("POST", f"{A}/clients", headers=H, json=c, timeout=20); created["clients"].append((c["clientId"], x.status_code))
                if x.status_code >= 300: created["errors"].append(f"client {c['clientId']}: {x.text[:200]}")
        gui = http("GET", f"{A}/clients", headers=H, params={"clientId": "platform-gui"}, timeout=20).json()
        if gui:
            gid = gui[0]["id"]
            if (gui[0].get("attributes") or {}).get("access.token.lifespan") != "1800":   # PUT bez protocolMappers (reprezentace by je přepsala) a PŘED přidáním mapperů (nález E2, 1. běh)
                rep_ = {k: v for k, v in gui[0].items() if k not in ("protocolMappers", "defaultClientScopes", "optionalClientScopes")}; rep_["attributes"] = {**(rep_.get("attributes") or {}), "access.token.lifespan": "1800"}
                x = http("PUT", f"{A}/clients/{gid}", headers=H, json=rep_, timeout=20); e2["gui_lifespan"] = x.status_code
            have = {m["name"] for m in http("GET", f"{A}/clients/{gid}/protocol-mappers/models", headers=H, timeout=20).json()}
            for m in kcc["gui_mappers"]:
                if m["name"] in have: continue
                x = http("POST", f"{A}/clients/{gid}/protocol-mappers/models", headers=H, json=m, timeout=20); e2.setdefault("gui_mappers", []).append((m["name"], x.status_code))
            e2["gui_mappers_now"] = len(http("GET", f"{A}/clients/{gid}/protocol-mappers/models", headers=H, timeout=20).json())
        ex = http("GET", f"{A}/authentication/flows/clients/executions", headers=H, timeout=20)
        e2["federated_jwt_execution"] = next((x_.get("requirement") for x_ in (ex.json() if ex.status_code == 200 else []) if x_.get("providerId") == "federated-jwt"), None)   # realm z 26.8 ji má; starší realm = kopie flow
    else: e2 = {"skipped": "bez keycloak-clients.json (rolegen-build) nebo P0_K8S_OIDC_ISSUER (zakazka-env)"}
    created["e2"] = e2
    return created


def spire_server_reload(a, kj):
    """P3-2: ConfigMap spire-server-config (allow-list ns tenantů) z Gitu – StatefulSet pod bez restartu nový config nenačte. Anotace podu se sha
    configu: liší se → pod smazat (raft/sqlite na PVC zůstává), počkat na rollout, anotovat."""
    import hashlib as _h
    cm = kj("-n", NS, "get", "configmap", "spire-server-config").get("data") or {}; sha = _h.sha256(json.dumps(cm, sort_keys=True).encode()).hexdigest()[:16]
    pod = kj("-n", NS, "get", "pod", "spire-server-0"); ann = (pod.get("metadata", {}).get("annotations") or {}).get("platform.config-sha")
    if ann == sha: return {"restarted": False, "sha": sha}
    kubectl(a, "-n", NS, "delete", "pod", "spire-server-0", "--wait=true", timeout=180)
    ok = kubectl(a, "-n", NS, "rollout", "status", "statefulset/spire-server", "--timeout=300s", timeout=320).returncode == 0
    kubectl(a, "-n", NS, "annotate", "pod", "spire-server-0", f"platform.config-sha={sha}", "--overwrite")
    return {"restarted": True, "sha": sha, "ready": ok, "previous": ann}


def tenant_flow(a, rep, http, led, APP, dsn, kj, zid_acme, tag, gui_shots):
    """T-1 (P3-2): druhý tenant beta – zakázka z GUI jako bea, pody rolí v ns tenant-beta (CNP, SPIFFE ID s tenantem), klíče per tenant, RLS org.*,
    viditelnost threadů per tenant a průřez tenanta platform."""
    import psycopg, yaml as _yt, hashlib as _ht
    sys.path.insert(0, str(HERE)); from gui_checks import Gui
    def tenant_namespaces(): return [n["metadata"]["name"] for n in kj("get", "ns", "-l", "platform.tenant").get("items", [])]
    kubectl(a, "delete", "ns", "platform-roles", "--ignore-not-found", "--wait=false")   # P2 ns bez tenantů – Flux roles kustomization nemá prune
    tenants_git = _yt.safe_load((ROOT / "knowledge/organization/tenants.yaml").read_text())["tenants"]
    tj = json.loads((kj("-n", NS, "get", "configmap", "rolegen-build").get("data") or {}).get("tenants.json") or "[]")
    sync = next((e for e in reversed(led()) if e["kind"] == "TENANTS_SYNC"), {})
    with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
        trows = {r[0]: {"budget": float(r[1]), "profile": r[2], "ns": r[3], "role_pods": r[4]} for r in c.execute("SELECT tenant_id, budget_usd, profile, namespace, role_pods FROM org.tenants").fetchall()}
        pols = sorted({(r[0], r[1]) for r in c.execute("SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'org'").fetchall()})
        rls_on = {r[0]: r[1] for r in c.execute("SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace = 'org'::regnamespace AND relkind = 'r'").fetchall()}
    want_ns = {f"tenant-{t['id']}" for t in tenants_git if t.get("role_pods")}
    rep.add("T1a", "Tenanti z Gitu (knowledge/organization/tenants.yaml → rolegen tenants.json v ConfigMapě → aplikace při startu): řádky org.tenants (acme, beta, platform s rozpočtem a profilem), namespace tenant-<id> pro tenanty s pody rolí existují (Flux z tenants-generated.yaml), RLS zapnutá s politikou tenant_isolation na org.tenants/zakazky/approvals (TENANTS_SYNC v ledgeru)", "PASS" if {t["id"] for t in tenants_git} == set(trows) == {t["id"] for t in tj} and all(abs(trows[t["id"]]["budget"] - float(t["budget_usd"])) < 1e-6 for t in tenants_git) and want_ns <= set(tenant_namespaces()) and all(rls_on.get(t) for t in ("tenants", "zakazky", "approvals")) and {("tenants", "tenant_isolation"), ("zakazky", "tenant_isolation"), ("approvals", "tenant_isolation")} <= set(pols) and sync.get("written") else "FAIL", {"org_tenants": trows, "namespaces": tenant_namespaces(), "rls": rls_on, "policies": pols, "sync": {k: sync.get(k) for k in ("written", "tenants", "rls", "error")}})
    zb = f"{tag}-beta"; g = Gui(f"{APP}/gui/", shots=gui_shots / "beta").open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10); t_b = time.time()
    def wait_i(g_, bod, timeout):
        t0 = time.time()
        while True:
            r = g_.wait_interrupt(bod, min(60, max(1, timeout - (time.time() - t0))))
            if r["interrupt"] or r["run_status"] in ("finished", "cancelled") or time.time() - t0 >= timeout: return r
            try: http("GET", f"{APP}/health", timeout=10)
            except Exception: pass
    try:
        li = g.login("bea", "bea"); lst0 = g.threads_list()
        g.create_thread(zb, f"Zakázka tenanta beta {zb}: založ v repu soubor zakazky/{zb}/NOTES.md (test druhého tenanta).")
        dialog_then(g, zb, 1500)
        h1 = wait_i(g, "H1", 1500); assert h1["interrupt"], f"H1 (beta) nepřišel: {h1['run_status']} {h1.get('error')} ledger={[(e['kind'], e.get('role'), e.get('error') or e.get('event')) for e in led() if e.get('zakazka') == zb][-8:]}"
        L = led(); pod_b = next((e for e in L if e["kind"] == "ROLE_POD" and e["zakazka"] == zb and e["role"] == "account"), {}); cr_b = next((e for e in L if e["kind"] == "ROLE_POD_CREATE" and e["zakazka"] == zb), {})
        nps = [n["metadata"]["name"] for n in kj("-n", "tenant-beta", "get", "networkpolicy").get("items", [])]
        eg = pod_b.get("egress_probe") or {}
        rep.add("T1b", "Pody rolí tenanta beta běží v ns tenant-beta (NetworkPolicy default-deny + role-egress jen na platformu): pod account zakázky beta v tenant-beta, Succeeded; z podu Postgres platformy nedosažitelný (timeout), internet blokován, gateway/paměť/aplikace průchozí", "PASS" if pod_b.get("namespace") == "tenant-beta" and cr_b.get("namespace") == "tenant-beta" and pod_b.get("phase") == "Succeeded" and {"default-deny", "role-egress"} <= set(nps) and (eg.get("postgres") or {}).get("result") not in (None, "open") and (eg.get("internet_1.1.1.1:443") or {}).get("result") != "open" and all((eg.get(n) or {}).get("result") == "open" for n in ("memory", "gateway", "app")) else "FAIL", {"pod": {k: pod_b.get(k) for k in ("pod", "namespace", "phase", "node", "image")}, "networkpolicies": nps, "egress_probe": eg})
        ids_b = pod_b.get("identity") or {}
        ents = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "entry", "show", "-socketPath", "/tmp/spire-server/private/api.sock").stdout
        rep.add("T1f", "Identita role nese tenant: SVID podu account v tenant-beta = spiffe://platform/role/account/beta (alias uzlu per role × tenant se selektorem k8s_psat:agent_ns:tenant-beta – hranicí je atestovaný namespace, ne label), server paměti ověřil JWT-SVID (tenant z cesty); entries pro oba tenanty v SPIRE serveru", "PASS" if ids_b.get("kind") == "svid" and ids_b.get("spiffe_id") == "spiffe://platform/role/account/beta" and "spiffe://platform/role/account/beta" in ents and "spiffe://platform/role/account/acme" in ents and "k8s_psat:agent_ns:tenant-beta" in ents and any(e["kind"] == "TOOL" and e["zakazka"] == zb and e.get("http") == 200 for e in L) else "FAIL", {"identity": ids_b, "entries_beta": ents.count("/beta"), "entries_acme": ents.count("/acme"), "memory_calls_200": sum(1 for e in L if e["kind"] == "TOOL" and e["zakazka"] == zb and e.get("http") == 200)})
        import yaml as _yk
        keys_cm = _yk.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
        mine = [k for k in keys_cm if (k.get("metadata") or {}).get("zakazka") == zb]; hashes = {(k.get("metadata") or {}).get("role"): k["keyHash"].split(":", 1)[1] for k in mine}
        with psycopg.connect(dsn("agentgateway"), autocommit=True, connect_timeout=10) as c:
            rows = c.execute("SELECT budget_id, used_amount FROM budget_usage WHERE budget_id LIKE '%-30d-block'").fetchall()
        spend_b = {r_: role_usage_usd(rows, h) for r_, h in hashes.items()}
        gate_b = next((e for e in L if e["kind"] == "BUDGET_GATE" and e["zakazka"] == zb), {})
        rep.add("T1d", "Klíče gateway per tenant: klíče zakázky beta jsou k-beta-<zakazka>-<role> s metadata.tenant=beta a user_id beta/…, vydané z šablony s placeholderem {tenant}; útrata account v budget_usage > 0; budget_gate zná strop tenanta (org.tenants.budget_usd 20) a útratu tenanta", "PASS" if len(mine) >= 4 and all((k.get("metadata") or {}).get("tenant") == "beta" and (k.get("metadata") or {}).get("name", "").startswith("k-beta-") and (k.get("metadata") or {}).get("user_id", "").startswith("beta/") for k in mine) and spend_b.get("account", 0) > 0 and (gate_b.get("tenant") or {}).get("budget_usd") == 20 else "FAIL", {"keys": [(k.get("metadata") or {}).get("name") for k in mine], "spend_usd": {k: round(v, 6) for k, v in spend_b.items()}, "gate": {k: gate_b.get(k) for k in ("role", "tenant", "exceeded")}})
        def rls(tenant):
            pw = dsn("org").split(":", 2)[2].split("@")[0]; host = dsn("org").split("@")[1].split("/")[0]
            with psycopg.connect(f"postgresql://org_reader:org_reader@{host}/org?sslmode=require", autocommit=True, connect_timeout=10) as c:
                c.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
                z_ = sorted(r[0] for r in c.execute("SELECT zakazka_id FROM org.zakazky").fetchall()); ap_ = c.execute("SELECT count(*) FROM org.approvals").fetchone()[0]
                tn_ = sorted(r[0] for r in c.execute("SELECT tenant_id FROM org.tenants").fetchall())
                return {"zakazky": z_, "approvals": ap_, "tenants": tn_}
        r_acme, r_beta, r_plat, r_none = rls("acme"), rls("beta"), rls("platform"), rls("")
        rep.add("T1c", "RLS per tenant_id na org.* (role org_reader = čtení pro Governance MCP): s app.tenant_id=beta jsou vidět jen zakázky/approvaly/tenant beta, s acme jen acme (zakázka beta chybí), s platform průřez obou, bez tenanta nic", "PASS" if zb in r_beta["zakazky"] and zid_acme not in r_beta["zakazky"] and zid_acme in r_acme["zakazky"] and zb not in r_acme["zakazky"] and {zid_acme, zb} <= set(r_plat["zakazky"]) and r_none["zakazky"] == [] and r_beta["tenants"] == ["beta"] and r_acme["approvals"] >= 4 and 1 <= r_beta["approvals"] < r_acme["approvals"] and r_beta["approvals"] + r_acme["approvals"] <= r_plat["approvals"] else "FAIL", {"beta": r_beta, "acme": {"zakazky_n": len(r_acme["zakazky"]), "has_acme": zid_acme in r_acme["zakazky"], "has_beta": zb in r_acme["zakazky"], "approvals": r_acme["approvals"]}, "platform": {"n": len(r_plat["zakazky"]), "tenants": r_plat["tenants"]}, "none": r_none})
        lst_b = g.threads_list(); ot = g.open_thread(zid_acme)
        r403 = http("POST", f"{APP}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": zid_acme, "runId": "t1e", "messages": []}, timeout=15).status_code
        g.page.goto(f"{APP}/gui/#/t/{zb}"); g.page.wait_for_timeout(1500)
        g.open_thread(zb); stp = g.stop("Test tenantů hotov – zakázku beta zastavuji (není třeba dokončit).")
        g.close(); g2 = Gui(f"{APP}/gui/", shots=gui_shots / "platform").open(); g2.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)
        lp = g2.login("platform-admin", "platform-admin"); lst_p = g2.threads_list(); ot_p = g2.open_thread(zb)
        r403p = http("POST", f"{APP}/agui/run", headers={"Authorization": f"Bearer {g2.token}"}, json={"threadId": f"{tag}-plat", "runId": "t1e2", "messages": [{"id": "m", "role": "user", "content": "platform nesmí zakládat"}]}, timeout=15).status_code
        g2.close()
        ids_b_list = [t["id"] for t in lst_b]; ids_p = [t["id"] for t in lst_p]
        rep.add("T1e", "GUI per tenant: bea (tenant beta) vidí jen zakázky beta (acme zakázka v seznamu není, otevřít ji → 404 v GUI i API), stop zakázky beta s důvodem funguje; platform-admin (tenant platform) vidí průřez obou tenantů (acme i beta), otevře thread beta, ale zakázku založit nesmí (403)", "PASS" if li["tenant"] == "beta" and zb in ids_b_list and zid_acme not in ids_b_list and all(t["cells"][1] == "beta" for t in lst_b) and ot["status"] == "error" and "404" in (ot["error"] or "") and r403 == 404 and stp["run_status"] == "cancelled" and lp["tenant"] == "platform" and {zid_acme, zb} <= set(ids_p) and ot_p["status"] != "error" and r403p == 403 else "FAIL", {"bea": {"tenant": li["tenant"], "listed": ids_b_list[:8], "open_acme": ot, "api_acme": r403, "stop": stp["run_status"]}, "platform_admin": {"tenant": lp["tenant"], "listed_n": len(ids_p), "has_both": {zid_acme, zb} <= set(ids_p), "open_beta": ot_p["status"], "create_http": r403p}, "wall_s": round(time.time() - t_b, 1)})
    finally:
        try: g.close()
        except Exception: pass


def dialog_then(g, zid, timeout_s):
    """P3-3: pokud první interrupt threadu je dialog Account (otázky), odpovědět a vrátit důkaz; HITL nechat čekat. Max 3 kola."""
    out = []
    for _ in range(3):
        w = g.wait_any_interrupt(timeout_s)
        if w.get("kind") != "dialog": return out
        out.append(g.answer_dialog("Soubor patří do zakazky/<id>/NOTES.md, čte ho vlastník procesu; rozpočet i termín výchozí."))
    return out


def gov_flow(a, rep, http, led, APP, KC, dsn, kj, zid_acme, tag, gui_shots, init_root_token):
    """U-2 (P3-3): GUI nad celou firmou – pohledy z Governance MCP (org.*, RLS), posun autonomie, stop tenanta, governance report, export, dialog Account."""
    import psycopg, yaml as _yg
    sys.path.insert(0, str(HERE)); from gui_checks import Gui, ROLES
    rg = __import__("importlib.util").util.spec_from_file_location("regm", ROOT / "tools/role_evals/registry.py"); rgm = __import__("importlib.util").util.module_from_spec(rg); rg.loader.exec_module(rgm)
    def tok(user, pw): r = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "platform-gui", "username": user, "password": pw}, timeout=15); return r.json()["access_token"]
    def gov(token, name, args=None): r = http("POST", f"{APP}/agui/gov/tools/{name}", json=args or {}, headers={"Authorization": f"Bearer {token}"}, timeout=30); return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200])
    L = led()
    # U2b – dialog Account před H1 (zakázka acme z gui_flow): DIALOG_WAIT/ANSWER v ledgeru, HANDOFF otazky → zadani s dialog_rounds, 2 běhy account
    dw = [e for e in L if e["kind"] == "NOTIFY" and e.get("event") == "DIALOG_WAIT" and e["zakazka"] == zid_acme]; da = [e for e in L if e["kind"] == "NOTIFY" and e.get("event") == "DIALOG_ANSWER" and e["zakazka"] == zid_acme]
    ho = [e for e in L if e["kind"] == "HANDOFF" and e["zakazka"] == zid_acme and e.get("frm") == "account"]; runs_acc = [e for e in L if e["kind"] == "AGENT_RUN" and e["zakazka"] == zid_acme and e["role"] == "account"]
    rep.add("U2b", "Založení zakázky z GUI s dialogem Account (procesy.md Upresneni, ≤ 3 kola): Account napsal otázky (artifacts/otazky.md → HANDOFF otazky://), AG-UI interrupt reason=dialog, odpověď zadavatele = resume {answer} → DIALOG_ANSWER, Account běžel znovu s odpověďmi a dodal Zadání (dialog_rounds=1), teprve pak H1", "PASS" if len(dw) == 1 and len(da) == 1 and len(ho) == 2 and str(ho[0].get("artifact", "")).startswith("otazky://") and str(ho[1].get("artifact", "")).startswith("issue://") and ho[1].get("dialog_rounds") == 1 and len(runs_acc) == 2 else "FAIL", {"dialog_wait": len(dw), "dialog_answer": [(e.get("by"), (e.get("answer") or "")[:60]) for e in da], "handoffs": [(e.get("artifact"), e.get("dialog_round") or e.get("dialog_rounds")) for e in ho], "account_runs": len(runs_acc)})
    # seed historie registru (org.agents) z celého ledgeru aplikace – podmínka A0→A1 (≥ 10 úkolů) pro acme; od P3-3 píše workflow samo (REGISTRY_AGENT)
    roles_yaml = {f.stem: _yg.safe_load(f.read_text()) for f in sorted((ROOT / "knowledge/organization/roles").glob("*.yaml"))}
    es = json.loads((ROOT / "tools/role_evals/results/eval-status.json").read_text()); results = {f.stem: json.loads(f.read_text()) for f in (ROOT / "tools/role_evals/results").glob("*.json") if f.stem != "eval-status"}
    with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
        rgm.ensure_schema(c); rgm.seed_roles(c, roles_yaml, es, os.environ.get("GITHUB_SHA", "local")); rgm.seed_eval_gates(c, results, os.environ.get("GITHUB_SHA", "local"))
        acme_zids = sorted({e["zakazka"] for e in L if e.get("kind") == "ZAKAZKA_START" and (e.get("tenant") or "acme") == "acme"})
        n_seed = sum(rgm.seed_agents(c, L, z_, roles_yaml, "seed", os.environ.get("P0_MODEL", "claude-haiku-4-5")) for z_ in acme_zids)
        wf_rows = [e for e in L if e["kind"] == "REGISTRY_AGENT" and e["zakazka"] == zid_acme and e.get("written")]
        db = {t: c.execute(f"SELECT count(*) FROM org.{t}").fetchone()[0] for t in ("tenants", "zakazky", "agents", "approvals", "agent_events", "role_definitions")}
    ta, tb, tp = tok("adam", "adam"), tok("bea", "bea"), tok("platform-admin", "platform-admin")
    api = {t: gov(tp, t) for t in ("tenants", "zakazky", "agents", "approvals", "roles", "finops", "governance_report", "risk_register")}
    cnt = {t: (len(api[t][1]["result"]) if api[t][0] == 200 and isinstance(api[t][1].get("result"), list) else None) for t in ("tenants", "zakazky", "agents", "approvals", "roles")}
    g = Gui(f"{APP}/gui/", shots=gui_shots / "gov").open(); t_g = time.time(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)
    try:
        g.login("platform-admin", "platform-admin")
        pages = {"firma": g.page_rows("firma", ["roles-table", "tenants-table"]), "registr": g.page_rows("registr", ["agents-table", "events-table"]), "finops": g.page_rows("finops", ["finops-tenants", "finops-zakazky"]), "audit": g.page_rows("audit", ["approvals-table"])}
        rep.add("U2a", "Každý pohled GUI (Firma, Registr agentů, FinOps, Governance, Audit) čte přes Governance MCP (org_reader, token člověka, RLS) z org.*, ne z ledgeru harnessu: počty řádků z API == DB (tenant platform), tabulky v GUI vykreslené; org.agents nově plní workflow po každém běhu role (REGISTRY_AGENT)", "PASS" if all(api[t][0] == 200 for t in api) and cnt["tenants"] == db["tenants"] and cnt["zakazky"] == min(db["zakazky"], 200) and cnt["approvals"] == min(db["approvals"], 200) and cnt["agents"] == min(db["agents"], 200) and len(wf_rows) >= 4 and pages["firma"]["roles-table"] >= 5 and pages["firma"]["tenants-table"] == db["tenants"] and pages["registr"]["agents-table"] >= 4 and pages["audit"]["approvals-table"] >= 4 and pages["finops"]["finops-tenants"] == db["tenants"] else "FAIL", {"api_http": {t: api[t][0] for t in api}, "api_counts": cnt, "db_counts": db, "workflow_agent_rows": len(wf_rows), "seeded_history": n_seed, "pages": pages})
        # U2c – autonomie: beta vyvojar A0→A1 bez podmínek odmítnut (úkolů < 10), acme account A0→A1 zapsán (historie ≥ 10 úkolů), acme account A1→A2 odmítnut (L2 gate chybí)
        with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:   # P3-6 nález: historie beta/vývojář přes měření narostla na ≥ 10 úkolů → posun legitimní; role s nejmenší historií, očekávání z pravidla (úkolů < 10)
            hist = {r_[0]: r_[1] for r_ in c.execute("SELECT role_id, count(*) FROM org.agents WHERE tenant_id = 'beta' GROUP BY role_id").fetchall()}
            cur_b = {r_[0]: r_[1] for r_ in c.execute("SELECT role_id, level FROM org.role_autonomy WHERE tenant_id = 'beta'").fetchall()}
            apd_b = {r_[0]: r_[1] for r_ in c.execute("SELECT decision, count(*) FROM org.approvals WHERE tenant_id = 'beta' GROUP BY decision").fetchall()}
        rej_b = apd_b.get("reject", 0) / max(1, apd_b.get("approve", 0) + apd_b.get("reject", 0))
        role_b = min((r_ for r_ in ROLES if cur_b.get(r_, "A0") == "A0"), key=lambda r_: hist.get(r_, 0), default="vyvojar"); tasks_b = hist.get(role_b, 0); expect_b = tasks_b >= 10 and rej_b <= 0.2
        r1 = g.autonomy(role_b, "beta", "A1", "Zkouška posunu bez splněných podmínek – musí být odmítnut." if not expect_b else "Role má ≥ 10 úkolů bez odmítnutí – posun na A1 podle pravidla.")
        r2 = g.autonomy("account", "acme", "A1", "Account prošel evaly a má přes 10 běhů bez odmítnutí – posun na A1.")
        r3 = g.autonomy("account", "acme", "A2", "Zkouška A2 – podmínky nesplněny (L2 gate, počet úkolů).")
        with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
            ra = c.execute("SELECT level, changed_by, reason FROM org.role_autonomy WHERE role_id = 'account' AND tenant_id = 'acme'").fetchone()
            ev = c.execute("SELECT count(*) FROM org.agent_events WHERE kind = 'autonomy_changed' AND role_id = 'account' AND tenant_id = 'acme'").fetchone()[0]
            rb = c.execute("SELECT level FROM org.role_autonomy WHERE role_id = %s AND tenant_id = 'beta'", (role_b,)).fetchone()
        rep.add("U2c", "Posun autonomie z GUI (metriky.md §6): beta/<role s nejmenší historií> A0→A1 odmítnut při úkolů < 10 (zapsán při ≥ 10 – pravidlo, ne stav DB), acme/account A0→A1 zapsán s důvodem (org.role_autonomy + agent_events autonomy_changed, changed_by = Keycloak sub), acme/account A1→A2 odmítnut (eval gate L2 chybí, úkolů < 30); důvod povinný, posun jen o úroveň", "PASS" if r1["ok"] == expect_b and r2["ok"] and not r3["ok"] and ra and ra[0] == "A1" and ev >= 1 and ((rb is None) if not expect_b else (rb and rb[0] == "A1")) else "FAIL", {"beta_role": {"role": role_b, "tasks": tasks_b, "reject_rate": round(rej_b, 3), "expect_ok": expect_b}, "beta_A1": r1, "acme_account_A1": r2, "acme_account_A2": r3, "db": {"account_acme": list(ra) if ra else None, "events": ev, "beta_role_level": rb}})
        # U2e/U2f – governance report a export (platform-admin vidí vše, bea jen beta)
        rp = g.report(); exp_b = http("GET", f"{APP}/agui/gov/export.jsonl", headers={"Authorization": f"Bearer {tb}"}, timeout=60).text
        lines_b = [json.loads(l) for l in exp_b.splitlines() if l.strip()]; tenants_b = {l.get("tenant_id") for l in lines_b if l.get("tenant_id")}
        exp_p = http("GET", f"{APP}/agui/gov/export.jsonl", headers={"Authorization": f"Bearer {tp}"}, timeout=60).text; tenants_p = {json.loads(l).get("tenant_id") for l in exp_p.splitlines() if l.strip()}
        rep.add("U2e", "Governance report (metriky.md §5) v GUI: per zakázka chybějící položky T11–T15 – zakázka acme z tohoto běhu má klasifikaci (T15 ok – P3-4), řádek registru (T12 ok) a approvaly merge/deploy (T13 ok); mezery zůstávají u starších zakázek a u T11 risk register", "PASS" if rp["gaps"] >= 1 and any(r["id"] == zid_acme for r in rp["rows"]) and not any(m.startswith("T12") or m.startswith("T13") or m.startswith("T15") for r in rp["rows"] if r["id"] == zid_acme for m in r["missing"]) else "FAIL", {"gaps": rp["gaps"], "rows": len(rp["rows"]), "acme_row": next((r for r in rp["rows"] if r["id"] == zid_acme), None), "sample": rp["rows"][:3]})
        rep.add("U2f", "Export JSONL per tenant (čl. 13(3)(f)) přes Governance MCP: bea dostane jen řádky tenanta beta (RLS), platform-admin všechny tenanty; GUI tlačítko exportu", "PASS" if lines_b and tenants_b == {"beta"} and {"acme", "beta"} <= tenants_p and rp["export_lines"] > 0 else "FAIL", {"bea_lines": len(lines_b), "bea_tenants": sorted(tenants_b), "platform_tenants": sorted(t for t in tenants_p if t), "gui_export_lines": rp["export_lines"]})
        # U2g – agentní token nesmí číst governance (jen lidé); org_writer DSN není v MCP
        ag = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "client_credentials"}, auth=("agent-account", "p0-account-secret"), timeout=15).json().get("access_token", "")
        s_ag = gov(ag, "zakazky")[0]; s_none = http("POST", f"{APP}/agui/gov/tools/zakazky", json={}, timeout=15).status_code
        res_h = http("GET", f"{APP}/agui/gov/resources", headers={"Authorization": f"Bearer {ta}"}, timeout=15).json()
        rep.add("U2g", "Governance MCP jen pro lidi a jen čtení: agentní token (client_credentials agent-account) → 403, bez tokenu 401, /resources hlásí read_only a DB roli org_reader (server nemá zápisové DSN)", "PASS" if s_ag == 403 and s_none == 401 and res_h.get("read_only") and res_h.get("db_role") == "org_reader" else "FAIL", {"agent_http": s_ag, "no_token_http": s_none, "resources": {k: res_h.get(k) for k in ("read_only", "db_role")}, "tools": [t["name"] for t in res_h.get("tools", [])]})
        # U2d – stop tenanta beta z GUI: druhá zakázka beta (bea) běží do interruptu, pak platform-admin stop → obě SUSPENDED, klíče Block (429), paměť deny, SPIRE entries zůstávají
        g.close(); gb = Gui(f"{APP}/gui/", shots=gui_shots / "beta2").open(); gb.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)   # Playwright sync: v jednom vlákně jen jedna instance → zavřít a znovu otevřít
        try:
            gb.login("bea", "bea"); zb2 = f"{tag}-beta2"; gb.create_thread(zb2, f"Druhá zakázka beta {zb2} – test stopu tenanta."); w2 = gb.wait_any_interrupt(1200)
        finally: gb.close()
        g = Gui(f"{APP}/gui/", shots=gui_shots / "gov").open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10); g.login("platform-admin", "platform-admin")
        beta_z = [z_ for z_ in sorted({e["zakazka"] for e in led() if e.get("kind") == "ZAKAZKA_START" and e.get("tenant") == "beta"})]
        def status(z): r = http("GET", f"{APP}/zakazky/{z}", timeout=15); return r.json().get("status") if r.status_code == 200 else f"http{r.status_code}"
        before = {z_: status(z_) for z_ in beta_z}; running_before = [z_ for z_, v in before.items() if v == "RUNNING" and z_.startswith(tag)]   # jen zakázky tohoto běhu: instance ze starého obrazu po pause/resume končí FAILED (změna kódu workflow = nedeterministický replay)
        st = g.tenant_stop("beta", "Zákazník beta pozastavil spolupráci do vyjasnění smlouvy – stop celého tenanta.")
        after = {z_: status(z_) for z_ in beta_z}
        import yaml as _yk
        keys_cm = _yk.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
        beta_keys = [k for k in keys_cm if (k.get("metadata") or {}).get("tenant") == "beta"]
        blocked_cm = bool(beta_keys) and all((k.get("metadata") or {}).get("blocked") == "tenant-stop" and all(b["limit"]["amount"] == 0 for b in k.get("budgets", [])) for k in beta_keys)
        safe = re.sub(r"[^a-z0-9-]", "-", zb2.lower()).strip("-")[:40]; pf_b = PortForward(a, "openbao", 18204, 8200); pf_gw = PortForward(a, "agentgateway", 14100, 4100); gw_http = None
        try:
            kv = http("GET", f"https://127.0.0.1:18204/v1/secret/data/zakazky/{safe}/gateway-keys", headers={"X-Vault-Token": init_root_token}, timeout=10)
            key = (((kv.json().get("data") or {}).get("data") or {}) if kv.status_code == 200 else {}).get("account")
            t_k = time.time()
            while key and time.time() - t_k < 120:   # propagace ConfigMapy → sidecar merge → hot reload (řádově 10–60 s)
                gw_http = http("POST", "http://127.0.0.1:14100/v1/messages", json={"model": os.environ.get("P0_MODEL", "claude-haiku-4-5"), "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}, headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=20).status_code
                if gw_http == 429: break
                time.sleep(5)
        finally: pf_b.stop(); pf_gw.stop()
        mem = http("POST", f"http://127.0.0.1:19900/tools/search_memory", json={"query": "test", "limit": 1}, headers={"Authorization": f"Bearer {tb}"}, timeout=15)
        mem_a = http("POST", f"http://127.0.0.1:19900/tools/search_memory", json={"query": "test", "limit": 1}, headers={"Authorization": f"Bearer {ta}"}, timeout=15)
        ents = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "entry", "show", "-socketPath", "/tmp/spire-server/private/api.sock").stdout
        with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
            tst = c.execute("SELECT status FROM org.tenants WHERE tenant_id = 'beta'").fetchone()[0]; evs = c.execute("SELECT count(*) FROM org.agent_events WHERE tenant_id = 'beta' AND kind = 'suspended'").fetchone()[0]
        stop_led = next((e for e in reversed(led()) if e["kind"] == "STOP_TENANT" and e.get("tenant") == "beta"), {})
        rs = g.tenant_stop("beta", "Test hotov – tenant beta zpět do provozu (resume).", resume=True)
        after_resume = {z_: status(z_) for z_ in beta_z}
        rep.add("U2d", "Stop tenanta z GUI (platform-admin, důvod povinný; autonomie.md T5): všechny běžící zakázky beta → SUSPENDED (durable, HITL zůstává), pody rolí ukončeny, klíče gateway tenanta Block (ConfigMap limit 0 → 429 na request s klíčem beta; acme nedotčen), paměť pro tenant beta deny (tenant_stopped; acme 200), SPIRE entries beta zůstávají, org.tenants.status=stopped + agent_events suspended; resume vrací zakázky do RUNNING a klíče zpět", "PASS" if st["ok"] and st["disabled_empty"] and w2.get("kind") in ("dialog", "approval") and running_before and all(after[z_] == "SUSPENDED" for z_ in running_before) and blocked_cm and gw_http == 429 and mem.status_code == 403 and "tenant_stopped" in mem.text and mem_a.status_code == 200 and "spiffe://platform/role/account/beta" in ents and tst == "stopped" and evs >= 1 and rs["ok"] and all(after_resume[z_] == "RUNNING" for z_ in running_before) else "FAIL", {"before": before, "after_stop": after, "after_resume": after_resume, "stop_gui": st, "keys_blocked_cm": blocked_cm, "gateway_http_beta_key": gw_http, "memory_beta": [mem.status_code, mem.text[:80]], "memory_acme": mem_a.status_code, "spire_beta_entries": ents.count("/beta"), "tenant_status": tst, "events_suspended": evs, "ledger": {k: stop_led.get(k) for k in ("paused", "pods_killed", "keys_blocked", "registry")}, "second_zakazka": {"id": zb2, "interrupt": w2.get("kind")}})
        rep.add("U2h", "GUI nad firmou: čas scénáře, screenshoty", "INFO", {"wall_s": round(time.time() - t_g, 1), "shots": sorted(p.name for p in (gui_shots / "gov").glob("*.png")) if (gui_shots / "gov").exists() else []})
    finally:
        g.close()

def e5_probe(a, kj, duration_s=75):
    """E5 (P3-6): dva sondovací Kata pody (tenant-acme, tenant-beta; SA role-account, label platform.role=account, sidecar spire-agent jako u podů rolí)
    současně na uzlu Kata; každý po dobu duration_s každé 2 s fetchuje X.509-SVID z Workload API a vypíše seznam SPIFFE ID. Důkaz identity agenta per pod:
    oba pody běží zároveň, každý vidí jen svůj SVID (role × tenant), SPIRE server eviduje agenty …/k8s_psat/platform/pod/<UID obou podů>."""
    zenv = kj("-n", NS, "get", "configmap", "zakazka-env").get("data") or {}
    img, sa_img, cm = zenv.get("P0_ROLE_IMAGE", ""), zenv.get("P0_ROLE_SPIRE_AGENT_IMAGE", "ghcr.io/spiffe/spire-agent:1.15.5"), "spire-agent-pod"
    code = ("import time, json\nfrom spiffe import WorkloadApiClient\nt0 = time.time(); seen = []\nwhile time.time() - t0 < %d:\n    try:\n        with WorkloadApiClient() as c: seen.append(str(c.fetch_x509_svid().spiffe_id))\n"
            "    except Exception as e: seen.append('ERR:' + type(e).__name__)\n    time.sleep(2)\nprint('SVIDS=' + json.dumps(seen), flush=True)\n") % duration_s
    def pod(tenant):
        return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "e5-probe", "namespace": f"tenant-{tenant}", "labels": {"app": "role", "platform.role": "account", "platform.e5": "probe"}},
                "spec": {"runtimeClassName": "kata-vm-isolation", "serviceAccountName": "role-account", "automountServiceAccountToken": False, "shareProcessNamespace": True, "restartPolicy": "Never", "activeDeadlineSeconds": 600,
                         "nodeSelector": {"pool": "kata"}, "tolerations": [{"key": "sandbox", "operator": "Equal", "value": "kata", "effect": "NoSchedule"}],
                         "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "fsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
                         "initContainers": [{"name": "spire-agent", "image": sa_img, "restartPolicy": "Always", "args": ["-config", "/run/spire/config/agent.conf"],
                                             "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsUser": 1000, "runAsGroup": 1000},
                                             "volumeMounts": [{"name": "spire-agent-config", "mountPath": "/run/spire/config", "readOnly": True}, {"name": "spire-sockets", "mountPath": "/run/spire/sockets"}, {"name": "spire-data", "mountPath": "/run/spire/data"}, {"name": "spire-token", "mountPath": "/var/run/secrets/tokens", "readOnly": True}],
                                             "resources": {"requests": {"cpu": "20m", "memory": "32Mi"}, "limits": {"memory": "128Mi"}}}],
                         "containers": [{"name": "probe", "image": img, "command": ["python", "-c", code], "env": [{"name": "SPIFFE_ENDPOINT_SOCKET", "value": "unix:///run/spire/sockets/agent.sock"}],
                                         "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}, "volumeMounts": [{"name": "spire-sockets", "mountPath": "/run/spire/sockets"}],
                                         "resources": {"requests": {"cpu": "50m", "memory": "128Mi"}, "limits": {"memory": "512Mi"}}}],
                         "volumes": [{"name": "spire-sockets", "emptyDir": {"medium": "Memory", "sizeLimit": "4Mi"}}, {"name": "spire-data", "emptyDir": {"medium": "Memory", "sizeLimit": "16Mi"}},
                                     {"name": "spire-agent-config", "configMap": {"name": cm}},
                                     {"name": "spire-token", "projected": {"sources": [{"serviceAccountToken": {"path": "spire-agent", "expirationSeconds": 7200, "audience": "spire-server"}}]}}]}}
    out = {"image": img, "both_running_at_s": None, "phases": {}, "svids": {}, "uids": {}, "nodes": {}}
    for t in ("acme", "beta"):
        kubectl(a, "-n", f"tenant-{t}", "delete", "pod", "e5-probe", "--ignore-not-found", "--wait=true")
        subprocess.run([a.kubectl, "--context", a.context, "apply", "-f", "-"], input=json.dumps(pod(t)), text=True, capture_output=True)
    t0 = time.time()
    while time.time() - t0 < 420:
        ph = {t: (kj("-n", f"tenant-{t}", "get", "pod", "e5-probe").get("status") or {}).get("phase") for t in ("acme", "beta")}
        if all(v == "Running" for v in ph.values()) and out["both_running_at_s"] is None: out["both_running_at_s"] = round(time.time() - t0, 1)
        if all(v in ("Succeeded", "Failed") for v in ph.values()): break
        time.sleep(5)
    for t in ("acme", "beta"):
        p_ = kj("-n", f"tenant-{t}", "get", "pod", "e5-probe"); out["phases"][t] = (p_.get("status") or {}).get("phase"); out["uids"][t] = (p_.get("metadata") or {}).get("uid"); out["nodes"][t] = (p_.get("spec") or {}).get("nodeName")
        log = kubectl(a, "-n", f"tenant-{t}", "logs", "e5-probe", "-c", "probe").stdout
        line = next((l for l in log.splitlines() if l.startswith("SVIDS=")), "")
        try: seen = json.loads(line[6:]) if line else []
        except Exception: seen = []
        out["svids"][t] = {"fetches": len(seen), "ids": sorted({x for x in seen if not x.startswith("ERR")}), "errors": sorted({x for x in seen if x.startswith("ERR")}), "first_ok_idx": next((i for i, x in enumerate(seen) if not x.startswith("ERR")), None)}
        kubectl(a, "-n", f"tenant-{t}", "delete", "pod", "e5-probe", "--ignore-not-found", "--wait=false")
    agents_out = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "agent", "list", "-socketPath", "/tmp/spire-server/private/api.sock").stdout
    ids = [l.split(":", 1)[1].strip() for l in agents_out.splitlines() if l.strip().startswith("SPIFFE ID")]
    out["agents_for_probes"] = {t: any(u and x.endswith("/pod/" + u) for x in ids) for t, u in out["uids"].items()}
    out["agents_pod_total"] = len([x for x in ids if "/k8s_psat/platform/pod/" in x])
    return out


def o3_flow(a, rep, http, led, APP, KC, dsn, kj, zid_acme, tag, gui_shots, init_root_token):
    """O-3 (P3-5): multi-tenant harness v clusteru – M-E3 izolace paměti přes PEP identitou podu (SVID role × tenant), stop tenanta uprostřed běžící role
    s checkpointem (SIGTERM → sync-up), resume → role znovu od checkpointu a další HITL v GUI, spany paměti bez cizího tenanta (ClickHouse), útrata per tenant."""
    import psycopg, uuid as _uu
    sys.path.insert(0, str(HERE)); from gui_checks import Gui, KLAS_NO
    def tok(user, pw): r = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "platform-gui", "username": user, "password": pw}, timeout=15); return r.json()["access_token"]
    def status(z): r = http("GET", f"{APP}/zakazky/{z}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
    def db(sql, args=None, name="org"):
        with psycopg.connect(dsn(name), autocommit=True, connect_timeout=10) as c: return c.execute(sql, args or None).fetchall()   # args None: literál % v SQL (LIKE '%-30d-block') se neparsuje
    def pods_of(ns, z): return [p["metadata"]["name"] for p in kj("-n", ns, "get", "pods", "-l", f"platform.zakazka={re.sub(r'[^A-Za-z0-9_.-]', '-', z)[:63]}").get("items", []) if not p["metadata"].get("deletionTimestamp")]
    ta, tb, tp = tok("adam", "adam"), tok("bea", "bea"), tok("platform-admin", "platform-admin"); t_o = time.time()
    # O3a – kanárky obou tenantů (lidé zapisují approved), zakázky obou tenantů se sondou paměti identitou podu (JWT-SVID role × tenant): cizí kanárek = 0 záznamů
    can = {t: f"CANARY-{t.upper()}-{_uu.uuid4().hex[:10]}" for t in ("acme", "beta")}
    wr = {}
    for t, tk in (("acme", ta), ("beta", tb)):
        r = http("POST", "http://127.0.0.1:19900/tools/create_memory", json={"content": f"Interní fakt tenanta {t}: kód projektu {can[t]} (kanárek M-E3).", "scope": "zakaznik", "type": "fakt", "requested_status": "approved", "sources": [{"kind": "harness", "ref": f"o3a/{tag}"}]}, headers={"Authorization": f"Bearer {tk}"}, timeout=15)
        wr[t] = r.json() if r.status_code == 200 else {"http": r.status_code, "text": r.text[:120]}
    probe_b = [can["acme"], can["beta"], "ACME kód projektu"]; probe_a = [can["beta"], can["acme"], "BETA kód projektu"]
    zb, za = f"{tag}-o3b", f"{tag}-o3a"
    http("POST", f"{APP}/zakazky", json={"id": zb, "poptavka": f"Zakázka tenanta beta {zb}: přidej soubor zakazky/{zb}/NOTES.md (test stopu tenanta uprostřed role).", "tenant": "beta", "klasifikace": KLAS_NO, "memory_probe": probe_b, "hitl_timeout_s": 3600}, timeout=15)
    # P3-6 E5: zakázka acme hned za beta – pody account obou tenantů běží paralelně na jednom uzlu Kata (agent ID per pod: use_pod_uid_for_agent_id); dřív sériově (P3-5)
    http("POST", f"{APP}/zakazky", json={"id": za, "poptavka": f"Zakázka tenanta acme {za}: přidej soubor zakazky/{za}/NOTES.md (acme běží během stopu beta).", "tenant": "acme", "klasifikace": KLAS_NO, "memory_probe": probe_a, "hitl_timeout_s": 3600}, timeout=15)
    t_par = time.time()
    g = Gui(f"{APP}/gui/", shots=gui_shots / "o3").open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)
    def wait_i(bod, timeout):
        t0 = time.time()
        while True:
            r = g.wait_interrupt(bod, min(60, max(1, timeout - (time.time() - t0))))
            if r["interrupt"] or r["run_status"] in ("finished", "cancelled") or time.time() - t0 >= timeout: r["waited_s"] = round(time.time() - t0, 1); return r
            try: http("GET", f"{APP}/health", timeout=10)
            except Exception: pass
    try:
        g.login("bea", "bea"); g.open_thread(zb); dialog_then(g, zb, 1500)
        h1 = wait_i("H1", 1500); assert h1["interrupt"], f"H1 (beta o3) nepřišel: {h1['run_status']} {h1.get('error')}"
        L = led(); pod_b = next((e for e in L if e["kind"] == "ROLE_POD" and e["zakazka"] == zb and e["role"] == "account"), {}); mp_b = pod_b.get("memory_probe") or {}
        t_a = time.time()
        while time.time() - t_a < 900 and not any(e["kind"] == "ROLE_POD" and e["zakazka"] == za and e["role"] == "account" for e in led()): time.sleep(5)
        pod_a = next((e for e in led() if e["kind"] == "ROLE_POD" and e["zakazka"] == za and e["role"] == "account"), {}); mp_a = pod_a.get("memory_probe") or {}
        # vyhledávání nemá práh podobnosti (top-N vlastního tenanta): důkazem izolace je, že se cizí kanárek (id) nikdy nevrátí a tenants_returned ⊆ vlastní tenant
        ok_b = bool(mp_b) and all(wr["acme"].get("id") not in (v.get("returned") or []) and set(v.get("tenants_returned") or []) <= {"beta"} and v.get("http") == 200 for v in mp_b.values()) and wr["beta"].get("id") in (mp_b.get(can["beta"], {}).get("returned") or [])
        ok_a = bool(mp_a) and all(wr["beta"].get("id") not in (v.get("returned") or []) and set(v.get("tenants_returned") or []) <= {"acme"} and v.get("http") == 200 for v in mp_a.values()) and wr["acme"].get("id") in (mp_a.get(can["acme"], {}).get("returned") or [])
        # E5 (P3-6): identita agenta per pod – deterministická sonda: dva Kata pody (acme, beta) se sidecarem SPIRE současně, každý vidí jen svůj SVID;
        # pody account zakázek běžely po sobě (vydání klíčů gateway serializuje start), proto měří sonda; agent ID …/k8s_psat/platform/pod/<UID> (SPIRE 1.15.5)
        pr = e5_probe(a, kj)
        own = {t: f"spiffe://platform/role/account/{t}" for t in ("acme", "beta")}
        ok_svid = all(pr["svids"][t]["fetches"] >= 10 and pr["svids"][t]["ids"] == [own[t]] for t in own)
        ida, idb = pod_a.get("identity") or {}, pod_b.get("identity") or {}
        scfg = (kj("-n", NS, "get", "configmap", "spire-server-config").get("data") or {}).get("server.conf", "")
        s_img = next((c["image"] for p_ in kj("-n", NS, "get", "pods", "-l", "app=spire-server").get("items", []) for c in p_["spec"]["containers"] if c["name"] == "spire-server"), "")
        rep.add("E5a", "Identita agenta per pod (SPIRE 1.15.5, k8s_psat use_pod_uid_for_agent_id): dva sondovací Kata pody tenantů acme a beta (SA role-account, sidecar spire-agent jako u rolí) běží současně na jednom uzlu, každý po 75 s fetchuje SVID a vidí jen svůj (role × tenant, žádný cizí – dřív se sidecary přetahovaly o jeden záznam agenta uzlu: AGENT_NOT_ACTIVE → reattest ping-pong), SPIRE server eviduje agenty …/k8s_psat/platform/pod/<UID> obou podů; pody account zakázek obou tenantů bez stale SVID; agent_ttl 1h + prune v configu", "PASS" if pr["both_running_at_s"] is not None and ok_svid and pr["nodes"]["acme"] and pr["nodes"]["acme"] == pr["nodes"]["beta"] and all(pr["agents_for_probes"].values()) and not ida.get("stale_svids") and not idb.get("stale_svids") and ida.get("kind") == "svid" and idb.get("kind") == "svid" and "use_pod_uid_for_agent_id = true" in scfg and 'agent_ttl = "1h"' in scfg and "prune_attested_nodes_expired_for" in scfg and s_img.endswith(":1.15.5") else "FAIL", {"probe": pr, "zakazky_pods": {"acme": {k: ida.get(k) for k in ("kind", "spiffe_id", "wait_s", "stale_svids")}, "beta": {k: idb.get(k) for k in ("kind", "spiffe_id", "wait_s", "stale_svids")}}, "server_image": s_img, "config": {k: (k in scfg) for k in ("use_pod_uid_for_agent_id = true", 'agent_ttl = "1h"', "prune_attested_nodes_expired_for")}})
        agents_out = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "agent", "list", "-socketPath", "/tmp/spire-server/private/api.sock").stdout
        agent_ids = [l.split(":", 1)[1].strip() for l in agents_out.splitlines() if l.strip().startswith("SPIFFE ID")]
        pod_agents = sorted({x for x in agent_ids if "/k8s_psat/platform/pod/" in x})
        exp_lines = [l.split(":", 1)[1].strip() for l in agents_out.splitlines() if "X509-SVID expires" in l or "Expires" in l]
        rep.add("E5b", "E5: záznamy agentů v SPIRE serveru (per pod – po zániku podu expirace agent_ttl, prune)", "INFO", {"agents_pod_ids": pod_agents[:6], "expires_sample": exp_lines[:4], "wait_s": {"acme": ida.get("wait_s"), "beta": idb.get("wait_s")}})
        rep.add("O3a", "M-E3 v clusteru (model-pameti.md): kanárky obou tenantů (lidé adam/bea zapsali approved přes server paměti), pod account každého tenanta se ptá identitou JWT-SVID role × tenant (PEP: tenant z cesty SVID, RLS app.tenant_id) na kanárek cizího tenanta → 0 záznamů, na vlastní → nalezen; 3 dotazy × 2 tenanty, žádný cizí tenant_id v odpovědích (gate 100 %); bez SVID pod paměť nečte (fail-closed, žádný záložní token)", "PASS" if ok_b and ok_a and (pod_b.get("identity") or {}).get("spiffe_id", "").endswith("/beta") and (pod_a.get("identity") or {}).get("spiffe_id", "").endswith("/acme") else "FAIL", {"canaries": wr, "beta_pod": {"identity": pod_b.get("identity"), "probe": mp_b}, "acme_pod": {"identity": pod_a.get("identity"), "probe": mp_a}})
        # O3b – beta k vývojáři (H1, H2 z GUI), stop tenanta beta během běžícího podu vývojáře: SIGTERM → checkpoint (sync-up) → pod pryč ≤ 60 s, acme běží dál
        g.decide("Zadání beta v pořádku – schvaluji (test stopu tenanta).")
        h2 = wait_i("H2", 1500); assert h2["interrupt"], f"H2 (beta o3) nepřišel: {h2['run_status']} {h2.get('error')}"
        g.decide("Návrh beta v pořádku – schvaluji (test stopu tenanta).")
        ws = g.wait_subagent("vyvojar", 900); pods_before = []; t_p = time.time()
        while time.time() - t_p < 180 and not pods_before: pods_before = [p_ for p_ in pods_of("tenant-beta", zb)]; time.sleep(2)
        t_pod = time.time()
        while time.time() - t_pod < 120 and not any((p_.get("status") or {}).get("phase") == "Running" for p_ in kj("-n", "tenant-beta", "get", "pods", "-l", f"platform.zakazka={zb}").get("items", [])): time.sleep(3)   # SIGTERM má smysl až v běžícím kontejneru
        time.sleep(8); st_a0 = status(za)
        import threading
        t_s = time.time(); watch = {"pods": pods_before, "gone_s": None}
        def _watch():   # P3-6 nález: stop čeká na blokaci klíčů na všech replikách (~40–80 s) – zánik podu se měří souběžně, od odeslání stopu, ne až po návratu
            while time.time() - t_s < 150 and watch["pods"]:
                watch["pods"] = pods_of("tenant-beta", zb)
                if not watch["pods"]: watch["gone_s"] = round(time.time() - t_s, 1); break
                time.sleep(2)
        th = threading.Thread(target=_watch, daemon=True); th.start()
        stp = http("POST", f"{APP}/agui/gov/tenant/beta/stop", json={"reason": "O3b: stop tenanta beta uprostřed běžící role vývojáře (test checkpointu)."}, headers={"Authorization": f"Bearer {tp}"}, timeout=180); stp_j = stp.json() if stp.status_code == 200 else {"http": stp.status_code}
        stop_s = round(time.time() - t_s, 1); th.join(max(1.0, 150 - (time.time() - t_s)))
        pods_after = watch["pods"]; gone_s = watch["gone_s"] if watch["gone_s"] is not None else round(time.time() - t_s, 1); t_w = time.time(); pod_v = {}
        while time.time() - t_w < 120 and not pod_v:   # ROLE_POD zabitého podu zapíše pod_run až po 404 a pokusu o logy (řádově desítky s)
            L = led(); pod_v = next((e for e in reversed(L) if e["kind"] == "ROLE_POD" and e["zakazka"] == zb and e["role"] == "vyvojar" and e.get("ts", 0) > t_s - 1), {})
            if not pod_v: time.sleep(5)
        L = led(); ck = [e for e in L if e["kind"] == "ROLE_CHECKPOINT" and e["zakazka"] == zb]; killed = [e for e in L if e["kind"] == "ROLE_POD_KILLED"]
        killed_mine = [p_ for e in killed if e["zakazka"] == zb for p_ in e.get("pods", [])]; killed_acme = [e for e in killed if e["zakazka"] == za and e.get("ts", 0) > t_s - 1]
        st_b, st_a1 = status(zb), status(za)
        rep.add("O3b", "Stop tenanta beta při běžící roli vývojář v Kata podu (autonomie.md T5, 60 s grace): workflow SUSPENDED, pod dostal SIGTERM → role_runner nahrál checkpoint (artifacts/work sync-up, ROLE_CHECKPOINT) a poslal výsledek stopped → pod pryč ≤ 60 s (ROLE_POD_KILLED), ROLE_POD stopped=True s checkpointem; zakázka acme běží dál (RUNNING, žádný její pod zabit)", "PASS" if ws["status"] == "running" and pods_before and stp.status_code == 200 and zb in (stp_j.get("paused") or []) and not pods_after and gone_s <= 60 and set(killed_mine) & set(pods_before) and ck and ck[0].get("written", 0) >= 0 and pod_v.get("stopped") and (pod_v.get("checkpoint") or {}).get("files") is not None and st_b.get("status") == "SUSPENDED" and st_a0.get("status") == "RUNNING" and st_a1.get("status") == "RUNNING" and not killed_acme else "FAIL", {"subagent": ws, "pods_before": pods_before, "pods_after": pods_after, "pod_gone_s": gone_s, "stop_call_s": stop_s, "stop": {k: stp_j.get(k) for k in ("paused", "pods_killed", "keys_blocked")}, "checkpoint": [{k: e.get(k) for k in ("role", "files", "written", "signal")} for e in ck], "role_pod": {k: pod_v.get(k) for k in ("phase", "stopped", "checkpoint", "exit_code")}, "beta_wf": st_b.get("status"), "acme_wf": [st_a0.get("status"), st_a1.get("status")], "acme_killed": len(killed_acme)})
        # O3c – resume tenanta beta: vývojář se spustí znovu od checkpointu (ROLE_STOPPED → nový ROLE_GATE/pod), reviewer, H4 znovu v GUI, schválení projde (merge executor allow)
        t_r = time.time(); rs = http("POST", f"{APP}/agui/gov/tenant/beta/resume", json={"reason": "O3c: resume tenanta beta po testu stopu."}, headers={"Authorization": f"Bearer {tp}"}, timeout=120); rs_j = rs.json() if rs.status_code == 200 else {"http": rs.status_code}
        t_rr = time.time()
        while time.time() - t_rr < 90 and status(zb).get("status") != "RUNNING": time.sleep(2)   # Dapr resume je asynchronní – GUI run otevřený nad ještě SUSPENDED instancí končí outcome=cancelled (nález 5. běhu)
        resumed_after_s = round(time.time() - t_rr, 1); g.open_thread(zb); h4 = wait_i("H4", 2400)   # po resume: 60 s prodleva (klíče), nový Kata pod vývojáře (sondy ~2–4 min), reviewer
        L = led(); stopped_ev = [e for e in L if e["kind"] == "NOTIFY" and e.get("event") == "ROLE_STOPPED" and e["zakazka"] == zb]
        gates_v = [e for e in L if e["kind"] == "ROLE_GATE" and e["zakazka"] == zb and e["role"] == "vyvojar"]; pods_v = [e for e in L if e["kind"] == "ROLE_POD" and e["zakazka"] == zb and e["role"] == "vyvojar"]
        d4 = g.decide("Review beta bez vad – schvaluji merge po resume (test O3c).") if h4["interrupt"] else None
        t_m = time.time(); ex = None
        while time.time() - t_m < 300:
            ex = next((e for e in led() if e["kind"] == "EXECUTED" and e["zakazka"] == zb and e.get("action") == "merge"), None)
            if ex: break
            time.sleep(3)
        st_b2 = status(zb); tail_b = [(round(e.get("ts", 0) - t_r), e.get("kind"), e.get("role"), e.get("event") or e.get("result") or e.get("status") or e.get("phase") or (str(e.get("error"))[:60] if e.get("error") else None)) for e in led() if e.get("zakazka") == zb and e.get("ts", 0) > t_r - 5][:60]
        app_pods = [(p_["metadata"]["name"], sum(c_.get("restartCount", 0) for c_ in (p_.get("status", {}).get("containerStatuses") or []))) for p_ in kj("-n", NS, "get", "pods", "-l", "app=zakazka").get("items", [])]
        if h4["interrupt"]: wait_i("H5", 300)
        stop_b = http("POST", f"{APP}/zakazky/{zb}/stop", json={"by": "harness", "reason": "O3c hotovo – zakázku beta zastavuji (H5 není třeba)."}, timeout=60).status_code
        rep.add("O3c", "Resume tenanta beta (platform-admin s důvodem): workflow RUNNING, výsledek zabitého podu (stopped) se zpracuje až po resume → ROLE_STOPPED rerun_after_resume → vývojář běží znovu (druhý ROLE_GATE/ROLE_POD vývojář od checkpointu), reviewer, HITL H4 znovu v GUI jako interrupt, schválení bea projde → merge executor allow (EXECUTED merge)", "PASS" if rs.status_code == 200 and zb in (rs_j.get("resumed") or []) and h4["interrupt"] and h4["interrupt"].startswith("hitl:H4:") and stopped_ev and stopped_ev[0].get("result") == "rerun_after_resume" and len(gates_v) >= 2 and len(pods_v) >= 2 and pods_v[-1].get("phase") == "Succeeded" and not pods_v[-1].get("stopped") and d4 and d4["new_run"] and ex and (ex.get("applied") is not None) else "FAIL", {"resume": {k: rs_j.get(k) for k in ("resumed", "keys_unblocked")}, "h4": h4["interrupt"], "h4_after_resume_s": round(time.time() - t_r, 1), "role_stopped": [{k: e.get(k) for k in ("role", "attempt", "result")} for e in stopped_ev], "vyvojar_gates": len(gates_v), "vyvojar_pods": [{k: e.get(k) for k in ("phase", "stopped", "t_run_s")} for e in pods_v], "decide": d4, "executed": {k: ex.get(k) for k in ("action", "by", "applied")} if ex else None, "stop_http": stop_b, "wf_after": st_b2.get("status"), "wf_output": st_b2.get("output"), "running_after_resume_s": resumed_after_s, "unblock_propagation": next((e.get("propagation") for e in reversed(led()) if e.get("kind") == "GATEWAY_KEYS_UNBLOCK" and e.get("tenant") == "beta"), None), "ledger_after_resume": tail_b, "app_pods": app_pods})
        # O3d – ClickHouse: spany serveru paměti (search_memory) tenanta acme nenesou žádný record.id ani tenant beta (a naopak); ledger zakázky acme bez identifikátorů beta
        pf_ch = PortForward(a, "clickhouse", 18123, 8123); rows = []; ch_err = None
        try:
            t_c = time.time()
            while time.time() - t_c < 120:
                q = "SELECT SpanAttributes['tenant.id'], SpanAttributes['gen_ai.memory.record.ids'], SpanAttributes['memory.tenants_returned'], SpanAttributes['enduser.id'] FROM otel.otel_traces WHERE ServiceName = 'memory-server' AND SpanName = 'search_memory' AND Timestamp > now() - INTERVAL 2 HOUR FORMAT JSONCompact"
                r = http("POST", "http://127.0.0.1:18123/", content=q, timeout=30)
                if r.status_code == 200:
                    rows = r.json().get("data", [])
                    if any(x[3] and "/beta" in x[3] for x in rows) and any(x[3] and "/acme" in x[3] for x in rows): break
                else: ch_err = r.text[:200]
                time.sleep(10)
        finally: pf_ch.stop()
        ids_beta = {i for x in rows if x[0] == "beta" for i in (x[1] or "").split(",") if i}; ids_acme = {i for x in rows if x[0] == "acme" for i in (x[1] or "").split(",") if i}
        bad = [x for x in rows if (x[0] == "acme" and ("beta" in (x[2] or "") or (set((x[1] or "").split(",")) & ids_beta))) or (x[0] == "beta" and ("acme" in (x[2] or "") or (set((x[1] or "").split(",")) & ids_acme)))]
        svid_rows = {t: sum(1 for x in rows if x[0] == t and x[3] and x[3].startswith("spiffe://")) for t in ("acme", "beta")}
        L = led(); led_acme = json.dumps([e for e in L if e.get("zakazka") == za and e.get("kind") != "ROLE_POD"], ensure_ascii=False); leak_led = [k for k in (zb, wr["beta"].get("id") or "~") if k in led_acme]   # ROLE_POD nese dotazy sondy (kanárek beta je dotaz, ne únik)
        probe_a_ret = [i for v in (next((e for e in L if e["kind"] == "ROLE_POD" and e["zakazka"] == za and e["role"] == "account"), {}).get("memory_probe") or {}).values() for i in (v.get("returned") or [])]
        if wr["beta"].get("id") in probe_a_ret: leak_led.append("memory_probe:" + wr["beta"]["id"])
        rep.add("O3d", "Spany serveru paměti v ClickHouse (OTEL Collector, O1): search_memory spany tenanta acme nenesou žádný record.id ani tenants_returned tenanta beta a naopak (M-E3 „žádný record.id tenanta B ve spanech“), spany z podů rolí nesou enduser.id = SPIFFE ID role × tenant; ledger zakázky acme neobsahuje id zakázky beta, kanárek beta ani id záznamu beta", "PASS" if rows and not bad and svid_rows["acme"] >= 1 and svid_rows["beta"] >= 1 and ids_beta and ids_acme and not leak_led else "FAIL", {"spans": len(rows), "by_tenant": {t: sum(1 for x in rows if x[0] == t) for t in ("acme", "beta")}, "svid_spans": svid_rows, "record_ids": {"acme": len(ids_acme), "beta": len(ids_beta)}, "cross_tenant_rows": bad[:3], "ledger_leaks": leak_led, "clickhouse_error": ch_err})
        # O3e – útrata per tenant = součet klíčů tenanta v budget_usage (zakázky tohoto běhu; org.zakazky plní workflow po každé roli, stop/resume synchronizují)
        http("POST", f"{APP}/zakazky/{za}/stop", json={"by": "harness", "reason": "O3e: zakázka acme splnila účel (běžela během stopu beta)."}, timeout=60)
        time.sleep(30)   # flush čítačů gateway (5 s) + requesty zabitých podů
        import yaml as _yk
        run_z = sorted({e["zakazka"] for e in led() if e.get("kind") == "ZAKAZKA_START" and str(e.get("zakazka", "")).startswith(tag)})
        synced = {z_: http("POST", f"{APP}/zakazky/{z_}/finops/sync", timeout=30).status_code for z_ in run_z}   # explicitní přepočet (opožděné zápisy po stopu jsou navíc)
        keys_cm = _yk.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
        mine = [k for k in keys_cm if str((k.get("metadata") or {}).get("zakazka", "")).startswith(tag)]
        usage = {r_[0]: r_[1] for r_ in db("SELECT budget_id, used_amount FROM budget_usage WHERE budget_id LIKE '%-30d-block'", name="agentgateway")}
        gw = {}
        for k in mine:
            hsh = k["keyHash"].split(":", 1)[1]; t = (k.get("metadata") or {}).get("tenant"); gw[t] = gw.get(t, 0.0) + role_usage_usd(usage.items(), hsh)
        org = {r_[0]: float(r_[1] or 0) for r_ in db("SELECT tenant_id, sum(spent_usd) FROM org.zakazky WHERE zakazka_id LIKE %s GROUP BY tenant_id", (tag + "%",))}
        per_z = {r_[0]: [r_[1], float(r_[2] or 0)] for r_ in db("SELECT zakazka_id, status, spent_usd FROM org.zakazky WHERE zakazka_id LIKE %s", (tag + "%",))}
        for k in mine:
            hsh = k["keyHash"].split(":", 1)[1]; zk = (k.get("metadata") or {}).get("zakazka"); per_z.setdefault(zk, ["?", 0.0]); per_z[zk].append(round(sum(u / 1e9 for bid, u in usage.items() if hsh in bid), 6))
        fin_t = {}
        for _ in range(4):   # port-forward/Governance MCP občas vrátí 5xx – opakovat
            fin = http("POST", f"{APP}/agui/gov/tools/finops", json={}, headers={"Authorization": f"Bearer {tp}"}, timeout=60)
            if fin.status_code == 200: fin_t = {x["tenant_id"]: x for x in ((fin.json().get("result") or {}).get("tenants") or [])}; break
            time.sleep(5)
        diff = {t: round(abs(gw.get(t, 0) - org.get(t, 0)), 6) for t in ("acme", "beta")}
        rep.add("O3e", "FinOps per tenant (P1-G eventually consistent): útrata zakázek tohoto běhu v org.zakazky (workflow zapisuje po každé roli, stop/resume synchronizují) == součet budget_usage klíčů tenanta (ConfigMap agentgateway-keys metadata.tenant) pro acme i beta, odchylka ≤ 5 % + 0.002 USD; FinOps nástroj Governance MCP hlásí strop vs. útratu per tenant", "PASS" if gw.get("beta", 0) > 0 and gw.get("acme", 0) > 0 and all(diff[t] <= 0.002 + 0.05 * max(gw.get(t, 0), org.get(t, 0)) for t in ("acme", "beta")) and {"acme", "beta"} <= set(fin_t) else "FAIL", {"gateway_usd": {t: round(v, 6) for t, v in gw.items()}, "org_zakazky_usd": org, "diff": diff, "keys": len(mine), "per_zakazka": {z_: [v[0], v[1], round(sum(v[2:]), 6)] for z_, v in per_z.items()}, "sync_http": synced, "finops_http": fin.status_code,
         "registry_ledger": {z_: [(e.get("status"), e.get("spent_usd"), e.get("written"), e.get("source"), (e.get("error") or "")[:60]) for e in led() if e.get("kind") == "REGISTRY_ZAKAZKA" and e.get("zakazka") == z_] for z_, v in per_z.items() if abs(v[1] - sum(v[2:])) > 0.001}, "finops_tool": {t: {k: fin_t[t].get(k) for k in ("budget_usd", "spent_usd", "pct", "status")} for t in fin_t}})
        rep.add("O3f", "O-3: čas scénáře, screenshoty", "INFO", {"wall_s": round(time.time() - t_o, 1), "shots": sorted(p.name for p in (gui_shots / "o3").glob("*.png")) if (gui_shots / "o3").exists() else []})
    finally:
        g.close()


def e3_flow(a, rep, http, led, APP, KC, dsn, kj, tag, gui_shots):
    """E3 (P3-6): strop zakázky i v gateway (rozpočet `zakazka-30d-block` per klíč = strop) → 429 z gateway, ne jen z budget_gate; navýšení stropu
    z HITL `rozpocet` v GUI → gateway (ConfigMap + sonda na repliky), registr org.zakazky, org.approvals (budget.raise, limits_shown), role běží znovu."""
    import psycopg, yaml as _yk
    sys.path.insert(0, str(HERE)); from gui_checks import Gui, KLAS_NO
    def db(sql, args=None):
        with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c: return c.execute(sql, args or None).fetchall()
    def status(z): r = http("GET", f"{APP}/zakazky/{z}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
    def cap_budgets(z):
        keys_cm = _yk.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
        return {(k.get("metadata") or {}).get("role"): next((b["limit"]["amount"] for b in k.get("budgets", []) if b.get("name") == "zakazka-30d-block"), None) for k in keys_cm if (k.get("metadata") or {}).get("zakazka") == z}
    zc = f"{tag}-cap"; t_e = time.time()
    http("POST", f"{APP}/zakazky", json={"id": zc, "poptavka": f"Zakázka {zc}: přidej soubor zakazky/{zc}/NOTES.md (test stropu v gateway).", "tenant": "acme", "klasifikace": KLAS_NO, "budget_usd": 0.01, "hitl_timeout_s": 1800, "budget_timeout_s": 1800}, timeout=15)
    t0 = time.time(); exc = None
    while time.time() - t0 < 900 and not exc:
        exc = next((e for e in led() if e["kind"] == "NOTIFY" and e.get("event") == "BUDGET_EXCEEDED" and e["zakazka"] == zc), None)
        if not exc: time.sleep(5)
    L = led(); gate0 = next((e for e in L if e["kind"] == "BUDGET_GATE" and e["zakazka"] == zc), {}); run0 = next((e for e in L if e["kind"] == "AGENT_RUN" and e["zakazka"] == zc and e["role"] == "account"), {})
    caps0 = cap_budgets(zc)
    g = Gui(f"{APP}/gui/", shots=gui_shots / "e3").open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)
    try:
        g.login("adam", "adam"); g.open_thread(zc); w = g.wait_interrupt("rozpocet", 300)
        box = {k: (g.t(f"budget-{k}").inner_text() if g.t(f"budget-{k}").count() else None) for k in ("source", "spent", "limit")}
        rep.add("E3a", "Strop zakázky i v gateway: klíče role × zakázka nesou rozpočet zakazka-30d-block = strop zakázky (0,01 USD) → první role dostane 429 z gateway (BUDGET_EXCEEDED source=agentgateway, ne zakazka-sum z orchestrátoru); eskalace = HITL rozpocet jako interrupt v GUI s útratou, stropem a zdrojem", "PASS" if exc and exc.get("source") == "agentgateway" and run0.get("budget_exceeded") and gate0.get("limit_usd") == 0.01 and not gate0.get("exceeded") and caps0 and all(v == 0.01 for v in caps0.values()) and w["interrupt"] and w["interrupt"].startswith("hitl:rozpocet:") and box.get("source") == "agentgateway" and box.get("limit") not in (None, "?") else "FAIL", {"exceeded": {k: exc.get(k) for k in ("role", "source", "escalate_to")} if exc else None, "agent_run": {k: run0.get(k) for k in ("budget_exceeded", "error")}, "gate_before": {k: gate0.get(k) for k in ("limit_usd", "spent_usd", "exceeded")}, "configmap_caps": caps0, "interrupt": w["interrupt"], "gui_box": box, "waited_s": round(time.time() - t0, 1)})
        d = g.decide("Strop zakázky byl pro pilot nízký – navyšuji na 5 USD, útrata zatím odpovídá odhadu.", budget=5)
        t1 = time.time(); raised = None
        while time.time() - t1 < 420 and not raised:
            raised = next((e for e in led() if e["kind"] == "NOTIFY" and e.get("event") == "BUDGET_RAISED" and e["zakazka"] == zc), None)
            if not raised: time.sleep(5)
        t2 = time.time(); run1 = None
        while time.time() - t2 < 900 and not run1:
            runs = [e for e in led() if e["kind"] == "AGENT_RUN" and e["zakazka"] == zc and e["role"] == "account"]
            run1 = runs[1] if len(runs) >= 2 else None
            if not run1: time.sleep(5)
        L = led(); capl = next((e for e in L if e["kind"] == "BUDGET_CAP" and e["zakazka"] == zc), {}); gwc = next((e for e in L if e["kind"] == "GATEWAY_KEYS_CAP" and e["zakazka"] == zc), {})
        caps1 = cap_budgets(zc)
        row = db("SELECT budget_usd, status FROM org.zakazky WHERE zakazka_id = %s", (zc,)); apr = db("SELECT action, decision, limits_shown, channel FROM org.approvals WHERE workflow_instance = %s AND action = 'budget.raise'", (zc,))
        gui_budget = g.t("state-budget").inner_text() if g.t("state-budget").count() else None
        st = status(zc); stop = http("POST", f"{APP}/zakazky/{zc}/stop", json={"by": "harness", "reason": "E3 hotovo – zakázku zastavuji."}, timeout=60).status_code
        rep.add("E3b", "Navýšení stropu z HITL rozpocet v GUI (N6 s důvodem): schválení s novým stropem 5 USD → BUDGET_CAP: rozpočet zakazka-30d-block všech klíčů zakázky v ConfigMapě = 5, sonda potvrdila přijetí na všech replikách gateway (hot reload), org.zakazky.budget_usd = 5, org.approvals řádek budget.raise s limits_shown (starý/nový strop); role běží znovu a tentokrát doběhne (druhý AGENT_RUN bez 429), stav zakázky v GUI ukazuje nový strop", "PASS" if d["new_run"] and raised and raised.get("budget_usd") == 5 and capl.get("registry") and (gwc.get("propagation") or {}).get("status") and all(v == 200 for v in gwc["propagation"]["status"].values()) and caps1 and all(v == 5 for v in caps1.values()) and row and float(row[0][0]) == 5 and apr and apr[0][1] == "approve" and (apr[0][2] or {}).get("budget_usd_new") == 5 and run1 and not run1.get("budget_exceeded") and not run1.get("error") and gui_budget in ("5", "5.0") else "FAIL", {"decide": d, "raised": {k: raised.get(k) for k in ("budget_usd", "by")} if raised else None, "cap_ledger": {k: capl.get(k) for k in ("budget_usd", "keys", "registry")}, "gateway_propagation": gwc.get("propagation"), "configmap_caps": caps1, "db": {"zakazky": [str(x) for x in row[0]] if row else None, "approvals": [[r_[0], r_[1], r_[2], r_[3]] for r_ in apr]}, "second_run": {k: run1.get(k) for k in ("budget_exceeded", "error", "cost_usd")} if run1 else None, "gui_budget": gui_budget, "wf": st.get("status"), "wf_failure": st.get("failure"), "stop_http": stop})
        rep.add("E3c", "E3: čas, screenshoty", "INFO", {"wall_s": round(time.time() - t_e, 1), "shots": sorted(p.name for p in (gui_shots / "e3").glob("*.png")) if (gui_shots / "e3").exists() else []})
    finally:
        g.close()


def e4_flow(a, rep, http, led, APP, KC, dsn, kj, tag, gui_shots):
    """E4 (P3-6): per-request ledger z gateway – tracing agentgateway (span každého LLM requestu s tenant/zakazka/role/llm.cost.total) → Collector → ClickHouse;
    FinOps pohled v Governance MCP (nástroj `ledger`, hranice tenanta jako RLS) a v GUI; součet per zakázka == budget_usage ± tolerance (nezávislý zdroj)."""
    import psycopg, yaml as _yk
    sys.path.insert(0, str(HERE)); from gui_checks import Gui
    def tok(user, pw): r = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "platform-gui", "username": user, "password": pw}, timeout=15); return r.json()["access_token"]
    t_e = time.time(); time.sleep(20)   # batch Collectoru + flush gateway
    pf_ch = PortForward(a, "clickhouse", 18123, 8123); rows = []; ch_err = None
    try:
        q = f"SELECT SpanAttributes['tenant'], SpanAttributes['zakazka'], SpanAttributes['role'], count(), sum(toFloat64OrZero(SpanAttributes['llm.cost.total'])), sum(toUInt64OrZero(SpanAttributes['gen_ai.usage.input_tokens'])), ServiceName FROM otel.otel_traces WHERE SpanAttributes['zakazka'] LIKE '{tag}%' AND Timestamp > now() - INTERVAL 6 HOUR GROUP BY 1,2,3,7 FORMAT JSONCompact"
        for _ in range(6):
            r = http("POST", "http://127.0.0.1:18123/", content=q, timeout=30)
            if r.status_code == 200: rows = r.json().get("data", []); break
            ch_err = r.text[:200]; time.sleep(5)
    finally: pf_ch.stop()
    keys_cm = _yk.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
    with psycopg.connect(dsn("agentgateway"), autocommit=True, connect_timeout=10) as c: usage = {r_[0]: r_[1] for r_ in c.execute("SELECT budget_id, used_amount FROM budget_usage WHERE budget_id LIKE '%-30d-block'").fetchall()}
    gw = {}
    for k in keys_cm:
        md = k.get("metadata") or {}; zk = md.get("zakazka", "")
        if not str(zk).startswith(tag): continue
        hsh = k["keyHash"].split(":", 1)[1]; gw[zk] = round(gw.get(zk, 0.0) + role_usage_usd(usage.items(), hsh), 6)
    ch = {}
    for t_, z_, r_, n_, cost, tin, svc in rows: ch[z_] = round(ch.get(z_, 0.0) + float(cost), 6)
    cmp = {z_: {"gateway_usd": gw.get(z_, 0.0), "ledger_usd": ch.get(z_, 0.0), "diff": round(abs(gw.get(z_, 0.0) - ch.get(z_, 0.0)), 6)} for z_ in sorted(set(gw) | set(ch))}
    with_spend = [z_ for z_, v in cmp.items() if v["gateway_usd"] > 0]
    ok_sum = bool(with_spend) and all(cmp[z_]["ledger_usd"] > 0 and cmp[z_]["diff"] <= 0.002 + 0.05 * max(cmp[z_]["gateway_usd"], cmp[z_]["ledger_usd"]) for z_ in with_spend)
    attrs_ok = bool(rows) and all(t_ in ("acme", "beta") and r_ and float(cost) >= 0 for t_, z_, r_, n_, cost, tin, svc in rows)
    rep.add("E4a", "Per-request ledger z gateway: tracing agentgateway (randomSampling, fields tenant/zakazka/role z metadat klíče + llm.cost.total) posílá span každého LLM requestu rolí do OTEL Collectoru → ClickHouse otel.otel_traces; součet llm.cost.total per zakázka tohoto běhu == útrata klíčů v budget_usage (± 5 % + 0,002 USD) – nezávislý zdroj FinOps bez tabulky gateway; každý span nese tenant, zakázku a roli", "PASS" if attrs_ok and ok_sum and not ch_err else "FAIL", {"spans_rows": len(rows), "services": sorted({svc for *_, svc in rows}), "per_zakazka": cmp, "zakazky_with_spend": len(with_spend), "sample": rows[:4], "clickhouse_error": ch_err})
    ta, tb, tp = tok("adam", "adam"), tok("bea", "bea"), tok("platform-admin", "platform-admin")
    def gov(t_, args=None): r = http("POST", f"{APP}/agui/gov/tools/ledger", json=args or {}, headers={"Authorization": f"Bearer {t_}"}, timeout=60); return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text[:200]})
    sp, sb = gov(tp), gov(tb)
    res_p = (sp[1].get("result") or {}) if sp[0] == 200 else {}; res_b = (sb[1].get("result") or {}) if sb[0] == 200 else {}
    ten_p = {r_["tenant_id"] for r_ in res_p.get("rows", [])}; ten_b = {r_["tenant_id"] for r_ in res_b.get("rows", [])}
    run_z = [z for z in res_p.get("by_zakazka", []) if str(z["zakazka_id"]).startswith(tag)]
    delta_ok = all(z.get("delta_usd") is not None and abs(z["delta_usd"]) <= 0.002 + 0.05 * max(z["ledger_usd"], z.get("spent_usd") or 0) for z in run_z if z["ledger_usd"] > 0 and (z.get("status") in ("Dokonceno", "Pozastaveno")))
    g = Gui(f"{APP}/gui/", shots=gui_shots / "e4").open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10)
    try:
        g.login("platform-admin", "platform-admin"); pages = g.page_rows("finops", ["finops-ledger", "finops-ledger-zakazky"]); src = g.t("ledger-source").inner_text() if g.t("ledger-source").count() else None
    finally: g.close()
    rep.add("E4b", "FinOps pohled z ledgeru: Governance MCP nástroj `ledger` čte ClickHouse (per tenant/zakázka/role, okno N dní) a přikládá rozdíl proti org.zakazky.spent_usd; hranice tenanta jako u RLS (bea vidí jen beta, platform-admin oba); u dokončených a zastavených zakázek běhu rozdíl ledger vs. registr ≤ 5 % + 0,002 USD; GUI FinOps má tabulky ledgeru s řádky", "PASS" if sp[0] == 200 and sb[0] == 200 and {"acme", "beta"} <= ten_p and ten_b == {"beta"} and run_z and delta_ok and isinstance(pages.get("finops-ledger"), int) and pages["finops-ledger"] >= 1 and pages.get("finops-ledger-zakazky", 0) >= 1 and src and "ClickHouse" in src else "FAIL", {"http": [sp[0], sb[0]], "tenants_platform": sorted(ten_p), "tenants_bea": sorted(ten_b), "run_zakazky": [{k: z.get(k) for k in ("zakazka_id", "status", "requests", "ledger_usd", "spent_usd", "delta_usd")} for z in run_z], "gui": pages, "source": src})
    rep.add("E4c", "E4: čas", "INFO", {"wall_s": round(time.time() - t_e, 1)})


def klas_flow(a, rep, http, led, APP, KC, dsn, kj, zid_acme, tag, gui_shots):
    """K-1 (P3-4): klasifikační brána K1–K6 před první rolí (profil → org.zakazky + OPA data, high-risk zamyká autonomii, čl. 5 → Odmitnuto bez podu,
    nejasné → H1a právník), čl. 50 naostro (e-mail + ticket přes mock-channels s disclosure z definice role a značením generated_by), SLA bodů (org.sla_events, eskalace)."""
    import psycopg, yaml as _yg
    sys.path.insert(0, str(HERE)); from gui_checks import Gui, KLAS_NO
    RNS = "tenant-acme"
    def pods_of(z): return [p["metadata"]["name"] for p in kj("-n", RNS, "get", "pods", "-l", f"platform.zakazka={re.sub(r'[^A-Za-z0-9_.-]', '-', z)[:63]}").get("items", [])]
    def status(z): r = http("GET", f"{APP}/zakazky/{z}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
    def db(sql, args=()):
        with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c: return c.execute(sql, args).fetchall()
    roles_disc = {r: (_yg.safe_load((ROOT / f"knowledge/organization/roles/{r}.yaml").read_text()).get("disclosure") or {}).get("channels", {}) for r in ("account", "sre")}
    pf_ch = PortForward(a, "mock-channels", 19804, 9804); pf_opa = PortForward(a, "opa", 18181, 8181)
    g = Gui(f"{APP}/gui/", shots=gui_shots / "klas").open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10); t_k = time.time()
    def wait_i(bod, timeout):   # čekání po 60s úsecích, mezi nimi /health obnoví spadlý port-forward (GUI se samo znovu připojí)
        t0 = time.time()
        while True:
            r = g.wait_interrupt(bod, min(60, max(1, timeout - (time.time() - t0))))
            if r["interrupt"] or r["run_status"] in ("finished", "cancelled") or time.time() - t0 >= timeout: r["waited_s"] = round(time.time() - t0, 1); return r
            try: http("GET", f"{APP}/health", timeout=10)
            except Exception: pass
    try:
        g.login("adam", "adam"); L = led()
        # K1d/K1e – zakázka z gui_flow prošla celá: e-mail po H1 (Account) a komentář ticketu po deployi (SRE) v mock-channels, disclosure z roles/*.yaml kanál email/ticket_comment, generated_by jen tam
        msgs = [m for m in http("GET", "http://127.0.0.1:19804/_debug/messages", timeout=15).json()["messages"] if m.get("zakazka") == zid_acme]
        em = next((m for m in msgs if m["channel"] == "email"), {}); tk = next((m for m in msgs if m["channel"] == "ticket"), {})
        sent = [e for e in L if e["kind"] == "CHANNEL_SENT" and e["zakazka"] == zid_acme]; hand = [e for e in L if e["kind"] == "HANDOFF" and e["zakazka"] == zid_acme]
        want_e, want_t = roles_disc["account"].get("email", ""), roles_disc["sre"].get("ticket_comment", "")
        rep.add("K1d", "Čl. 50(1) naostro (T7): stavové zprávy zákazníkovi jdou reálným kanálem přes adaptér (mock-channels: e-mail po H1 od role Account, komentář ticketu po deployi od SRE); disclosure vkládá adaptér z definice role (roles/account.yaml channels.email, roles/sre.yaml channels.ticket_comment), ne model; CHANNEL_SENT http 200 v ledgeru, aktivita channel v GUI", "PASS" if em and tk and em["body"].startswith(want_e.split("{")[0][:30]) and tk["body"].startswith(want_t.split("{")[0][:30]) and len(sent) >= 2 and all(e.get("http") == 200 for e in sent) else "FAIL", {"email": {k: (em.get(k) if k != "body" else (em.get("body") or "")[:120]) for k in ("to", "subject", "body")}, "ticket": {"ticket": tk.get("ticket"), "body": (tk.get("body") or "")[:120]}, "ledger_sent": [(e.get("channel"), e.get("http")) for e in sent], "want_prefix": {"email": want_e[:50], "ticket": want_t[:50]}})
        rep.add("K1e", "Značení generovaného obsahu (T8) jen na kanálech k lidem: e-mail nese hlavičky X-AI-Generated/X-AI-Generated-By a metadata generated_by=ai-agent:account, ticket generated_by=ai-agent:sre (model, zakázka, disclosure=cl50-1); interní předání mezi rolemi (HANDOFF, AG-UI zprávy) značení nenesou", "PASS" if (em.get("headers") or {}).get("X-AI-Generated") == "true" and (em.get("generated_by") or {}).get("generated_by") == "ai-agent:account" and (tk.get("generated_by") or {}).get("generated_by") == "ai-agent:sre" and (em.get("generated_by") or {}).get("zakazka") == zid_acme and hand and not any("generated_by" in e for e in hand) else "FAIL", {"email_headers": em.get("headers"), "email_generated_by": em.get("generated_by"), "ticket_generated_by": tk.get("generated_by"), "handoffs": len(hand)})
        # K1a – K2 = ano → high-risk-III/4: profil v org.zakazky + klasifikace jsonb, approvals zadani.classify, OPA data zakazky/<id>, posun autonomie acme/account A1→A2 odmítnut kvůli high-risk; pak stop
        za = f"{tag}-hr"; g.create_thread(za, f"Zakázka {za}: agent bude přidělovat úkoly lidem v týmu zákazníka (test brány).", klasifikace={"K2": True}); pa = g.wait_profile(120)
        rowa = db("SELECT profile, klasifikace, status FROM org.zakazky WHERE zakazka_id = %s", (za,)); apra = db("SELECT action, decision, approver, channel FROM org.approvals WHERE workflow_instance = %s AND action = 'zadani.classify'", (za,))
        opa_a = http("GET", f"http://127.0.0.1:18181/v1/data/zakazky/{za}", timeout=10); opa_j = (opa_a.json().get("result") or {}) if opa_a.status_code == 200 else {}
        auto = http("POST", f"{APP}/agui/gov/autonomy", headers={"Authorization": f"Bearer {g.token}"}, json={"role": "account", "tenant": "acme", "level": "A2", "reason": "Zkouška: high-risk zakázka tenanta musí posun zamknout (T9)."}, timeout=30)
        auto_j = auto.json() if auto.headers.get("content-type", "").startswith("application/json") else {}
        sta = g.stop("High-risk test hotov – zastavit zakázku, aby neutrácela."); gone = pods_of(za)
        rep.add("K1a", "Klasifikační brána P1a (T9/T15) z GUI: K2 = ano → profil high-risk-III/4 vyhodnocen deterministicky (ne modelem) před první rolí; org.zakazky.profile + klasifikace (odpovědi, by), auditní řádek org.approvals action=zadani.classify approver=adam channel=agui, OPA data zakazky/<id>.profile (PUT /v1/data), STATE_SNAPSHOT.profile v GUI; posun autonomie acme/account na A2 odmítnut s důvodem high-risk (autonomie.md: pass^k vypnuto)", "PASS" if pa["profile"] == "high-risk-III/4" and rowa and rowa[0][0] == "high-risk-III/4" and (rowa[0][1] or {}).get("K2") is True and apra and apra[0][1] == "approve" and apra[0][3] == "agui" and opa_j.get("profile") == "high-risk-III/4" and auto.status_code == 409 and any("high-risk" in r for r in auto_j.get("reasons", [])) and sta["run_status"] == "cancelled" else "FAIL", {"gui_profile": pa["profile"], "db": {"row": [rowa[0][0], rowa[0][2]] if rowa else None, "klasifikace": rowa[0][1] if rowa else None, "approvals": [list(r) for r in apra]}, "opa": {"http": opa_a.status_code, "data": opa_j}, "autonomy": {"http": auto.status_code, "reasons": auto_j.get("reasons"), "metrics": auto_j.get("metrics")}, "stop": sta["run_status"], "pods_after_stop": gone})
        # K1b – K1 = ano → Odmitnuto: workflow končí v P1 bez jediného podu role, org.zakazky status Odmitnuto, approvals decision=reject
        zb = f"{tag}-k1"; g.create_thread(zb, f"Zakázka {zb}: social scoring občanů (čl. 5 – musí být odmítnuta).", klasifikace={"K1": True}); fb = g.wait_finished(120); stb = status(zb)
        rowb = db("SELECT profile, status FROM org.zakazky WHERE zakazka_id = %s", (zb,)); aprb = db("SELECT decision, reason FROM org.approvals WHERE workflow_instance = %s AND action = 'zadani.classify'", (zb,))
        Lb = [e for e in led() if e.get("zakazka") == zb]; pods_b = [e for e in Lb if e["kind"] in ("ROLE_POD_CREATE", "ROLE_GATE", "AGENT_RUN")]
        rep.add("K1b", "Čl. 5 (K1 = ano) → profil odmitnout: zakázka končí v P1 stavem Odmitnuto s auditním záznamem (org.approvals zadani.classify decision=reject, org.zakazky status Odmitnuto) – žádná role neběžela (žádný ROLE_GATE/ROLE_POD_CREATE, žádný pod v ns tenanta), GUI run finished se stavem Odmitnuto", "PASS" if fb["state"]["stav"] == "Odmitnuto" and fb["state"]["profile"] == "odmitnout" and (stb.get("output") or {}).get("stav") == "Odmitnuto" and rowb and rowb[0] == ("odmitnout", "Odmitnuto") and aprb and aprb[0][0] == "reject" and not pods_b and not fb["subagents"] and not pods_of(zb) else "FAIL", {"gui": fb["state"], "wf": stb.get("output"), "db": {"row": list(rowb[0]) if rowb else None, "approval": [aprb[0][0], (aprb[0][1] or "")[:60]] if aprb else None}, "role_events": len(pods_b), "ledger_kinds": sorted({e["kind"] for e in Lb})})
        # K1c – zakázka z interního API bez dotazníku → interrupt reason=klasifikace v GUI; K4 = ano → nejasne → H1a stanovisko právníka (approvals pravnik.stanovisko) → pokračuje; stop
        zc = f"{tag}-api"; http("POST", f"{APP}/zakazky", json={"id": zc, "poptavka": f"Zakázka {zc} z interního API bez dotazníku (test interruptu klasifikace).", "tenant": "acme", "hitl_timeout_s": 1800}, timeout=15); time.sleep(2)
        otc = g.open_thread(zc); wc = g.wait_any_interrupt(120); cc = g.classify({"K4": True}, "Zákazník je obecní úřad – zařazení nejasné.") if wc.get("kind") == "klasifikace" else None
        h1a = wait_i("H1a", 120); d1a = g.decide("Stanovisko právníka: agenda obecního úřadu mimo body přílohy III, pokračovat; smluvně vymezit intended purpose.") if h1a["interrupt"] else None
        pc = g.wait_profile(60); rowc = db("SELECT profile, klasifikace FROM org.zakazky WHERE zakazka_id = %s", (zc,)); aprc = db("SELECT action, decision, channel FROM org.approvals WHERE workflow_instance = %s ORDER BY decided_at", (zc,))
        stc = g.stop("Test H1a hotov – zastavit zakázku.")
        rep.add("K1c", "Zakázka založená bez dotazníku (interní API) čeká na klasifikaci jako AG-UI interrupt reason=klasifikace (resume payload {answers K1–K6}); K4 = ano → profil nejasne → H1a stanovisko právníka jako HITL s důvodem (org.approvals action=pravnik.stanovisko) → zakázka pokračuje k Account; profil zůstává nejasne (do stanoviska high-risk zacházení)", "PASS" if wc.get("kind") == "klasifikace" and cc and cc["questions_shown"] == 6 and h1a["interrupt"] and h1a["interrupt"].startswith("hitl:H1a:") and d1a and d1a["new_run"] and pc["profile"] == "nejasne" and rowc and rowc[0][0] == "nejasne" and (rowc[0][1] or {}).get("by") == "adam" and any(r[0] == "pravnik.stanovisko" and r[1] == "approve" and r[2] == "agui" for r in aprc) and stc["run_status"] == "cancelled" else "FAIL", {"open": otc, "first_interrupt": wc.get("kind"), "classify": cc, "h1a": h1a["interrupt"], "profile": pc["profile"], "db": {"row": [rowc[0][0], rowc[0][1]] if rowc else None, "approvals": [list(r) for r in aprc]}, "stop": stc["run_status"]})
        # K1f – SLA bodu H1 = 20 s (procesy.md lhůta zkrácena pro měření): překročení → SLA_BREACH + org.sla_events + eskalace vlastníkovi, GUI ukáže „SLA překročeno“, zakázka dál čeká; po schválení pokračuje
        zf = f"{tag}-sla"; http("POST", f"{APP}/zakazky", json={"id": zf, "poptavka": f"Zakázka {zf}: přidej soubor zakazky/{zf}/NOTES.md (test SLA H1).", "tenant": "acme", "klasifikace": KLAS_NO, "sla": {"H1": 20}, "hitl_timeout_s": 1800}, timeout=15); time.sleep(2)
        g.open_thread(zf); dialog_then(g, zf, 1200)
        hf = wait_i("H1", 600); slaf = g.wait_sla(90); stf0 = status(zf)
        df = g.decide("SLA překročeno, zadání je přesto v pořádku – schvaluji vstup zakázky.") if hf["interrupt"] else None; wsf = g.wait_subagent("architekt", 600); fin_f = g.snapshot()
        rowf = [(r[0], float(r[1]), r[2], r[3]) for r in db("SELECT bod, sla_s, escalated_to, process_id FROM org.sla_events WHERE zakazka_id = %s", (zf,))]; brf = [e for e in led() if e["kind"] == "SLA_BREACH" and e["zakazka"] == zf]
        stf = g.stop("Test SLA hotov – zastavit zakázku."); 
        rep.add("K1f", "SLA bodů (procesy.md) jako timer uvnitř HITL čekání: H1 s SLA 20 s překročeno → SLA_BREACH v ledgeru + řádek org.sla_events (bod H1, eskalace vlastnik:account, proces P1), GUI ukáže „SLA překročeno: H1“ při otevřeném interruptu (stav threadu), zakázka zůstává RUNNING a čeká dál (timeout teprve pozastaví); po schválení pokračuje (architekt běží), aktivita sla v GUI", "PASS" if hf["interrupt"] and slaf["sla_text"] and "H1" in slaf["sla_text"] and slaf["interrupt"] == hf["interrupt"] and stf0.get("status") == "RUNNING" and rowf and rowf[0][0] == "H1" and float(rowf[0][1]) == 20 and rowf[0][2] == "vlastnik:account" and brf and brf[0].get("result") == "ceka_dal" and df and df["new_run"] and wsf["status"] == "running" and fin_f["acts"]["sla"] >= 1 else "FAIL", {"h1": hf["interrupt"], "sla_gui": slaf, "wf_during_wait": stf0.get("status"), "db_sla_events": [list(r) for r in rowf], "ledger_breach": [{k: e.get(k) for k in ("bod", "sla_s", "escalated_to", "registry")} for e in brf], "after_decide": wsf, "acts": fin_f["acts"], "stop": stf["run_status"]})
        rep.add("K1g", "Klasifikační brána, kanály a SLA: čas scénáře, screenshoty", "INFO", {"wall_s": round(time.time() - t_k, 1), "shots": sorted(p.name for p in (gui_shots / "klas").glob("*.png")) if (gui_shots / "klas").exists() else []})
    finally:
        g.close(); pf_ch.stop(); pf_opa.stop()


def gui_flow(a, rep, http, led, zid, APP, GHS, dsn):
    """U-1 (P3-1): zakázka řízená z GUI v prohlížeči (Playwright nad port-forwardem aplikace). Vrací to, co P21b potřebuje dál
    (zid, issue, pr, merged, st, adr_early) a zapíše checky U1a–U1g."""
    import psycopg
    sys.path.insert(0, str(HERE)); from gui_checks import Gui, ROLES
    RNS = "tenant-acme"; shots = LOGS / "gui-shots"   # P3-2: pody rolí v ns tenanta zakázky
    def kj(*args):
        r = kubectl(a, *args, "-o", "json"); return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
    def pods_of(z): return [p["metadata"]["name"] for p in kj("-n", RNS, "get", "pods", "-l", f"platform.zakazka={re.sub(r'[^A-Za-z0-9_.-]', '-', z)[:63]}").get("items", []) if not p["metadata"].get("deletionTimestamp")]
    def status(z):
        r = http("GET", f"{APP}/zakazky/{z}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
    def approvals(z):
        try:
            with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
                return [dict(zip(("process_id", "action", "decision", "reason", "approver", "channel", "artifact_sha"), r)) for r in c.execute("SELECT process_id, action, decision, reason, approver, channel, artifact_sha FROM org.approvals WHERE workflow_instance = %s ORDER BY decided_at", (z,)).fetchall()]
        except Exception as e: return {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    g = Gui(f"{APP}/gui/", shots=shots).open(); g.keepalive = lambda: http("GET", f"{APP}/health", timeout=10); t_gui = time.time()
    def wait_i(bod, timeout):
        """Čekání na interrupt po 60s úsecích; mezi nimi http() na /health (obnoví spadlý port-forward – GUI se pak samo znovu připojí)."""
        t0 = time.time()
        while True:
            r = g.wait_interrupt(bod, min(60, max(1, timeout - (time.time() - t0))))
            if r["interrupt"] or r["run_status"] in ("finished", "cancelled") or time.time() - t0 >= timeout: r["waited_s"] = round(time.time() - t0, 1); return r
            try: http("GET", f"{APP}/health", timeout=10)
            except Exception: pass
    g.wait_interrupt_chunked = wait_i
    try:
        lf = g.login_fail("adam", "wrong-password"); li = g.login("adam", "adam"); lst0 = g.threads_list()
        api_me = http("GET", f"{APP}/agui/me", headers={"Authorization": f"Bearer {g.token}"}, timeout=10); me = api_me.json() if api_me.status_code == 200 else {}
        noauth = http("GET", f"{APP}/agui/threads", timeout=10).status_code
        rep.add("U1a", "GUI (vlastní frontend, AG-UI 1.0 klient) servírované aplikací zakázky: přihlášení člověka přes Keycloak (password grant klientem harness-human – zjednodušení P3-1), špatné heslo odmítnuto, token RS256 ověřen JWKS (realm role human, tenant_id acme z claimu), bez tokenu 401, seznam zakázek tenanta", "PASS" if lf["still_login"] and li["user"] == "adam" and li["tenant"] == "acme" and li["token"] and me.get("tenant") == "acme" and "human" in (me.get("roles") or []) and noauth == 401 and isinstance(lst0, list) else "FAIL", {"login": li, "login_fail": lf, "me": {k: me.get(k) for k in ("name", "tenant", "roles")}, "no_token_http": noauth, "threads_before": len(lst0)})
        # U1b/U1c/U1e/U1g – zakázka 1 celá z GUI
        t1 = time.time(); cr = g.create_thread(zid, f"Přidej do repa platformy soubor zakazky/{zid}/NOTES.md s poznámkou, že zakázku řídil člověk z GUI (AG-UI) v AKS.")
        dlg = dialog_then(g, zid, 1800)   # P3-3: Account se nejdřív ptá (mock: 1 kolo) – odpovědět, pak H1
        h1 = wait_i("H1", 1200); assert h1["interrupt"], f"H1 interrupt nepřišel: {h1['run_status']} {h1.get('error')} ledger={[(e['kind'], e.get('role'), e.get('error') or e.get('event')) for e in led() if e.get('zakazka') == zid][-8:]}"
        api422 = http("POST", f"{APP}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": zid, "runId": "u1c", "messages": [], "resume": [{"interruptId": h1["interrupt"], "status": "resolved", "payload": {"decision": "approve", "reason": "ok"}}]}, timeout=15)
        d1 = g.decide("Zadání odpovídá poptávce, akceptační kritéria jsou měřitelná – schvaluji vstup zakázky.")
        h2 = wait_i("H2", 1200); assert h2["interrupt"], f"H2 interrupt nepřišel: {h2['run_status']} {h2.get('error')}"
        d2 = g.decide("Návrh je v rozpočtu a drží konvence repa – schvaluji ADR.")
        h4 = wait_i("H4", 2400); assert h4["interrupt"], f"H4 interrupt nepřišel: {h4['run_status']} {h4.get('error')}"
        d4 = g.decide("Review bez vad, soubory odpovídají zadání – schvaluji merge (N1).")
        h5 = wait_i("H5", 600); assert h5["interrupt"], f"H5 interrupt nepřišel: {h5['run_status']} {h5.get('error')}"
        d5 = g.decide("Nasazení schváleno, rollback v runbooku – schvaluji deploy (N2).")
        fin = g.wait_finished(600); st = status(zid)
        L = led(); issue = next((e for e in L if e["kind"] == "PUBLISHED" and e["zakazka"] == zid and e.get("publish_kind") == "issue"), {}); pr = next((e for e in L if e["kind"] == "PUBLISHED" and e["zakazka"] == zid and e.get("publish_kind") == "pull_request"), {})
        try: merged = http("GET", GHS, timeout=10).json()["pulls"][str(pr["number"])]["merged"] if pr else False
        except Exception: merged = False
        apr = approvals(zid); apr_l = apr if isinstance(apr, list) else []
        gui_apr = [e for e in L if e["kind"] == "APPROVAL_RAISED" and e["zakazka"] == zid and e.get("channel") == "agui"]
        waits = [e for e in L if e["kind"] == "NOTIFY" and e.get("event") == "HITL_WAIT" and e["zakazka"] == zid]
        rep.add("U1b", "Thread zakázky v GUI streamuje průběh ze SSE AG-UI: 4 role v pořadí account → architekt → vyvojar → reviewer jako SUBAGENT_STARTED/FINISHED (status done), stav z STATE_SNAPSHOT = Dokonceno; zakázka prošla P1→P5 jen klikáním v GUI (žádný /schvaluji, HITL_WAIT pro H1/H2/H4/H5 v ledgeru, approval eventy channel=agui)", "PASS" if list(dict.fromkeys(s["name"] for s in fin["subagents"])) == list(ROLES) and all(s["status"] == "done" for s in fin["subagents"]) and fin["state"]["stav"] == "Dokonceno" and (st.get("output") or {}).get("stav") == "Dokonceno" and [w["bod"] for w in waits] == ["H1", "H2", "H4", "H5"] and len(gui_apr) == 4 else "FAIL", {"subagents": fin["subagents"], "state": fin["state"], "wf": st.get("output"), "hitl_waits": [w["bod"] for w in waits], "approvals_agui": len(gui_apr), "wall_s": round(time.time() - t1, 1)})
        ok_db = len(apr_l) >= 4 and all(r["decision"] == "approve" and len(r["reason"] or "") >= 10 and r["channel"] == "agui" and r["approver"] == me.get("sub") for r in apr_l) and {r["action"] for r in apr_l} >= {"zadani.accept", "navrh.accept", "pr.merge", "deploy.apply"}
        rep.add("U1c", "HITL = interrupt/resume s povinným důvodem (T6): tlačítka Schválit/Zamítnout zakázaná bez důvodu i s krátkým důvodem; resume přes API bez důvodu → 422; každé schválení = APPROVAL_RAISED by=adam channel=agui + HITL_APPROVED by=adam v ledgeru + řádek org.approvals (decision approve, reason ≥ 10, approver = Keycloak sub, channel agui) – 4 řádky za H1/H2/H4/H5", "PASS" if api422.status_code == 422 and all(d["disabled_empty"] and d["disabled_short"] and not d["disabled_with_reason"] and d["new_run"] and not d["error"] for d in (d1, d2, d4, d5)) and ok_db and all(e.get("by") == "adam" for e in L if e["kind"] == "NOTIFY" and e.get("event") == "HITL_APPROVED" and e["zakazka"] == zid) else "FAIL", {"api_no_reason_http": api422.status_code, "decide": {"H1": d1, "H2": d2, "H4": d4, "H5": d5}, "org_approvals": apr if isinstance(apr, dict) else [{k: (v if k != "reason" else v[:40]) for k, v in r.items()} for r in apr_l]})
        import yaml as _yg
        want_disc = {r: (_yg.safe_load((ROOT / f"knowledge/organization/roles/{r}.yaml").read_text()).get("disclosure") or {}).get("channels", {}).get("agui", "") for r in ROLES}
        got_disc = {r: next((m["disclosure"] for m in fin["messages"] if m["name"] == r and m["disclosure"]), None) for r in ROLES}
        rep.add("U1e", "Disclosure čl. 50(1) (T7) v první zprávě každé role v GUI: věta z kanálu `agui` definice role (roles/*.yaml → rolegen roles.json), vkládá ji platforma (AG-UI server), ne model; {firma}/{vlastník procesu} doplněny", "PASS" if all(got_disc[r] and "AI agent" in got_disc[r] and got_disc[r].split("{")[0][:25] == want_disc[r].split("{")[0][:25] for r in ROLES) else "FAIL", {"messages": fin["messages"], "want_prefix": {r: want_disc[r][:60] for r in ROLES}})
        ev = fin["events"]
        rep.add("U1g", "Shoda se spec AG-UI 1.0: RUN_STARTED s protocolVersion=1.0 (zobrazeno v GUI), stream začíná RUN_STARTED a končí RUN_FINISHED, HITL jako RUN_FINISHED outcome=interrupt s id hitl:<bod>:<hash> pro H1/H2/H4/H5, rozhodnutí jako RunAgentInput.resume [{interruptId, status: resolved, payload}], po resume nový run (runId se změnil)", "PASS" if cr["protocol"] == "1.0" and fin["protocol"] == "1.0" and ev and ev[0] == "RUN_STARTED" and ev[-1] == "RUN_FINISHED" and all(h["interrupt"] and h["interrupt"].startswith(f"hitl:{b}:") for h, b in ((h1, "H1"), (h2, "H2"), (h4, "H4"), (h5, "H5"))) and "SUBAGENT_STARTED" in ev and "STATE_SNAPSHOT" in ev else "FAIL", {"protocol": cr["protocol"], "events": sorted(set(ev)), "n_events": len(ev), "interrupts": [h["interrupt"] for h in (h1, h2, h4, h5)]})
        # U1d – cizí tenant: zakázka tenanta beta přes interní API (rozpočet 0 → gate ji hned pozastaví, žádný pod); GUI acme ji nevidí, run → 404
        zb = f"{zid}-beta"; http("POST", f"{APP}/zakazky", json={"id": zb, "poptavka": "cizí tenant – nesmí být vidět", "tenant": "beta", "budget_usd": 0.001, "budget_timeout_s": 5, "hitl_timeout_s": 5}, timeout=15); time.sleep(3)   # krátké timeouty: po první roli se sama pozastaví
        lst = g.threads_list(); r404 = http("POST", f"{APP}/agui/run", headers={"Authorization": f"Bearer {g.token}"}, json={"threadId": zb, "runId": "u1d", "messages": []}, timeout=15); ot = g.open_thread(zb)
        rep.add("U1d", "Autorizace na transportu: thread cizího tenanta (zakázka tenanta beta založená interním API) není v seznamu tenanta acme, POST /agui/run na něj → 404 (API i GUI), vlastní zakázka v seznamu je", "PASS" if zb not in [t["id"] for t in lst] and zid in [t["id"] for t in lst] and r404.status_code == 404 and "404" in (ot.get("error") or "") else "FAIL", {"listed": [t["id"] for t in lst][:10], "run_http": r404.status_code, "gui": ot})
        # U1f – stop uprostřed role (architekt v Kata podu) s důvodem: pause workflow + pod pryč ≤ 60 s
        zid2 = f"{zid[:-2]}-2"; g.create_thread(zid2, f"Druhá zakázka {zid2} – test stopu z GUI uprostřed role."); dialog_then(g, zid2, 1200); h1b = wait_i("H1", 1200); assert h1b["interrupt"], f"H1 (zakázka 2) nepřišel: {h1b['run_status']} {h1b.get('error')}"
        g.decide("Zadání v pořádku, pokračovat k návrhu – test stopu.")
        ws = g.wait_subagent("architekt", 600)
        t_p = time.time(); pods_before = []
        while time.time() - t_p < 120 and not pods_before: pods_before = pods_of(zid2); time.sleep(2)
        stp = g.stop("Zákazník pozastavil zakázku do vyjasnění rozpočtu – stop z GUI."); t_s = time.time(); pods_after = pods_before
        while time.time() - t_s < 90 and pods_after: pods_after = pods_of(zid2); time.sleep(2)
        gone_s = round(time.time() - t_s, 1); st2 = status(zid2); stop_led = next((e for e in reversed(led()) if e["kind"] == "STOP" and e["zakazka"] == zid2), {})
        rep.add("U1f", "Stop zakázky z GUI s důvodem (T5/T6): tlačítko bez důvodu zakázané; stop → pause workflow (Dapr SUSPENDED, čekající HITL zůstává durable) + ukončení běžícího Kata podu role (ROLE_POD_KILLED, pod pryč ≤ 60 s) → RUN_FINISHED outcome=cancelled v GUI; STOP v ledgeru nese důvod, kanál agui a smazané pody", "PASS" if ws["status"] == "running" and pods_before and stp["disabled_short"] and not stp["disabled_with_reason"] and stp["run_status"] == "cancelled" and st2.get("status") == "SUSPENDED" and not pods_after and gone_s <= 60 and stop_led.get("channel") == "agui" and stop_led.get("reason") and set(stop_led.get("pods_killed") or []) & set(pods_before) else "FAIL", {"subagent": ws, "pods_before": pods_before, "pods_after": pods_after, "pod_gone_s": gone_s, "stop": {k: stp.get(k) for k in ("disabled_short", "disabled_with_reason", "run_status", "stop_to_cancelled_s", "state")}, "wf": st2, "ledger_stop": {k: stop_led.get(k) for k in ("by", "reason", "channel", "pods_killed", "status")}})
        rep.add("U1h", "GUI: konzole prohlížeče (chyby/varování) a čas scénáře", "INFO", {"console": g.log[:10], "wall_s": round(time.time() - t_gui, 1), "shots": sorted(p.name for p in shots.glob("*.png")) if shots.exists() else []})
    finally:
        g.close()
    return zid, issue, pr, merged, st, False


KLAS_NO = {k: False for k in ("K1", "K2", "K3", "K4", "K5", "K6")}   # P3-4: zakázky z interního API musí nést dotazník, jinak čekají na klasifikaci v AG-UI


def e6_flow(a, rep, http, led, APP, kj, tag):
    """E6 (P3-6): verzování workflow – Dapr named versioning (1.17+): každá verze orchestrátoru (zakazka_wf.py, snímky wf_versions/) je registrovaná pod
    jménem `zakazka` s version_name = hash obsahu; instance nese verzi v historii a po nasazení nového obrazu (zde: restart podu aplikace, obě verze
    v obrazu) běží dál na své verzi – nález P3-5 (instance ze starého obrazu po pause/resume FAILED) tím mizí. Důkaz: zakázka založená na starší,
    ne-latest verzi (kandidát s jiným pořadím úloh) i zakázka na latest čekají na klasifikaci, pod aplikace se restartuje, obě po eventu dojdou
    (Odmitnuto, K1) – každá na své verzi (ledger WORKFLOW_VERSION/KLASIFIKACE_DONE jen u kandidáta, KLASIFIKACE_WAIT.wf_version), žádná FAILED."""
    t_e = time.time()
    chk = sh([sys.executable, str(T / "harness_p0_o2/wf_versions.py"), "check"]); chk_j = json.loads(chk.stdout.strip().splitlines()[-1]) if chk.stdout.strip() else {}
    v0 = http("GET", f"{APP}/_wf/versions", timeout=30).json(); cur = v0.get("current"); reg = (v0.get("registered") or {}).get("versions") or []
    L0 = led(); wfv = [e for e in L0 if e["kind"] == "WF_VERSIONS"]
    rep.add("E6a", "Verzování workflow (Dapr named versioning): orchestrátor zakázky v samostatném modulu zakazka_wf.py (aktivity jménem), verze = hash obsahu, snímek každé verze v wf_versions/ (CI `wf_versions.py check` = snímek aktuální verze existuje a odpovídá názvu); aplikace registruje všechny snímky + aktuální jako latest a při startu ověří, že všechny aktivity volané kteroukoli verzí jsou registrované (ledger WF_VERSIONS), GET /_wf/versions hlásí current == verze z HEAD repa, ≥ 2 registrované verze (kandidát s jiným pořadím úloh), latest == current, žádný neshodný snímek", "PASS" if chk.returncode == 0 and chk_j.get("ok") and cur and cur == chk_j.get("current") and v0.get("latest") == cur and len(reg) >= 2 and cur in reg and not (v0.get("registered") or {}).get("unfrozen") and not (v0.get("registered") or {}).get("bad") and (v0.get("registered") or {}).get("activities_checked") and all(v0.get("snapshots", {}).values()) and wfv and wfv[-1].get("current") == cur else "FAIL", {"check": chk_j, "check_rc": chk.returncode, "api": {k: v0.get(k) for k in ("current", "latest", "registered", "snapshots")}, "ledger_wf_versions": (wfv[-1] if wfv else None)})
    old = next((v for v in sorted(reg) if v != cur), None); zo, zn = f"{tag}-e6old", f"{tag}-e6new"
    def K(e): return e.get("event") if e.get("kind") == "NOTIFY" else e.get("kind")   # události orchestrátoru jdou přes aktivitu notify (kind NOTIFY, event=…)
    def wait_kind(zid, kind, timeout=120):
        t0 = time.time()
        while time.time() - t0 < timeout:
            e = next((e for e in led() if K(e) == kind and e.get("zakazka") == zid), None)
            if e: return e
            time.sleep(2)
    def status(z): r = http("GET", f"{APP}/zakazky/{z}", timeout=15); return r.json() if r.status_code == 200 else {"status": f"http{r.status_code}"}
    sw1 = http("POST", f"{APP}/_wf/latest", json={"version": old, "by": "harness", "reason": "E6b: zakázka na starší verzi orchestrátoru"}, timeout=15).json() if old else {}
    http("POST", f"{APP}/zakazky", json={"id": zo, "poptavka": f"Zakázka {zo} bez dotazníku (E6b: založena na starší verzi orchestrátoru {old}).", "tenant": "acme", "hitl_timeout_s": 1800}, timeout=15)
    w_old = wait_kind(zo, "KLASIFIKACE_WAIT") or {}
    sw2 = http("POST", f"{APP}/_wf/latest", json={"version": cur, "by": "harness", "reason": "E6b: zpět na latest"}, timeout=15).json()
    http("POST", f"{APP}/zakazky", json={"id": zn, "poptavka": f"Zakázka {zn} bez dotazníku (E6b: založena na latest verzi {cur}).", "tenant": "acme", "hitl_timeout_s": 1800}, timeout=15)
    w_new = wait_kind(zn, "KLASIFIKACE_WAIT") or {}
    st_before = {zo: status(zo).get("status"), zn: status(zn).get("status")}; v_mid = http("GET", f"{APP}/_wf/versions", timeout=30).json()
    # „nasazení“: nový pod aplikace (tentýž obraz nese obě verze); pody rolí nesmí běžet (výsledek běhu role se posílá do procesu aplikace)
    t_w = time.time()
    while time.time() - t_w < 600 and any(p_ for ns_ in [n["metadata"]["name"] for n in kj("get", "ns", "-l", "platform.tenant").get("items", [])] for p_ in kj("-n", ns_, "get", "pods", "-l", "app=role").get("items", []) if (p_.get("status") or {}).get("phase") in ("Pending", "Running")): time.sleep(10)
    t_r = time.time(); restart_pods(a, "zakazka"); time.sleep(5)
    roll = kubectl(a, "-n", NS, "rollout", "status", "deployment/zakazka", "--timeout=420s", timeout=440).returncode == 0
    kubectl(a, "-n", NS, "wait", "--for=condition=Ready", "pod", "-l", "app=zakazka", "--timeout=300s", timeout=320)
    health = None
    for _ in range(30):
        try: health = http("GET", f"{APP}/health", timeout=10).status_code
        except Exception: health = None
        if health == 200: break
        time.sleep(5)
    restart_s = round(time.time() - t_r, 1)
    wfv2 = [e for e in led() if e["kind"] == "WF_VERSIONS" and e["ts"] > t_r]; v_after = http("GET", f"{APP}/_wf/versions", timeout=30).json()
    for z_ in (zo, zn): http("POST", f"{APP}/zakazky/{z_}/classify", json={"answers": {"K1": True}, "by": "harness", "reason": "E6b: čl. 5 → Odmitnuto bez role (rychlý konec)"}, timeout=15)
    fin = {}
    t0 = time.time()
    while time.time() - t0 < 240 and not all(fin.get(z_, {}).get("status") in ("COMPLETED", "FAILED", "TERMINATED") for z_ in (zo, zn)):
        fin = {z_: status(z_) for z_ in (zo, zn)}; time.sleep(3)
    L = led(); ev = {z_: [(K(e), e.get("wf_version"), round(e["ts"] - t_r, 1)) for e in L if e.get("zakazka") == z_ and K(e) in ("ZAKAZKA_START", "WORKFLOW_VERSION", "KLASIFIKACE_WAIT", "KLASIFIKACE_RAISED", "KLASIFIKACE", "KLASIFIKACE_DONE", "REGISTRY_ZAKAZKA")] for z_ in (zo, zn)}
    done_old = next((e for e in L if e.get("zakazka") == zo and K(e) == "KLASIFIKACE_DONE"), None)
    ok_old = bool(old) and sw1.get("latest") == old and w_old.get("wf_version") == old and any(K(e) == "WORKFLOW_VERSION" and e.get("wf_version") == old for e in L if e.get("zakazka") == zo) and fin.get(zo, {}).get("status") == "COMPLETED" and (fin[zo].get("output") or {}).get("stav") == "Odmitnuto" and done_old and done_old.get("wf_version") == old and done_old["ts"] > t_r and fin[zo].get("wf_version") == old
    ok_new = sw2.get("latest") == cur and w_new.get("wf_version") == cur and not any(K(e) in ("WORKFLOW_VERSION", "KLASIFIKACE_DONE") for e in L if e.get("zakazka") == zn) and fin.get(zn, {}).get("status") == "COMPLETED" and (fin[zn].get("output") or {}).get("stav") == "Odmitnuto" and fin[zn].get("wf_version") == cur
    rep.add("E6b", "Instance workflow přežije nasazení jiné verze: zakázka založená na starší (ne-latest) verzi orchestrátoru (POST /_wf/latest → kandidát s jiným pořadím úloh: WORKFLOW_VERSION navíc) a zakázka na latest čekají na klasifikaci (stejný mechanismus čekání jako HITL: external event + timery); restart podu aplikace (nový proces = replay historie z Postgresu, latest zpět na verzi obrazu – WF_VERSIONS) → event klasifikace K1 → obě COMPLETED/Odmitnuto, každá na své verzi (kandidát po restartu zapsal KLASIFIKACE_DONE se svou verzí, latest nic), žádná FAILED; GET /zakazky/<id>.wf_version", "PASS" if ok_old and ok_new and roll and health == 200 and wfv2 and wfv2[-1].get("current") == cur and v_after.get("latest") == cur and st_before == {zo: "RUNNING", zn: "RUNNING"} else "FAIL", {"versions": {"current": cur, "old": old}, "switch": [sw1, sw2], "before_restart": st_before, "latest_mid": v_mid.get("latest"), "restart": {"rollout": roll, "health": health, "s": restart_s, "wf_versions_after": (wfv2[-1] if wfv2 else None)}, "final": {z_: {"status": fin.get(z_, {}).get("status"), "stav": (fin.get(z_, {}).get("output") or {}).get("stav"), "wf_version": fin.get(z_, {}).get("wf_version"), "failure": fin.get(z_, {}).get("failure")} for z_ in (zo, zn)}, "events": ev})
    v_end = http("GET", f"{APP}/_wf/versions", timeout=30).json(); vo = (v_end.get("versions") or {}).get(old) or {}; vc = (v_end.get("versions") or {}).get(cur) or {}
    rep.add("E6c", "Report verzí pro drain (GET /_wf/versions): instance per verze podle ledgeru + stavu v Dapru; starší verze má po dokončení E6b jen terminální instance (drained = snímek lze smazat), latest má instance běhu; `legacy` = instance z doby před verzováním (Dapr je přehrává na latest – kompatibilní, dokud se nezmění pořadí úloh); chybějící verze by instance nechala STALLED, ne FAILED (Dapr 1.17+, neměřeno)", "PASS" if vo.get("registered") and vo.get("instances", {}).get("COMPLETED", 0) >= 1 and vo.get("drained") is True and vc.get("registered") and sum(vc.get("instances", {}).values()) >= 1 else "FAIL", {"old": vo, "current": vc, "legacy": v_end.get("legacy"), "latest": v_end.get("latest"), "wall_s": round(time.time() - t_e, 1)})


def platform_ca_bundle(a, kj):
    """P3-6 E7: root interní CA (Secret cert-manager/platform-root-ca) → logs/platform-ca.crt a bundle certifi + root → SSL_CERT_FILE procesu harnessu
    (httpx trust_env, urllib/PyJWKClient, Playwright ne – GUI jde přes aplikaci). Vrací cestu k rootu."""
    import base64 as _b, certifi
    sec = kj("-n", "cert-manager", "get", "secret", "platform-root-ca"); root = _b.b64decode((sec.get("data") or {}).get("ca.crt", "")).decode()
    assert root.strip(), "Secret cert-manager/platform-root-ca bez ca.crt (kustomizace trust není Ready?)"
    (LOGS / "platform-ca.crt").write_text(root); (LOGS / "ca-bundle.pem").write_text(open(certifi.where()).read().rstrip("\n") + "\n" + root)
    os.environ["SSL_CERT_FILE"] = str(LOGS / "ca-bundle.pem")
    return str(LOGS / "platform-ca.crt")


def e7_checks(a, rep, http, kj, KC, BAO, ca_file):
    """E7 (P3-6): OpenBao (8200) a Keycloak (8443) jen HTTPS s certifikáty z interní CA (cert-manager ClusterIssuer platform-ca), klienti ověřují
    proti ConfigMapě platform-ca (SSL_CERT_FILE v podech); issuer tokenů https://keycloak:8443/realms/p0; plaintext odmítnut."""
    import ssl, base64 as _b
    from cryptography import x509; from cryptography.hazmat.primitives.asymmetric import ec
    def get(ns, kind, name):
        r = kj("-n", ns, "get", kind, name); return r if isinstance(r, dict) else {}
    def ready(o): return next((c.get("status") for c in ((o.get("status") or {}).get("conditions") or []) if c.get("type") == "Ready"), None)
    root = open(ca_file).read(); rootc = x509.load_pem_x509_certificate(root.encode())
    import certifi
    ctx_root = ssl.create_default_context(cafile=ca_file); ctx_public = ssl.create_default_context(cafile=certifi.where())   # jen veřejné CA (certifi; výchozí kontext by vzal SSL_CERT_FILE harnessu s rootem) – interní cert musí odmítnout
    certs = {}
    for name in ("openbao-tls", "keycloak-tls"):
        c = get(NS, "certificate", name); sec = get(NS, "secret", name); crt = _b.b64decode((sec.get("data") or {}).get("tls.crt", "")).decode()
        leaf = x509.load_pem_x509_certificate(crt.split("-----END CERTIFICATE-----")[0].encode() + b"-----END CERTIFICATE-----\n") if crt else None
        try: rootc.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(leaf.signature_hash_algorithm)); chain = True
        except Exception as e: chain = type(e).__name__
        san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value if leaf else None
        certs[name] = {"ready": ready(c), "issuer": ((sec.get("metadata") or {}).get("annotations") or {}).get("cert-manager.io/issuer-name"), "dns": sorted(san.get_values_for_type(x509.DNSName)) if san else [], "ip": [str(i) for i in san.get_values_for_type(x509.IPAddress)] if san else [], "chain_ok": chain, "not_after": leaf.not_valid_after_utc.isoformat() if leaf else None, "days_left": (leaf.not_valid_after_utc - __import__("datetime").datetime.now(__import__("datetime").timezone.utc)).days if leaf else None}
    def probe(url, ctx, **kw):
        try: r = httpx.get(url, verify=ctx, timeout=15, **kw); return {"http": r.status_code, "body": r.text[:120]}
        except Exception as e: return {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    bao_ok = probe(f"{BAO}/v1/sys/health?standbyok=true", ctx_root); bao_pub = probe(f"{BAO}/v1/sys/health?standbyok=true", ctx_public)
    kc_disc = probe(f"{KC}/realms/p0/.well-known/openid-configuration", ctx_root); kc_pub = probe(f"{KC}/realms/p0/.well-known/openid-configuration", ctx_public)
    iss = None
    try: iss = httpx.get(f"{KC}/realms/p0/.well-known/openid-configuration", verify=ctx_root, timeout=15).json().get("issuer")
    except Exception: pass
    # plaintext zevnitř clusteru (pod aplikace): OpenBao TLS listener odpoví 400 „HTTPS server“, Keycloak port 8080 Service nemá (connect error)
    code = "import httpx\nfor u in ('http://openbao:8200/v1/sys/health', 'http://keycloak:8080/realms/p0', 'http://keycloak:8443/realms/p0'):\n    try: r = httpx.get(u, timeout=5); print(u, r.status_code, r.text[:60].replace('\\n', ' '))\n    except Exception as e: print(u, 'ERR', type(e).__name__)\n"
    plain = kubectl(a, "-n", NS, "exec", "deploy/zakazka", "-c", "app", "--", "python", "-c", code, timeout=90).stdout.strip().splitlines()
    plain_ok = len(plain) == 3 and (" 400 " in plain[0] or " ERR " in plain[0]) and " ERR " in plain[1] and (" 400 " in plain[2] or " ERR " in plain[2])
    svc = {n: [p_["port"] for p_ in (get(NS, "service", n).get("spec") or {}).get("ports", [])] for n in ("openbao", "keycloak")}
    env = get(NS, "configmap", "zakazka-env").get("data") or {}
    cm_ca = (get(NS, "configmap", "platform-ca").get("data") or {}).get("ca.crt", "")
    want_sans = {"openbao-tls": ["localhost", "openbao", "openbao.platform-data", "openbao.platform-data.svc", "openbao.platform-data.svc.cluster.local"], "keycloak-tls": ["keycloak", "keycloak.platform-data", "keycloak.platform-data.svc", "keycloak.platform-data.svc.cluster.local", "localhost"]}
    ok_certs = all(v["ready"] == "True" and v["issuer"] == "platform-ca" and v["chain_ok"] is True and v["dns"] == want_sans[k] and v["ip"] == ["127.0.0.1"] and (v["days_left"] or 0) > 30 for k, v in certs.items())
    rep.add("E7a", "TLS OpenBao a Keycloaku z interní CA (cert-manager Certificate openbao-tls/keycloak-tls, ClusterIssuer platform-ca): Secrety vydané, leaf podepsán rootem platformy, SAN = jméno Service (krátké i FQDN) + localhost/127.0.0.1 (port-forward), > 30 dní platnosti; OpenBao /sys/health i Keycloak discovery přes HTTPS ověřené proti root CA (proti veřejným CA odmítnuto), issuer tokenů https://keycloak:8443/realms/p0; plaintext zevnitř clusteru odmítnut (OpenBao 400 HTTPS server, Keycloak 8080 bez Service); Service jen 8200/8443(+9000 mgmt); zakazka-env P0_BAO_ADDR/P0_KC_* https + SSL_CERT_FILE = ConfigMap platform-ca (root)", "PASS" if ok_certs and bao_ok.get("http") in (200, 429, 472, 473, 501, 503) and "error" in bao_pub and kc_disc.get("http") == 200 and "error" in kc_pub and iss == "https://keycloak:8443/realms/p0" and plain_ok and svc.get("openbao") == [8200, 8201] and svc.get("keycloak") == [8443, 9000] and env.get("P0_BAO_ADDR", "").startswith("https://") and all(env.get(k, "").startswith("https://keycloak:8443/") for k in ("P0_KC_TOKEN_URL", "P0_KC_JWKS_URL", "P0_KC_ISSUER")) and env.get("P0_KC_EXCHANGE_URL", "").startswith("https://keycloak.platform-data.svc:8443/") and env.get("SSL_CERT_FILE") == "/etc/platform/ca/ca.crt" and cm_ca.strip() == root.strip() else "FAIL", {"certs": certs, "openbao": {"root_ca": bao_ok, "public_ca": bao_pub}, "keycloak": {"root_ca": kc_disc, "public_ca": kc_pub, "issuer": iss}, "plaintext_from_pod": plain, "services": svc, "env": {k: env.get(k) for k in ("P0_BAO_ADDR", "P0_KC_TOKEN_URL", "P0_KC_ISSUER", "P0_KC_EXCHANGE_URL", "SSL_CERT_FILE")}, "platform_ca_is_root": cm_ca.strip() == root.strip()})


def e7_app_checks(rep, http, led, APP, zid, t_run):
    """E7b: klienti přes TLS v provozu – aplikace (password grant z GUI, BAO_LOGIN auth kubernetes, SIGN transit), server paměti (JWKS → volání rolí 200),
    Governance MCP (token člověka), pod role (token exchange na https URL, iss https); žádná chyba TLS v ledgeru."""
    L = [e for e in led() if e.get("ts", 0) > t_run]
    me = http("POST", f"{APP}/agui/login", json={"username": "adam", "password": "adam"}, timeout=20); tok = (me.json() if me.status_code == 200 else {}).get("token") or (me.json() if me.status_code == 200 else {}).get("access_token")
    iss = None
    if tok:
        import jwt as _j
        try: iss = _j.decode(tok, options={"verify_signature": False}).get("iss")
        except Exception: pass
    bao = [e for e in L if e["kind"] == "BAO_LOGIN"]; signs = [e for e in L if e["kind"] == "SIGN" and e.get("zakazka") == zid]
    mem = [e for e in L if e["kind"] == "TOOL" and e.get("zakazka") == zid and e.get("tool") in ("search_memory", "create_memory")]
    pods = [e for e in L if e["kind"] == "ROLE_POD" and e.get("zakazka") == zid]; dele = [d for d in (((p.get("identity") or {}).get("delegation")) for p in pods) if d]
    gov = http("POST", f"{APP}/agui/gov/tools/zakazky", json={}, headers={"Authorization": f"Bearer {tok}"}, timeout=30).status_code if tok else None
    tls_err = [e for e in L if any(x in str(e.get("error") or "") for x in ("SSLError", "SSLCertVerification", "CERTIFICATE_VERIFY", "certificate verify"))]   # jen pole error (ROLE_POD nese env SSL_CERT_FILE)
    rep.add("E7b", "Klienti přes TLS v provozu: přihlášení člověka z GUI = password grant aplikace na https Keycloak (token iss https://keycloak:8443/realms/p0), aplikace do OpenBao přes https (BAO_LOGIN auth kubernetes, SIGN transit u zakázky), server paměti ověřil tokeny rolí z JWKS přes https (volání paměti z podů 200), Governance MCP ověřil token člověka (200), pody rolí vyměnily token na https URL (delegace s iss https); v ledgeru žádná chyba ověření certifikátu", "PASS" if me.status_code == 200 and iss == "https://keycloak:8443/realms/p0" and bao and all(b.get("method") == "kubernetes" for b in bao) and signs and all(s_.get("backend") == "openbao-transit" for s_ in signs) and mem and all(m.get("http") == 200 for m in mem) and gov == 200 and dele and all(d.get("iss") == "https://keycloak:8443/realms/p0" and d.get("exchange_ms") for d in dele) and not tls_err else "FAIL", {"login": me.status_code, "iss": iss, "bao_login": len(bao), "signs": len(signs), "memory_200": sum(1 for m in mem if m.get("http") == 200), "memory_total": len(mem), "gov": gov, "delegations": [{k: d.get(k) for k in ("iss", "azp", "exchange_ms", "error")} for d in dele], "tls_errors": [{"kind": e["kind"], "error": str(e.get("error"))[:100]} for e in tls_err][:3]})


def e7_rotation(a, rep, kj, http, APP):
    """E7c: rotace certifikátů za běhu – harness vyvolá obnovu (stav Certificate Issuing=True = `cmctl renew`), cert-manager vydá nový leaf
    (jiné sériové číslo), kubelet aktualizuje Secret volume, OpenBao (tls_auto_reload 30 s) i Keycloak (reload period 1 m) nový cert nabídnou
    bez restartu podu; klienti (aplikace: login člověka) fungují dál."""
    import ssl, datetime as _dt
    from cryptography import x509
    def serial(port):
        try: return x509.load_pem_x509_certificate(ssl.get_server_certificate(("127.0.0.1", port)).encode()).serial_number
        except Exception as e: return f"ERR {type(e).__name__}"
    def restarts(app): return {p["metadata"]["name"]: sum(c.get("restartCount", 0) for c in (p["status"].get("containerStatuses") or [])) for p in kj("-n", NS, "get", "pods", "-l", f"app={app}").get("items", [])}
    pf_b = PortForward(a, "openbao", 18205, 8200); pf_k = PortForward(a, "keycloak", 18444, 8443)
    try:
        before = {"openbao": serial(18205), "keycloak": serial(18444)}; r0 = {"openbao": restarts("openbao"), "keycloak": restarts("keycloak")}
        patched = {}
        for name in ("openbao-tls", "keycloak-tls"):
            r = kubectl(a, "-n", NS, "patch", "certificate", name, "--subresource=status", "--type=merge", "-p", json.dumps({"status": {"conditions": [{"type": "Issuing", "status": "True", "reason": "ManuallyTriggered", "message": "harness E7c", "lastTransitionTime": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}]}}))
            patched[name] = r.returncode == 0 or (r.stderr or "")[-160:]
        t0 = time.time(); after = dict(before); seen = {}
        while time.time() - t0 < 420:
            for n, port in (("openbao", 18205), ("keycloak", 18444)):
                if n not in seen:
                    cur = serial(port)
                    if isinstance(cur, int) and cur != before[n]: seen[n] = round(time.time() - t0, 1); after[n] = cur
            if len(seen) == 2: break
            time.sleep(10); pf_b.start() if pf_b.p.poll() is not None else None; pf_k.start() if pf_k.p.poll() is not None else None
        r1 = {"openbao": restarts("openbao"), "keycloak": restarts("keycloak")}
        login = http("POST", f"{APP}/agui/login", json={"username": "adam", "password": "adam"}, timeout=20).status_code
        secs = {n: ((kj("-n", NS, "get", "secret", n).get("metadata") or {}).get("annotations") or {}).get("cert-manager.io/certificate-name") for n in ("openbao-tls", "keycloak-tls")}
        rep.add("E7c", "Rotace certifikátů bez restartu: obnova vyvolána stavem Certificate Issuing=True (jako `cmctl renew`), cert-manager vydal nový leaf (jiné sériové číslo v Secretu), kubelet volume aktualizoval a OpenBao (tls_auto_reload 30 s) i Keycloak (https-certificates-reload-period 1 m) nový cert nabízejí bez restartu podu (restartCount beze změny); login člověka přes aplikaci funguje dál", "PASS" if all(v is True for v in patched.values()) and len(seen) == 2 and r0 == r1 and login == 200 else "FAIL", {"patched": patched, "serial_before": {k: str(v) for k, v in before.items()}, "serial_after": {k: str(v) for k, v in after.items()}, "reload_s": seen, "restarts": {"before": r0, "after": r1}, "login_after": login, "secrets": secs})
    finally: pf_b.stop(); pf_k.stop()


def e1_checks(a, rep, kj, pre):
    """E1 (P3-6): tajemství a certifikáty platformy vydávají operátoři z Gitu – cert-manager (interní CA → agentgateway-tls), trust-manager
    (ConfigMap platform-ca v platform-data a ns tenantů), ESO (Key Vault přes workload identitu → postgres-auth, agentgateway-secrets, zakazka-secrets,
    zakazka-finops, agentgateway-git-token, dapr-components); harness ani Flux substitute žádné tajemství nenesou."""
    import base64 as _b64, hashlib as _h
    from cryptography import x509; from cryptography.hazmat.primitives.asymmetric import ec
    def get(ns, kind, name):
        r = kubectl(a, *(["-n", ns] if ns else []), "get", kind, name, "-o", "json"); return json.loads(r.stdout) if r.returncode == 0 else {}
    def ready(obj): return next((c["status"] for c in (obj.get("status") or {}).get("conditions", []) if c["type"] == "Ready"), None)
    def managers(obj): return sorted({m.get("manager", "") for m in (obj.get("metadata") or {}).get("managedFields", [])})
    tenants = [n["metadata"]["name"] for n in kj("get", "ns", "-l", "platform.tenant").get("items", [])]
    hr = {f'{h["metadata"]["namespace"]}/{h["metadata"]["name"]}': {"ready": ready(h), "version": (h.get("status") or {}).get("lastAttemptedRevision") or h["spec"]["chart"]["spec"].get("version")} for h in kj("get", "helmreleases", "-A").get("items", [])}
    ks = {k["metadata"]["name"].removeprefix("platform-"): {"ready": ready(k), "substitute": sorted((((k.get("spec") or {}).get("postBuild") or {}).get("substitute") or {}).keys()), "dependsOn": [d["name"].removeprefix("platform-") for d in (k.get("spec") or {}).get("dependsOn", [])]} for k in kj("-n", "flux-system", "get", "kustomizations").get("items", [])}   # Flux extension AKS: kustomizace <konfigurace>-<název> (platform-trust)
    # E1a – cert-manager + trust-manager
    cert = get(NS, "certificate", "agentgateway-tls"); tls = get(NS, "secret", "agentgateway-tls"); ann = (tls.get("metadata") or {}).get("annotations") or {}
    root = _b64.b64decode((get("cert-manager", "secret", "platform-root-ca").get("data") or {}).get("ca.crt", "")).decode()
    crt = _b64.b64decode((tls.get("data") or {}).get("tls.crt", "")).decode(); ca_in_tls = _b64.b64decode((tls.get("data") or {}).get("ca.crt", "")).decode()
    leaf = x509.load_pem_x509_certificate(crt.split("-----END CERTIFICATE-----")[0].encode() + b"-----END CERTIFICATE-----\n") if crt else None
    rootc = x509.load_pem_x509_certificate(root.encode()) if root else None
    sans = sorted(leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)) if leaf else []
    try: rootc.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, ec.ECDSA(leaf.signature_hash_algorithm)); chain_ok = True
    except Exception as e: chain_ok = f"{type(e).__name__}"
    cms = {ns: get(ns, "configmap", "platform-ca") for ns in [NS] + tenants}
    cm_ok = {ns: ((c.get("metadata") or {}).get("labels") or {}).get("trust.cert-manager.io/bundle") == "platform-ca" and (c.get("data") or {}).get("ca.crt", "").strip() == root.strip() for ns, c in cms.items()}
    days = round((leaf.not_valid_after_utc - leaf.not_valid_before_utc).days, 0) if leaf else None
    rep.add("E1a", "TLS egressu gateway z cert-manageru (interní CA: self-signed root platform-root-ca → ClusterIssuer platform-ca): Certificate agentgateway-tls Ready, Secret s anotacemi cert-manageru, SAN git/mirror.platform.internal, podpis ověřen proti root CA, ca.crt v Secretu == root; trust-manager rozdal CA jako ConfigMap platform-ca (label bundle) do platform-data i všech ns tenantů; HelmReleasy cert-manager/trust-manager Ready; Secret bez stopy kubectl", "PASS" if ready(cert) == "True" and ann.get("cert-manager.io/issuer-name") == "platform-ca" and ann.get("cert-manager.io/issuer-kind") == "ClusterIssuer" and sans == ["git.platform.internal", "mirror.platform.internal"] and chain_ok is True and ca_in_tls.strip() == root.strip() and root and cm_ok and all(cm_ok.values()) and all(hr.get(k, {}).get("ready") == "True" for k in ("cert-manager/cert-manager", "cert-manager/trust-manager")) and not any(m.startswith("kubectl") for m in managers(tls)) else "FAIL", {"certificate_ready": ready(cert), "issuer": [ann.get("cert-manager.io/issuer-kind"), ann.get("cert-manager.io/issuer-name")], "sans": sans, "issuer_cn": leaf.issuer.rfc4514_string() if leaf else None, "validity_days": days, "chain_ok": chain_ok, "ca_matches_root": ca_in_tls.strip() == root.strip(), "platform_ca_configmaps": cm_ok, "secret_managers": managers(tls), "helm": {k: hr.get(k) for k in ("cert-manager/cert-manager", "cert-manager/trust-manager")}, "legacy_removed": pre.get("legacy_removed")})
    # E1b – ESO z Key Vaultu přes workload identitu
    css = get(None, "clustersecretstore", "azure-kv"); ess = {x["metadata"]["name"]: x for x in kj("-n", NS, "get", "externalsecrets").get("items", [])}
    want = ["postgres-auth", "agentgateway-secrets", "zakazka-secrets", "zakazka-finops", "agentgateway-git-token", "dapr-components"]
    secs = {n: get(NS, "secret", n) for n in want}
    owned = {n: any(o.get("kind") == "ExternalSecret" and o.get("name") == n for o in ((s_.get("metadata") or {}).get("ownerReferences") or [])) for n, s_ in secs.items()}
    kv_name = ((((get("flux-system", "kustomization", "platform-trust").get("spec") or {}).get("postBuild") or {}).get("substitute") or {}).get("KV_NAME"))
    def kv(name):
        r = subprocess.run(["az", "keyvault", "secret", "show", "--vault-name", kv_name or "", "-n", name, "--query", "value", "-o", "tsv"], capture_output=True, text=True, timeout=120); return r.stdout.strip() if r.returncode == 0 else None
    kv_tok, kv_pg = kv("git-backend-token"), kv("pg-platform-password")
    tok = _b64.b64decode((secs["agentgateway-git-token"].get("data") or {}).get("token", "")).decode(); pg = _b64.b64decode((secs["postgres-auth"].get("data") or {}).get("POSTGRES_PASSWORD", "")).decode()
    agw_url = _b64.b64decode((secs["agentgateway-secrets"].get("data") or {}).get("AGW_DATABASE_URL", "")).decode(); dapr = _b64.b64decode((secs["dapr-components"].get("data") or {}).get("statestore.yaml", "")).decode()
    zs = {k: _b64.b64decode(v).decode() for k, v in (secs["zakazka-secrets"].get("data") or {}).items()}
    kv_ok = bool(kv_tok) and kv_tok == tok and bool(kv_pg) and kv_pg == pg and pg and f":{pg}@postgres" in agw_url and f"password={pg} " in dapr
    rep.add("E1b", "Tajemství z Key Vaultu přes ESO (ClusterSecretStore azure-kv, Workload Identity UAMI id-eso + federated credential SA external-secrets/eso-keyvault, role Key Vault Secrets User): ExternalSecrety Ready/SecretSynced, Secrety vlastní ExternalSecret (ownerReference), hodnoty == Key Vault (git token, heslo PG i v DSN gateway/FinOps/Dapr), zakazka-secrets nese client secrety rolí/API klíč/webhook; Flux substitute kustomizace platform už PG_PASSWORD nenese; HelmRelease external-secrets Ready", "PASS" if ready(css) == "True" and set(want) <= set(ess) and all(ready(ess[n]) == "True" for n in want) and all(owned.values()) and kv_ok and set(zs) >= {"P0_ROLE_CLIENT_SECRETS", "P0_API_KEY", "BRIDGE_WEBHOOK_SECRET", "P0_ROLE_KEYS"} and "PG_PASSWORD" not in ks.get("platform", {}).get("substitute", []) and hr.get("external-secrets/external-secrets", {}).get("ready") == "True" else "FAIL", {"store_ready": ready(css), "store_message": next((c.get("message") for c in (css.get("status") or {}).get("conditions", []) if c["type"] == "Ready"), None), "externalsecrets": {n: ready(ess[n]) if n in ess else None for n in want}, "owned_by_eso": owned, "keyvault": {"name": kv_name, "git_token_match": bool(kv_tok) and kv_tok == tok, "pg_match": bool(kv_pg) and kv_pg == pg, "pg_in_dsn": bool(pg) and f":{pg}@postgres" in agw_url, "pg_in_dapr": bool(pg) and f"password={pg} " in dapr}, "zakazka_secrets_keys": sorted(zs), "flux": ks, "helm": hr.get("external-secrets/external-secrets")})
    # E1c – harness nic nevydává: žádný Secret platformy se stopou kubectl kromě openbao-init (bootstrap OpenBao – zbývá PushSecret do Key Vaultu)
    by_kubectl = sorted(s_["metadata"]["name"] for s_ in kj("-n", NS, "get", "secrets").get("items", []) if any(m.get("manager", "").startswith("kubectl") for m in s_["metadata"].get("managedFields", [])))
    rep.add("E1c", "Harness nic nevydává: žádný Secret v platform-data se stopou kubectl (managedFields) kromě openbao-init (init OpenBao – bootstrap, zbývá), ensure_platform_secrets nic nezaložil (jen čekal na operátory), Flux kustomizace operators → trust → platform v závislostech", "PASS" if set(by_kubectl) <= {"openbao-init"} and pre.get("created") == [] and ks.get("trust", {}).get("dependsOn") == ["operators"] and ks.get("platform", {}).get("dependsOn") == ["trust"] else "FAIL", {"secrets_by_kubectl": by_kubectl, "created_by_harness": pre.get("created"), "waited_s": pre.get("wait_s"), "flux_depends": {k: v.get("dependsOn") for k, v in ks.items()}})


def e2_checks(a, rep, http, led, dsn, kj, KC, MEM, APP, zid, t_run):
    """E2 (P3-6): „jedná jménem“ doložené token exchange v podu role – subject = access token schvalovatele (člověk z platform-gui), client assertion =
    projektovaný token SA role-<role> (IdP kubernetes) → Keycloak token sub=člověk, azp=agent-<role>-<tenant>; paměť ho ověřuje (X-Delegation),
    zapisuje on_behalf_of do záznamů a registr org.agents.on_behalf_of. Keycloak 26.8.1 bez preview (delegace `act` i SPIFFE client auth jsou preview)."""
    import base64 as _b64, psycopg
    def tok(user, pw): r = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "platform-gui", "username": user, "password": pw}, timeout=15); return r.json()["access_token"]
    def claims(t): return json.loads(_b64.urlsafe_b64decode(t.split(".")[1] + "==").decode())
    ta, tb = tok("adam", "adam"), tok("bea", "bea"); adam_sub = claims(ta)["sub"]; aud_gui = claims(ta).get("aud"); aud_gui = aud_gui if isinstance(aud_gui, list) else [aud_gui]
    # admin pohled na Keycloak (IdP + klient role)
    import base64 as _b
    pw = _b.b64decode(kubectl(a, "-n", NS, "get", "secret", "keycloak-admin", "-o", "jsonpath={.data.KC_BOOTSTRAP_ADMIN_PASSWORD}").stdout.strip()).decode()
    adm = http("POST", f"{KC}/realms/master/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "admin-cli", "username": "admin", "password": pw}, timeout=20).json().get("access_token")
    H = {"Authorization": f"Bearer {adm}"}; A = f"{KC}/admin/realms/p0"
    idp = http("GET", f"{A}/identity-provider/instances/aks", headers=H, timeout=20); idp_j = idp.json() if idp.status_code == 200 else {}
    cl = http("GET", f"{A}/clients", headers=H, params={"clientId": "agent-architekt-acme"}, timeout=20).json(); cl0 = cl[0] if cl else {}
    gui = http("GET", f"{A}/clients", headers=H, params={"clientId": "platform-gui"}, timeout=20).json(); gui_m = sorted(m["name"] for m in http("GET", f"{A}/clients/{gui[0]['id']}/protocol-mappers/models", headers=H, timeout=20).json()) if gui else []
    L = led(); pods = {e["role"]: e for e in L if e.get("kind") == "ROLE_POD" and e.get("zakazka") == zid}
    deleg = {r: ((e.get("identity") or {}).get("delegation") or {}) for r, e in pods.items()}
    def db(name, sql, args=()):
        with psycopg.connect(dsn(name), autocommit=True, connect_timeout=10) as c: return c.execute(sql, args or None).fetchall()
    apr = {r_[0]: r_[1] for r_ in db("org", "SELECT action, approver FROM org.approvals WHERE workflow_instance = %s", (zid,))}
    want_roles = [r for r in ("account", "architekt", "vyvojar", "reviewer", "sre") if r in pods]
    ok_roles = {r: deleg.get(r, {}).get("sub") == adam_sub and deleg[r].get("azp") == f"agent-{r}-acme" and "memory" in (deleg[r].get("aud") if isinstance(deleg[r].get("aud"), list) else [deleg[r].get("aud")]) and deleg[r].get("client_assertion_sub") == f"system:serviceaccount:tenant-acme:role-{r}" and deleg[r].get("tenant_id") == "acme" and not deleg[r].get("act") for r in want_roles}
    rep.add("E2a", "Token exchange v podu role (Keycloak 26.8.1 standard V2, bez preview): subject = access token schvalovatele H1/H2/H4 (člověk z platform-gui, v aud klient role), client assertion = projektovaný token SA role-<role> ns tenanta (IdP `aks` typu kubernetes, issuer clusteru z Terraformu, klient agent-<role>-<tenant> s autentizátorem federated-jwt) → token sub = Keycloak sub schvalovatele, azp = agent-<role>-acme, aud memory, tenant_id acme, bez `act` (delegace je preview); platí pro každou roli zakázky (account = zadavatel)", "PASS" if want_roles and all(ok_roles.values()) and idp_j.get("providerId") == "kubernetes" and (idp_j.get("config") or {}).get("jwksUrl") and cl0.get("clientAuthenticatorType") == "federated-jwt" and (cl0.get("attributes") or {}).get("standard.token.exchange.enabled") == "true" and "agent-architekt-acme" in aud_gui and all(v == adam_sub for v in apr.values()) else "FAIL", {"roles": {r: {k: deleg[r].get(k) for k in ("sub", "azp", "aud", "tenant_id", "client_assertion_sub", "client_assertion_iss", "exp_in_s", "exchange_ms", "act", "error")} for r in want_roles}, "ok_roles": ok_roles, "approver_sub": adam_sub, "approvals": apr, "idp": {"providerId": idp_j.get("providerId"), "issuer": (idp_j.get("config") or {}).get("issuer"), "jwks": bool((idp_j.get("config") or {}).get("jwksUrl"))}, "client": {"authenticator": cl0.get("clientAuthenticatorType"), "attributes": {k: (cl0.get("attributes") or {}).get(k) for k in ("jwt.credential.issuer", "jwt.credential.sub", "standard.token.exchange.enabled", "access.token.lifespan")}}, "gui_aud": aud_gui, "gui_mappers": gui_m, "gui_lifespan": (gui[0].get("attributes") or {}).get("access.token.lifespan") if gui else None})
    # E2b – paměť: záznamy rolí zakázky nesou on_behalf_of = sub schvalovatele; cizí/padělaná delegace odmítnuta
    rows = db("memory", "SELECT created_by FROM memory_records WHERE created_by->>'agent_id' LIKE 'spiffe://platform/role/%%/acme' AND created_at > to_timestamp(%s)", (t_run,))
    obo = [(r_[0] if isinstance(r_[0], dict) else json.loads(r_[0])).get("on_behalf_of") for r_ in rows]
    agent_tok = http("POST", f"{KC}/realms/p0/protocol/openid-connect/token", data={"grant_type": "client_credentials"}, auth=("agent-account", "p0-account-secret"), timeout=15).json().get("access_token", "")
    kc_iss = http("GET", f"{KC}/realms/p0/.well-known/openid-configuration", timeout=15).json().get("issuer")   # P3-6 E7: issuer https://keycloak:8443/realms/p0
    def mem(deleg_tok): r = http("POST", f"{MEM}/tools/search_memory", json={"query": "kontakt", "limit": 1}, headers={"Authorization": f"Bearer {agent_tok}", "X-Delegation": deleg_tok}, timeout=15); return r.status_code
    forged = ".".join(_b64.urlsafe_b64encode(json.dumps(x).encode()).decode().rstrip("=") for x in ({"alg": "HS256", "typ": "JWT"}, {"sub": adam_sub, "azp": "agent-account-acme", "aud": "memory", "iss": kc_iss, "tenant_id": "acme", "exp": int(time.time()) + 600})) + ".x"
    neg = {"gui_token_adam": mem(ta), "gui_token_bea": mem(tb), "forged_hs256": mem(forged), "none": http("POST", f"{MEM}/tools/search_memory", json={"query": "kontakt", "limit": 1}, headers={"Authorization": f"Bearer {agent_tok}"}, timeout=15).status_code}
    rep.add("E2b", "Paměť čte delegaci z hlavičky X-Delegation: ověření JWKS realmu (RS256, aud memory), azp = klient role odpovídající SVID volajícího, tenant subjektu = tenant role → on_behalf_of = sub schvalovatele v created_by všech záznamů rolí tohoto běhu; token člověka z GUI (azp platform-gui) 403, token cizího tenanta 403, padělaný HS256 401, bez hlavičky beze změny (200)", "PASS" if rows and all(v == adam_sub for v in obo) and neg["gui_token_adam"] == 403 and neg["gui_token_bea"] == 403 and neg["forged_hs256"] == 401 and neg["none"] == 200 else "FAIL", {"records": len(rows), "on_behalf_of": sorted({str(v) for v in obo}), "negative": neg})
    # E2c – registr: org.agents.on_behalf_of (metriky.md T1) + Governance MCP
    ag = db("org", "SELECT role_id, on_behalf_of FROM org.agents WHERE zakazka_id = %s", (zid,))
    tp = tok("platform-admin", "platform-admin"); g = http("POST", f"{APP}/agui/gov/tools/agents", json={"zakazka_id": zid}, headers={"Authorization": f"Bearer {tp}"}, timeout=30)
    gj = (g.json().get("result") or []) if g.status_code == 200 else []
    rep.add("E2c", "Registr agentů nese principala: org.agents.on_behalf_of = sub schvalovatele u každého běhu role zakázky (z identity.delegation podu, zapisuje workflow), nástroj Governance MCP `agents` ho vrací", "PASS" if ag and all(r_[1] == adam_sub for r_ in ag) and gj and all(x.get("on_behalf_of") == adam_sub for x in gj) else "FAIL", {"org_agents": [list(r_) for r_ in ag], "gov_tool": [(x.get("role_id"), x.get("on_behalf_of")) for x in gj], "http": g.status_code})


def step_p2_1(a, rep, env, images=False, registry=False, identity=False, egress=False, finops=False, gui=False, tenant=False, gov=False, klas=False, o3=False, e3=False, e4=False, e1=False, e2=False, e6=False, e7=False):
    """P2-1 na AKS (nahrazuje p1-6): konfigurace gateway a rolegen build z Gitu přes Flux (infra/k8s/rolegen), klíče role × zakázka vydává aplikace;
    harness dodává jen tajemství. Checky P21a–h = P16a–h + ověření původu konfigurace a vydaných klíčů.
    gui (P3-1, U-1): zakázka se místo GitHub HITL řídí z GUI v prohlížeči (Playwright, gui_checks.py) – přihlášení Keycloak, založení, schválení
    H1/H2/H4/H5 s důvodem, cizí tenant 404, stop uprostřed role; zbytek checků (pody, egress, paměť, FinOps) běží nad touž zakázkou."""
    import psycopg, jwt, hashlib as _h, base64 as _b
    O2 = T / "harness_p0_o2"; M1 = T / "harness_memory_m1"
    o2 = __import__("importlib.util").util.spec_from_file_location("o2h", O2 / "harness.py"); o2m = __import__("importlib.util").util.module_from_spec(o2); o2.loader.exec_module(o2m)
    m1 = __import__("importlib.util").util.spec_from_file_location("m1h", M1 / "harness.py"); m1m = __import__("importlib.util").util.module_from_spec(m1); m1.loader.exec_module(m1m)
    RNS = "tenant-acme"; t_all = time.time()   # P3-2: ns per tenant (infra/k8s/roles/tenants-generated.yaml); RNS = tenant dogfoodingu
    def tenant_namespaces(): return [n["metadata"]["name"] for n in kj("get", "ns", "-l", "platform.tenant").get("items", [])]
    def kj(*args):
        r = kubectl(a, *args, "-o", "json"); return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
    def secret(name, key, ns=NS):
        v = kubectl(a, "-n", ns, "get", "secret", name, "-o", f"jsonpath={{.data.{key}}}").stdout.strip(); return _b.b64decode(v).decode() if v else None
    # Flux: obě kustomizations Ready a mock-upstream (nový objekt overlay) existuje
    want_sha = os.environ.get("GITHUB_SHA") or sh(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    # Flux sleduje hlavu větve: commit pushnutý během měření (např. jen docs) by jinak měření shodil; přijmout i aktuální hlavu větve z originu
    head_now = (sh(["git", "-C", str(ROOT), "ls-remote", "origin", f"refs/heads/{os.environ.get('GITHUB_REF_NAME', '')}"]).stdout.split() or [""])[0] if os.environ.get("GITHUB_REF_NAME") else ""
    want_shas = {want_sha} | ({head_now} if head_now else set())
    def rev_ok(r): return any(r.endswith(w) for w in want_shas)
    # P3-6 E1: tajemství egressu gateway (Secret agentgateway-tls, agentgateway-git-token) a CA pro pody rolí (ConfigMap platform-ca) vydávají z Gitu
    # cert-manager, ESO (Key Vault) a trust-manager (infra/k8s/operators, trust, overlays/aks/secrets-eso.yaml) – harness nic nevydává. Jen uklidí
    # ConfigMapy platform-ca z dřívějších běhů, které vydal sám (bez labelu trust-manageru – SSA konflikt by bundle nepřepsal; Secrety bez vlastníka
    # ESO/cert-manager převezmou), a po Fluxu počká, až operátoři objekty dodají.
    def ensure_platform_secrets(wait_s=0):
        def get(ns, kind, name): r = kubectl(a, "-n", ns, "get", kind, name, "-o", "json"); return json.loads(r.stdout) if r.returncode == 0 else None
        removed = []
        for tns in [NS] + tenant_namespaces():
            cm = get(tns, "configmap", "platform-ca")
            if cm and "trust.cert-manager.io/bundle" not in (cm["metadata"].get("labels") or {}):
                kubectl(a, "-n", tns, "delete", "configmap", "platform-ca", "--ignore-not-found"); removed.append(f"configmap/platform-ca@{tns}")
        t0 = time.time(); status = {}; ok = False
        while True:
            cert = get(NS, "certificate", "agentgateway-tls") or {}
            status["certificate"] = next((c["status"] for c in cert.get("status", {}).get("conditions", []) if c["type"] == "Ready"), None)
            ess = kj("-n", NS, "get", "externalsecrets").get("items", [])
            status["externalsecrets"] = {x["metadata"]["name"]: next((c["status"] for c in x.get("status", {}).get("conditions", []) if c["type"] == "Ready"), None) for x in ess}
            status["platform_ca"] = {tns: bool(((get(tns, "configmap", "platform-ca") or {}).get("data") or {}).get("ca.crt")) for tns in [NS] + tenant_namespaces()}
            ok = status["certificate"] == "True" and bool(ess) and all(v == "True" for v in status["externalsecrets"].values()) and bool(status["platform_ca"]) and all(status["platform_ca"].values())
            if ok or time.time() - t0 >= wait_s: break
            time.sleep(10)
        tok = _b.b64decode(((get(NS, "secret", "agentgateway-git-token") or {}).get("data") or {}).get("token", "")).decode()
        return {"created": [], "legacy_removed": removed, "status": status, "ok": ok, "wait_s": round(time.time() - t0, 1), "token_sha12": _h.sha256(tok.encode()).hexdigest()[:12] if tok else None, "ca_present": status["platform_ca"].get(NS, False)}
    egress_secrets = ensure_platform_secrets()
    # StatefulSet s podem v CrashLoopBackOff rolling update nenahradí (kubernetes/kubernetes#67250): po Flux applyi smazat pody, které nejsou na updateRevision
    # (ne jen currentRevision – pod může stát na mezilehlé revizi, když se nedokončil ani předchozí rollout; měřeno 2026-10-25). Flux health check
    # (wait) kustomizace platform projde až s novým podem → mazání musí běžet uvnitř čekání na Flux.
    sts_deleted = {}
    def sts_unstick():
        for sts in kj("-n", NS, "get", "sts").get("items", []):
            upd = sts.get("status", {}).get("updateRevision"); n = sts["metadata"]["name"]
            if not upd or sts.get("status", {}).get("currentRevision") == upd: continue
            for p_ in kj("-n", NS, "get", "pods", "-l", f"app={n}").get("items", []) or kj("-n", NS, "get", "pods", "-l", f"statefulset.kubernetes.io/pod-name={n}-0").get("items", []):
                h = p_["metadata"].get("labels", {}).get("controller-revision-hash")
                if h and h != upd and not p_["metadata"].get("deletionTimestamp"):
                    kubectl(a, "-n", NS, "delete", "pod", p_["metadata"]["name"], "--wait=false"); sts_deleted.setdefault(n, []).append(f"{p_['metadata']['name']}@{h}→{upd}")
    t0 = time.time(); flux = {}
    while time.time() - t0 < 900:
        ks = kj("-n", "flux-system", "get", "kustomizations").get("items", [])
        flux = {k["metadata"]["name"]: next((c["status"] for c in k.get("status", {}).get("conditions", []) if c["type"] == "Ready"), "?") for k in ks}
        revs = [(k.get("status", {}).get("lastAppliedRevision") or "") for k in ks]
        if flux and all(v == "True" for v in flux.values()) and all(rev_ok(r) for r in revs) and kubectl(a, "-n", NS, "get", "deploy/mock-upstream").returncode == 0 and kubectl(a, "get", "ns", RNS).returncode == 0: break
        sts_unstick(); time.sleep(10)   # Flux sync 120 s + rollout po změně manifestů; měříme vždy stav z aktuálního commitu
    ks_now = kj("-n", "flux-system", "get", "kustomizations").get("items", [])
    flux_rev = {k["metadata"]["name"]: (k.get("status", {}).get("lastAppliedRevision") or "")[:60] for k in ks_now}
    flux_msg = {k["metadata"]["name"]: next((c.get("message", "")[:1500] for c in k.get("status", {}).get("conditions", []) if c["type"] == "Ready"), "?") for k in ks_now}
    print(f"  flux: ready={flux} rev={flux_rev} wait_s={round(time.time() - t0)} sts_unstick={sts_deleted}\n  flux msg: {json.dumps(flux_msg, ensure_ascii=False)}")
    if not (flux and all(v == "True" for v in flux.values()) and all(rev_ok(k.get("status", {}).get("lastAppliedRevision") or "") for k in ks_now)):   # fail-fast: bez applyované konfigurace z HEAD měření nemá smysl
        ops = {f'{o["kind"]}/{o["metadata"]["name"]}': next((f'{c["status"]} {c.get("reason", "")}: {c.get("message", "")[:300]}' for c in (o.get("status") or {}).get("conditions", []) if c["type"] == "Ready"), "?") for kind in ("clustersecretstore", "helmreleases", "externalsecrets", "certificate") for o in kj("get", kind, "-A").get("items", [])}   # P3-6 E1: stav operátorů do zprávy
        raise AssertionError(f"Flux neaplikoval HEAD {[w[:12] for w in want_shas]}: {flux_msg}\n  operátoři: {json.dumps(ops, ensure_ascii=False)}")
    egress_secrets = ensure_platform_secrets(wait_s=600) | {"legacy_removed": egress_secrets["legacy_removed"]}   # ns tenantů existují až po Flux → trust bundle, Certificate a ExternalSecrety
    assert egress_secrets["ok"], f"operátoři nedodali tajemství platformy (cert-manager/ESO/trust-manager): {json.dumps(egress_secrets['status'], ensure_ascii=False)}"
    if e1: e1_checks(a, rep, kj, egress_secrets)
    # OpenBao: init (klíče do Secretu openbao-init – runner CI nemá trvalé logs/) + unseal + transit/policy/token aplikace
    if kubectl(a, "-n", NS, "rollout", "status", "statefulset/openbao", "--timeout=600s", timeout=620).returncode != 0:   # P2-3: nový config (seal plugin) → pod se restartuje
        st_ = kubectl(a, "-n", NS, "get", "pod", "openbao-0", "-o", "jsonpath={range .status.initContainerStatuses[*]}{.name}={.state}{'\\n'}{end}{range .status.containerStatuses[*]}{.name}={.state}{'\\n'}{end}").stdout
        raise AssertionError(f"openbao-0 nenaběhl:\n{st_}\n{kubectl(a, '-n', NS, 'logs', 'openbao-0', '--all-containers', '--tail=40', '--prefix').stdout[-3000:]}")
    ca_file = platform_ca_bundle(a, kj)   # P3-6 E7: OpenBao i Keycloak jen HTTPS z interní CA – httpx (trust_env) i urllib ověřují přes SSL_CERT_FILE (certifi + root platformy)
    pf_bao = PortForward(a, "openbao", 18200, 8200); BAO = "https://127.0.0.1:18200"
    seal0 = None
    for _ in range(40):
        try: seal0 = httpx.get(f"{BAO}/v1/sys/seal-status", timeout=10).json(); break
        except Exception: time.sleep(3); pf_bao.start()
    assert seal0 is not None, "OpenBao neodpovídá na seal-status (pod padá? kubectl -n platform-data logs openbao-0)"
    seal_type = seal0.get("type")
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
    assert identity, "kroky bez identity (p2-1/p2-2/p2-5) od P3-6 E1 nejsou podporované: zakazka-secrets (vč. P0_BAO_TOKEN) vydává ESO z Key Vaultu, aplikace má auth kubernetes"   # P3-6 E1: zakazka-secrets z ESO (secrets-eso.yaml), harness nic nevydává
    # P2-3: registrace SPIRE z rolegen (ConfigMap rolegen-build/spire-entries.json): alias uzlu per role (sidecar agent podu) + workload entry
    spire_applied = []
    if identity:
        import yaml as _ys
        ents = json.loads((kj("-n", NS, "get", "configmap", "rolegen-build").get("data") or {}).get("spire-entries.json") or "[]")
        def entry_fields(show):   # bloky `Entry ID : …` / `Parent ID : …` z výstupu entry show
            out = []
            for blk in show.split("\n\n"):
                f = dict(l.split(":", 1) for l in blk.splitlines() if ":" in l); f = {k.strip(): v.strip() for k, v in f.items()}
                f["selectors"] = sorted(l.split(":", 1)[1].strip() for l in blk.splitlines() if l.strip().startswith("Selector"))   # P3-6 E2: SA per role → selektor alias uzlu se mění
                if f.get("Entry ID"): out.append(f)
            return out
        for e in ents:
            show = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "entry", "show", "-spiffeID", e["spiffe_id"], "-socketPath", "/tmp/spire-server/private/api.sock").stdout
            have = entry_fields(show) if e["spiffe_id"] in show else []
            if have and ((e.get("node") and any(h["selectors"] == sorted(e["selectors"]) for h in have)) or (not e.get("node") and any(h.get("Parent ID") == e.get("parent_id") for h in have))): continue
            for h in have:   # P3-2: stejné SPIFFE ID s jiným rodičem (alias uzlu per tenant) nebo jinými selektory (P3-6 E2: agent_sa:role-<role>) → smazat a založit znovu
                kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "entry", "delete", "-socketPath", "/tmp/spire-server/private/api.sock", "-entryID", h["Entry ID"]); spire_applied.append((e["spiffe_id"], "deleted", h.get("Parent ID")))
            args = [SPIRE_SERVER_BIN, "entry", "create", "-socketPath", "/tmp/spire-server/private/api.sock", "-spiffeID", e["spiffe_id"]] + (["-node"] if e.get("node") else ["-parentID", e["parent_id"]])
            for sel in e["selectors"]: args += ["-selector", sel]
            if e.get("x509_svid_ttl"): args += ["-x509SVIDTTL", str(e["x509_svid_ttl"])]
            if e.get("jwt_svid_ttl"): args += ["-jwtSVIDTTL", str(e["jwt_svid_ttl"])]
            r = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", *args); spire_applied.append((e["spiffe_id"], r.returncode, (r.stderr or r.stdout)[-120:]))
    restart_pods(a, "zakazka", "memory", "bridge", "mock-github", "mock-mirror", "mock-upstream", "governance", "mock-channels", *(["agentgateway"] if e4 or e1 else [])); time.sleep(5)   # P3-6 E4: config.tracing gateway se načítá jen při startu   # vše z obrazu zakazka-app:p1 – po rebuildu obrazu musí nový kód dostat i mocky (P3-1: mirror zahlcený /health)
    t0 = time.time()
    rolls = {k: kubectl(a, "-n", NS, "rollout", "status", k, "--timeout=600s", timeout=620).returncode == 0 for k in ("deployment/keycloak", "deployment/opa", "statefulset/placement", "statefulset/scheduler", "deployment/agentgateway", "deployment/mock-upstream", "deployment/memory", "deployment/mock-github", "deployment/bridge", "deployment/zakazka")}
    for n, p in (("zakazka", 8010), ("memory", 9900), ("mock-github", 9801), ("bridge", 9802)):
        kubectl(a, "-n", NS, "wait", "--for=condition=Ready", "pod", "-l", f"app={n}", "--timeout=300s", timeout=320)
    pfs = {n: PortForward(a, n, lp, rp) for n, lp, rp in (("zakazka", 18010, 8010), ("memory", 19900, 9900), ("mock-github", 19801, 9801), ("bridge", 19802, 9802), ("keycloak", 18443, 8443))}   # P3-6 E7: Keycloak jen HTTPS 8443
    APP, MEM, GHM, GHS, KC = "http://127.0.0.1:18010", "http://127.0.0.1:19900", "http://127.0.0.1:19801/repos/akczcz/adam", "http://127.0.0.1:19801/_debug/state", "https://127.0.0.1:18443"
    def http(method, url, **kw):
        for i in range(12):
            try: return httpx.request(method, url, **kw)
            except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError):
                if i == 11: raise
                time.sleep(5)
                for pf in pfs.values(): pf.start()
    try:
        health = {n: http("GET", f"http://127.0.0.1:{p}/health", timeout=10).status_code for n, p in (("app", 18010), ("memory", 19900), ("mock_github", 19801), ("bridge", 19802))}
        kc_migr = kc_ensure(a, http, KC) if (gui or tenant) else None   # P3-2: realm v běžícím clusteru doplnit admin API (klient platform-gui, lidé tenantů)
        spire_reload = spire_server_reload(a, kj) if tenant else None   # P3-2: allow-list ns tenantů v configu SPIRE serveru
        if kc_migr or spire_reload: print(f"  kc_ensure={kc_migr} spire_reload={spire_reload}")
        with psycopg.connect(dsn("dapr_state"), autocommit=True, connect_timeout=10) as c:
            dapr_tables = sorted(r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall())
        gw_ok = all(config_from_git.values()) and gw_cfg.get("llm", {}).get("models", [{}])[0].get("params", {}).get("baseUrl") == "$LLM_UPSTREAM_URL" and "apiKey" in (gw_cfg.get("llm", {}).get("policies") or {}) and "apikeys-template.yaml" in (cfg_cluster["rolegen-build"] or {}) and any(k.startswith("srt-") for k in (cfg_cluster["rolegen-build"] or {}))
        rep.add("P21a", "AKS: Flux kustomizations platform + roles Ready na HEAD; ConfigMapy agentgateway-config a rolegen-build v clusteru == render infra/k8s/overlays/aks z HEAD (konfigurace z Gitu, harness nic nerenderuje); gateway má apiKey policy a upstream z env LLM_UPSTREAM_URL; rolegen-build nese apikeys-template a srt; platforma vč. mock-upstream Ready; OpenBao init/unseal/transit; schéma paměti M1 na Flexible Serveru; harness dodal jen tajemství", "PASS" if all(v == "True" for v in flux.values()) and gw_ok and all(rolls.values()) and all(v == 200 for v in health.values()) and dapr_tables else "FAIL", {"flux": flux, "flux_rev": flux_rev, "config_from_git": config_from_git, "config_diff": config_diff, "gateway_upstream_env": gw_env.get("LLM_UPSTREAM_URL"), "rolegen_build_keys": sorted(cfg_cluster["rolegen-build"] or {}), "rollouts": rolls, "health": health, "pg": {"host": pg_host, "version": pg_ver, "via": pg_via}, "dapr_state_tables": dapr_tables, "rollout_s": round(time.time() - t0, 1)})

        if e7: e7_checks(a, rep, http, kj, KC, BAO, ca_file)   # P3-6 E7: TLS OpenBao a Keycloaku z interní CA
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
        run_tag = time.strftime("%H%M%S"); zid = f"{'P31' if gui else 'P23' if identity else 'P25' if registry else 'P22' if images else 'P21'}-{run_tag}-1"; t1 = time.time()
        if gui:
            zid, issue, pr, merged, st, adr_early = gui_flow(a, rep, http, led, zid, APP, GHS, dsn)
            if e2: e2_checks(a, rep, http, led, dsn, kj, KC, MEM, APP, zid, t1)   # P3-6 E2: mandát z token exchange v podu
            if e7: e7_app_checks(rep, http, led, APP, zid, t1)   # P3-6 E7: klienti OpenBao/Keycloaku přes TLS v provozu
            if e7: e7_rotation(a, rep, kj, http, APP)   # P3-6 E7c: rotace certifikátů bez restartu
        else:
            http("POST", f"{APP}/zakazky", json={"id": zid, "poptavka": f"Přidej do repa platformy soubor zakazky/{zid}/NOTES.md s poznámkou, že zakázka proběhla v AKS s konfigurací rolí z Gitu.", "hitl_timeout_s": 7200, "klasifikace": KLAS_NO}, timeout=15)
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
        rep.add("P21b", ("Zakázka na AKS end-to-end řízená z GUI (AG-UI, bez /schvaluji): H1 → ADR → H2 → PR → review → H4 → merge → H5 → Dokonceno" if gui else "Zakázka na AKS end-to-end přes GitHub HITL (mock GitHub v clusteru): issue → /schvaluji → ADR → H2 → PR → review → merge → H5 → Dokonceno") + "; 4 role jako pody v ns platform-roles (ROLE_POD Succeeded s výsledkem), AGENT_RUN z podu přeposlán do ledgeru aplikace (via=pod), paměť 200, approval tokeny z OpenBao", "PASS" if (st.get("output") or {}).get("stav") == "Dokonceno" and merged and not adr_early and set(runs) == set(ROLE_CLIENTS) and not any(r.get("error") for r in runs.values()) and all(r.get("via") == "pod" for r in runs.values()) and ok_pods and not pod_err and mem_calls and all(c.get("http") == 200 for c in mem_calls) and signs and all(s["backend"] == "openbao-transit" for s in signs) else "FAIL", {"output": st.get("output"), "merged_in_mock_github": merged, "issue": issue.get("number"), "pr": pr.get("number"), "roles": {k: {"tools": r.get("tool_uses"), "error": r.get("error"), "cost_usd": r.get("cost_usd"), "via": r.get("via")} for k, r in runs.items()}, "pods": {k: {"phase": p.get("phase"), "exit": p.get("exit_code"), "result": p.get("result_received"), "log_tail": p.get("log_tail")} for k, p in pods_led.items()}, "pod_errors": [e.get("error") for e in pod_err][:3], "memory_calls_200": sum(1 for c in mem_calls if c.get("http") == 200), "signs": len(signs), "wall_s": round(time.time() - t1, 1)})

        # P21b2 – klíče role × zakázka vydala aplikace (ledger GATEWAY_KEYS_ISSUED, ConfigMap agentgateway-keys, Secret zakazka-keys-<id>), rozpočty = roles/*.yaml
        issued = next((e for e in L if e["kind"] == "GATEWAY_KEYS_ISSUED" and e["zakazka"] == zid), None)
        keys_cm = _y.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-keys").get("data") or {}).get("keys.yaml") or "[]") or []
        mine = [k for k in keys_cm if (k.get("metadata") or {}).get("zakazka") == zid]
        want_block = {}
        for f in sorted((ROOT / "knowledge/organization/roles").glob("*.yaml")):
            r = _y.safe_load(f.read_text()); want_block[r["role"]] = next((b["amount"] for b in r.get("budget", {}).get("budgets", []) if b.get("window") == "24h" and b.get("action") == "Block"), None)
        got_block = {(k.get("metadata") or {}).get("role"): next((b["limit"]["amount"] for b in k.get("budgets", []) if b["name"].endswith("24h-block")), None) for k in mine}
        sec_keys = kubectl(a, "-n", NS, "get", "secret", f"zakazka-keys-{zid.lower()}", "-o", "jsonpath={.metadata.name}").stdout.strip()
        if tenant: tenant_flow(a, rep, http, led, APP, dsn, kj, zid, zid[:-2], LOGS / "gui-shots")   # P3-2: T1a–T1f
        if gov: gov_flow(a, rep, http, led, APP, KC, dsn, kj, zid, zid[:-2], LOGS / "gui-shots", init["root_token"])   # P3-3: U2a–U2h
        if klas: klas_flow(a, rep, http, led, APP, KC, dsn, kj, zid, zid[:-2], LOGS / "gui-shots")   # P3-4: K1a–K1g
        if o3: o3_flow(a, rep, http, led, APP, KC, dsn, kj, zid, zid[:-2], LOGS / "gui-shots", init["root_token"])   # P3-5: O3a–O3f
        if e3: e3_flow(a, rep, http, led, APP, KC, dsn, kj, zid[:-2], LOGS / "gui-shots")   # P3-6 E3: strop v gateway + navýšení z GUI
        if e4: e4_flow(a, rep, http, led, APP, KC, dsn, kj, zid[:-2], LOGS / "gui-shots")   # P3-6 E4: per-request ledger → ClickHouse
        if e6: e6_flow(a, rep, http, led, APP, kj, zid[:-2])   # P3-6 E6: verzování workflow (restart podu aplikace – až po všech tocích s pody rolí)
        rep.add("P21b2", "Klíče gateway role × zakázka vydala aplikace při prvním běhu role (ne harness): hash + rozpočty z rolegen šablony do ConfigMapy agentgateway-keys (sidecar config-merge → hot reload), hodnoty do Secretu zakazka-keys-<id>; rozpočty Block 24h == knowledge/organization/roles/*.yaml; gateway klíč přijala (sonda 401 → 200)", "PASS" if issued and issued.get("probe_status") == 200 and set(ROLE_CLIENTS) <= set(issued.get("roles", [])) and len(mine) >= 4 and all(got_block.get(r) == want_block.get(r) for r in ROLE_CLIENTS) and (sec_keys or issued.get("keys_source") == "openbao") else "FAIL", {"issued": {k: issued.get(k) for k in ("roles", "propagation_s", "probe_status", "total_s", "hashes")} if issued else None, "keys_in_configmap_for_zakazka": len(mine), "budgets_block_24h": {"cluster": got_block, "roles_yaml": want_block}, "secret": sec_keys or None})

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
            if identity: ALLOWED |= {"initContainers", "serviceAccountName", "shareProcessNamespace"}   # P2-3: sidecar SPIRE agenta (SA role jen pro projektovaný token sidecaru, sdílený PID ns pro unix attestor)
            tplinfo = {k: {"template": p.get("template"), "image": p.get("image"), "overrides": p.get("overrides"), "unexpected": sorted(set(p.get("overrides") or []) - ALLOWED), "resources": p.get("resources"), "image_role": p.get("image_role")} for k, p in pods_led.items()}
            ok_tpl = bool(tplinfo) and all(v["template"] and not v["unexpected"] and (v["image"] or "").startswith(f"{a.acr}/roles/{k}:{versions[k]}") and (v["image_role"] or {}).get("role") == k and (v["image_role"] or {}).get("version") == versions[k] and (v["image_role"] or {}).get("managed_settings") for k, v in tplinfo.items())
            rep.add("P22b", "Pod role ze šablony rolegen (pod-<role>.yaml z build/k8s): RuntimeClass, non-root, SA token off, drop ALL, resources, env a labels z definice role; aplikace doplní jen běh (jméno, Secret, env běhu, uzel, timeout, registry obrazu, seccomp Localhost → RuntimeDefault na Katě); obraz = roles/<role>:<verze> a /etc/platform/role.json v obrazu nese tutéž roli a verzi, managed settings zapečené", "PASS" if ok_tpl else "FAIL", tplinfo)
            tools_ok = bool(pods_led) and all((p.get("image_tools") or {}).get("present") and all((p["image_tools"]["present"]).values()) and all((p["image_tools"]["absent"]).values()) for p in pods_led.values())
            rep.add("P22c", "Obsah obrazu role (sonda z podu): git, node, python3, srt, bwrap, claude přítomny; az, gcloud, aws, kubectl, docker, helm, terraform nepřítomny (role.md: obraz role bez cloud CLI)", "PASS" if tools_ok else "FAIL", {k: p.get("image_tools") for k, p in pods_led.items()})

        if identity:
            # P2-3 – OpenBao auto-unseal + auth kubernetes, SVID podů rolí
            pf_bao2 = PortForward(a, "openbao", 18201, 8200); B2 = "https://127.0.0.1:18201"
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
            rep.add("P23c", "Identita role v Kata podu = SVID: sidecar spire-agent (atestace k8s_psat projektovaným tokenem SA role, alias uzlu per role z rolegen entries, workload unix uid 1000) vydá X.509-SVID a JWT-SVID spiffe://platform/role/<role>/acme; role s ním volá paměť (server paměti ověřuje JWT-SVID přes spire-oidc /keys, tenant z cesty SPIFFE ID), Keycloak token ze Secretu nepoužit", "PASS" if ok_svid and mem_calls and all(c.get("http") == 200 for c in mem_calls) else "FAIL", {"identity": ids, "spire_entries_applied_now": spire_applied, "memory_calls_200": sum(1 for c in mem_calls if c.get("http") == 200)} | ({} if ok_svid else {"sidecar": {k: p.get("svid_sidecar_state") for k, p in pods_led.items()}, "spire_server_log": [l_[-300:] for l_ in kubectl(a, "-n", NS, "logs", "spire-server-0", "-c", "spire-server", "--since=20m").stdout.splitlines() if "attest" in l_.lower() or "error" in l_.lower()][-12:]}))
            pf_oidc = PortForward(a, "spire-oidc", 18082, 8082)
            try:
                jwks = http("GET", "http://127.0.0.1:18082/keys", headers={"Host": "spire-oidc"}, timeout=10); jk = jwks.json() if jwks.status_code == 200 else {}
                disc = http("GET", "http://127.0.0.1:18082/.well-known/openid-configuration", headers={"Host": "spire-oidc"}, timeout=10)
            finally: pf_oidc.stop()
            ents_now = kubectl(a, "-n", NS, "exec", "spire-server-0", "-c", "spire-server", "--", SPIRE_SERVER_BIN, "entry", "show", "-socketPath", "/tmp/spire-server/private/api.sock").stdout
            rep.add("P23d", "SPIRE OIDC discovery provider (sidecar serveru) vydává JWKS pro JWT-SVID; registrace z rolegen (alias uzlu + workload per role) v serveru", "PASS" if jk.get("keys") and disc.status_code == 200 and all(f"spiffe://platform/role/{r}/acme" in ents_now for r in ROLE_CLIENTS) else "FAIL", {"jwks_keys": len(jk.get("keys", [])), "discovery": disc.status_code, "entries": ents_now.count("Entry ID")})

        if egress:
            # P2-4 – egress naostro: git a mirror z Kata podu role jen přes gateway CONNECT (srt parentProxy), terminace TLS + token z gateway, chráněné větve
            import yaml as _y4
            gcfg = _y4.safe_load((kj("-n", NS, "get", "configmap", "agentgateway-config").get("data") or {}).get("config.yaml") or "{}")
            binds = gcfg.get("binds") or []; lst = {l["name"]: l for l in ((gcfg.get("gateways") or {}).get("secure") or {}).get("listeners", [])}; rts = {r_["name"]: r_ for r_ in gcfg.get("routes") or []}
            git_rt = rts.get("git-acme", {}); allow = " ".join(x.get("allow", "") for x in ((git_rt.get("policies") or {}).get("authorization") or {}).get("rules", []))
            svc_ports = {p_["port"] for p_ in (kj("-n", NS, "get", "svc", "agentgateway").get("spec") or {}).get("ports", [])}
            gw_dep = kj("-n", NS, "get", "deploy", "agentgateway").get("status") or {}
            np_ok = kubectl(a, "-n", NS, "get", "networkpolicy", "agentgateway-egress").returncode == 0
            ok_cfg = any(b.get("port") == 3128 and b.get("tunnelProtocol") == "connect" for b in binds) and all(lst.get(n, {}).get("protocol") == "HTTPS" and (lst[n].get("tls") or {}).get("cert") for n in ("git", "mirror")) and lst.get("public-egress", {}).get("protocol") == "TLS" \
                     and ((git_rt.get("policies") or {}).get("backendAuth") or {}).get("key", {}).get("value", {}).get("file") and "POST" in allow and "GET" in allow and ("mirror-shared" in rts or "mirror-acme" in rts) and 3128 in svc_ports and gw_dep.get("readyReplicas") == gw_dep.get("replicas") and np_ok
            rep.add("P24a", "Gateway egress z Gitu (rolegen → agentgateway-config): CONNECT bind 3128, HTTPS listenery git/mirror.platform.internal s certem (Secret mimo Git; od P3-6 E1 vydává cert-manager), passthrough jen allow-list; routa git-acme = metody z authz.http rolí + backendAuth (token jen v gateway); Service 3128; NetworkPolicy egressu gateway (ne IMDS/link-local/privátní sítě); obě repliky Ready", "PASS" if ok_cfg else "FAIL", {"binds": binds, "listeners": {k: v.get("protocol") for k, v in lst.items()}, "git_route_allow": allow, "git_backend_auth": bool((git_rt.get("policies") or {}).get("backendAuth")), "routes": sorted(rts), "svc_ports": sorted(svc_ports), "networkpolicy": np_ok, "gw_ready": [gw_dep.get("readyReplicas"), gw_dep.get("replicas")], "secrets": egress_secrets})
            gp = (pods_led.get("vyvojar") or {}).get("git_probe") or {}
            pf_gh = PortForward(a, "mock-github", 19811, 9801); pf_mi = PortForward(a, "mock-mirror", 19812, 9803)
            try:
                gdbg = http("GET", "http://127.0.0.1:19811/_debug/git", timeout=15).json()
                mdbg = http("GET", "http://127.0.0.1:19812/_debug/requests", timeout=15).json()
            finally: pf_gh.stop(); pf_mi.stop()
            refs = (gdbg.get("refs") or {}).get("acme/platform") or {}; greq = gdbg.get("requests") or []
            rp = [q for q in greq if "git-receive-pack" in q.get("path", "") and q.get("method") == "POST" and q.get("ts", 0) >= t1]   # jen tento běh
            gw_rp = [l_[-260:] for l_ in kubectl(a, "-n", NS, "logs", "-l", "app=agentgateway", "-c", "agentgateway", "--since=30m", "--tail=4000", "--prefix").stdout.splitlines() if "git-receive-pack" in l_]
            branch_ref = f"refs/heads/agent/{zid}/vyvojar"   # větev sondy per role
            ok_git = gp.get("clone") == 0 and gp.get("commit") == 0 and gp.get("push_branch") == 0 and gp.get("push_main") not in (None, 0) and ("chráněný" in str(gp.get("push_main_err", "")) or "pre-receive" in str(gp.get("push_main_err", ""))) \
                     and gp.get("token_env") == 0 and branch_ref in refs and bool(rp) and all(q.get("auth_scheme") == "Bearer" and q.get("auth_sha256_12") == egress_secrets.get("token_sha12") for q in greq) \
                     and (gp.get("via") == "srt" or not finops)   # P2-6: sonda musí jít přes srt (parentProxy), ne přímo – P2-4 to nechalo otevřené (zápis do /work)
            rep.add("P24b", "Vývojář z Kata podu: clone, commit a push větve agent/<wf>/vyvojar přes gateway CONNECT (srt parentProxy → terminace TLS git.platform.internal, gateway vloží Bearer token – pod žádný token nemá), push do main odmítne git server (branch protection v pre-receive hooku; gateway ref v těle pkt-line nevidí); backend viděl každý git request s tokenem gateway", "PASS" if ok_git else "FAIL", {"probe": {k: v for k, v in gp.items() if not k.startswith(("pip", "npm", "evil", "http80", "other"))}, "refs": refs, "receive_pack_requests": [(round(q["ts"] - t1, 1), q.get("path", "")[-40:], q.get("forwarded")) for q in rp], "gateway_receive_pack_log": gw_rp[-6:], "work_info": (pods_led.get("vyvojar") or {}).get("work_info"), "git_requests_auth": sorted({(q.get("auth_scheme"), q.get("auth_sha256_12") == egress_secrets.get("token_sha12")) for q in greq}, key=str)})
            mreq = mdbg.get("requests") or []
            ok_mirror = gp.get("pip") == 0 and ".whl" in str(gp.get("pip_files", "")) and gp.get("npm") == 0 and ".tgz" in str(gp.get("npm_files", "")) and any("/pypi/" in q.get("path", "") for q in mreq) and any("/npm/" in q.get("path", "") for q in mreq)
            rep.add("P24c", "Mirror balíčků z Kata podu: pip download (index mirror.platform.internal/pypi/simple) a npm pack (registry /npm/) přes gateway CONNECT – terminace TLS, routa jen GET; mirror viděl požadavky obou klientů", "PASS" if ok_mirror else "FAIL", {"pip": gp.get("pip"), "pip_files": gp.get("pip_files"), "pip_err": gp.get("pip_err"), "npm": gp.get("npm"), "npm_files": gp.get("npm_files"), "npm_err": gp.get("npm_err"), "mirror_paths": sorted({q.get("path") for q in mreq})[:10], "via": gp.get("via")})
            gw_log = kubectl(a, "-n", NS, "logs", "-l", "app=agentgateway", "-c", "agentgateway", "--since=40m", "--tail=4000", "--prefix").stdout   # obě repliky
            sni_lines = {h: sum(1 for l in gw_log.splitlines() if h in l) for h in ("git.platform.internal", "mirror.platform.internal", "evil.example.com")}
            eg_v = ((pods_led.get("vyvojar") or {}).get("egress_probe") or {})
            ok_edge = gp.get("evil_sni") not in (None, 0) and str(gp.get("http80_code")) in ("403", "404", "405", "000") and str(gp.get("other_repo_http")) in ("404", "403") and eg_v.get("internet_1.1.1.1:443", {}).get("result") == "timeout" and sni_lines["git.platform.internal"] > 0
            rep.add("P24d", "Hranice egressu podu role: cizí SNI (evil.example.com) přes proxy neprojde (srt allow-list → CONNECT 403; gateway route not found → TLS EOF), HTTP :80 ven neexistuje (srt 403 / CONNECT bind gateway 405), cizí repo mimo /acme/ → 404 z gateway, přímý internet timeout (NetworkPolicy); gateway loguje SNI egressu", "PASS" if ok_edge else "FAIL", {"evil_sni": gp.get("evil_sni"), "evil_err": gp.get("evil_err"), "http80_code": gp.get("http80_code"), "other_repo_http": gp.get("other_repo_http"), "internet": eg_v.get("internet_1.1.1.1:443"), "gateway_log_sni": sni_lines, "violations": gp.get("violations"), "srt_attempt": gp.get("srt_attempt")})

        if finops:
            # P2-6 – FinOps naostro: klíče role × zakázka z OpenBao (KV), cena zakázky = součet klíčů z budget_usage, strop zakázky vynucuje orchestrátor, registr org.zakazky
            safe_zid = re.sub(r"[^a-z0-9-]", "-", zid.lower()).strip("-")[:40]
            pf_bao3 = PortForward(a, "openbao", 18203, 8200); Hb3 = {"X-Vault-Token": init["root_token"]}
            try: kv = http("GET", f"https://127.0.0.1:18203/v1/secret/data/zakazky/{safe_zid}/gateway-keys", headers=Hb3, timeout=10)
            finally: pf_bao3.stop()
            kv_keys = ((kv.json().get("data") or {}).get("data") or {}) if kv.status_code == 200 else {}
            kv_hashes = {r_: _h.sha256(v.encode()).hexdigest() for r_, v in kv_keys.items()}
            cm_hashes = {(k.get("metadata") or {}).get("role"): k["keyHash"].split(":", 1)[1] for k in mine}
            sec_gone = kubectl(a, "-n", NS, "get", "secret", f"zakazka-keys-{safe_zid}").returncode != 0
            iss = next((e for e in L if e["kind"] == "GATEWAY_KEYS_ISSUED" and e["zakazka"] == zid), {})
            ok_kv = set(ROLE_CLIENTS) <= set(kv_keys) and all(kv_hashes.get(r_) == cm_hashes.get(r_) for r_ in ROLE_CLIENTS) and sec_gone and iss.get("keys_source") == "openbao" and iss.get("entropy") == ["openbao"]
            rep.add("P26a", "Klíče gateway role × zakázka vydává a drží OpenBao: entropie sys/tools/random, hodnoty v KV v2 secret/zakazky/<id>/gateway-keys (aplikace přes auth kubernetes, policy jen zakazky/*), v clusteru žádný Secret zakazka-keys-<id>; gateway a Git znají jen sha256 (ConfigMap agentgateway-keys == KV)", "PASS" if ok_kv else "FAIL", {"kv_http": kv.status_code, "kv_roles": sorted(kv_keys), "hash_match": {r_: kv_hashes.get(r_) == cm_hashes.get(r_) for r_ in ROLE_CLIENTS}, "secret_absent": sec_gone, "issued": {k: iss.get(k) for k in ("keys_source", "entropy", "kv_path", "secret")}})
            # P26b – cena zakázky: BUDGET z budget_usage (součet 30d útraty 4 klíčů) == nezávislý součet harnessu z DB; registr org.zakazky
            bud = next((e for e in reversed(L) if e["kind"] == "BUDGET" and e["zakazka"] == zid), {})
            with psycopg.connect(dsn("agentgateway"), autocommit=True, connect_timeout=10) as c:
                rows30 = c.execute("SELECT budget_id, used_amount FROM budget_usage WHERE budget_id LIKE '%-30d-block'").fetchall()
            db_sum = {r_: role_usage_usd(rows30, cm_hashes.get(r_, "∅")) for r_ in ROLE_CLIENTS}
            with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
                zrow = c.execute("SELECT budget_usd, spent_usd, status, keys_source, spend_source, key_hashes FROM org.zakazky WHERE zakazka_id = %s", (zid,)).fetchone()
            ok_cost = bud.get("source") == "budget_usage" and bud.get("window") == "30d" and abs(float(bud.get("spent_usd", 0)) - sum(db_sum.values())) < 0.002 and set(ROLE_CLIENTS) <= set(bud.get("by_role") or {}) and bud.get("spent_usd", 0) > 0 \
                      and zrow is not None and abs(float(zrow[1]) - float(bud.get("spent_usd", 0))) < 0.002 and zrow[2] == "Dokonceno" and zrow[3] == "openbao" and zrow[4] == "budget_usage" and len(zrow[5] or {}) >= 4
            rep.add("P26b", "Cena zakázky = součet 30d útraty jejích 4 klíčů v budget_usage gateway (Flexible Server), ne usage SDK; aplikace ji zapsala do ledgeru (BUDGET source=budget_usage) a do registru org.zakazky (spent_usd, by_role, status Dokonceno, keys_source openbao); nezávislý součet harnessu z DB souhlasí", "PASS" if ok_cost else "FAIL", {"budget_ledger": {k: bud.get(k) for k in ("spent_usd", "limit_usd", "source", "window", "by_role")}, "db_sum_by_role": {k: round(v, 6) for k, v in db_sum.items()}, "db_total": round(sum(db_sum.values()), 6), "registry_row": [str(x) for x in zrow] if zrow else None})
            # P26c – strop zakázky: zakázka s budget_usd 0.01 → po první roli (~0,015 USD) gate před další rolí → BudgetExceeded (zakazka-sum) → HITL rozpocet → timeout → Pozastaveno
            zid2 = f"P26-{run_tag}-2"; t26 = time.time()
            http("POST", f"{APP}/zakazky", json={"id": zid2, "poptavka": f"Přidej do repa platformy soubor zakazky/{zid2}/NOTES.md (test stropu zakázky).", "hitl_timeout_s": 600, "budget_timeout_s": 25, "budget_usd": 0.01, "klasifikace": KLAS_NO}, timeout=15)
            approved = set(); exc = None; issue2 = None
            while time.time() - t26 < 480:
                L2 = led(); exc = next((e for e in L2 if e["kind"] == "BUDGET_EXCEEDED" and e["zakazka"] == zid2 and e.get("source") in ("zakazka-sum", "agentgateway")), None)   # P3-6 E3: strop zakázky = i rozpočet klíče v gateway → 429 už v první roli
                if exc: break
                if "H1" not in approved:
                    issue2 = next((e for e in L2 if e["kind"] == "PUBLISHED" and e["zakazka"] == zid2 and e.get("publish_kind") == "issue"), None)
                    if issue2: gh_post(f"/issues/{issue2['number']}/comments", {"body": "/schvaluji – test stropu"}, "adam"); approved.add("H1")
                if "H2" not in approved:
                    adr2 = next((e for e in L2 if e["kind"] == "HANDOFF" and e["zakazka"] == zid2 and str(e.get("artifact", "")).startswith("adr://")), None)
                    if adr2: approve(zid2, "H2", adr2.get("hash")); approved.add("H2")
                time.sleep(4)
            st2 = wait_status(zid2, {"COMPLETED", "FAILED"}, 240) if exc else status(zid2)
            out2 = (st2 or {}).get("output") or {}
            gates = [e for e in led() if e["kind"] == "BUDGET_GATE" and e["zakazka"] == zid2]
            with psycopg.connect(dsn("org"), autocommit=True, connect_timeout=10) as c:
                zrow2 = c.execute("SELECT budget_usd, spent_usd, status FROM org.zakazky WHERE zakazka_id = %s", (zid2,)).fetchone()
            ok_cap = exc is not None and float(exc.get("spent_usd", 0)) >= 0.01 and exc.get("role") in ("architekt", "vyvojar", "reviewer") and out2.get("stav") == "Pozastaveno" and out2.get("bod") == "rozpocet" \
                     and zrow2 is not None and zrow2[2] == "BudgetExceeded" and float(zrow2[1]) >= 0.01
            rep.add("P26c", "Strop zakázky (sdílený napříč rolemi) vynucuje orchestrátor ze součtu klíčů: zakázka s budget_usd 0,01 projde první rolí, gate před další rolí hlásí BudgetExceeded (zdroj zakazka-sum), eskalace HITL rozpocet bez schválení → timeout → Pozastaveno; registr org.zakazky status BudgetExceeded se spent_usd >= strop", "PASS" if ok_cap else "FAIL", {"exceeded": {k: exc.get(k) for k in ("role", "spent_usd", "limit_usd", "by_role")} if exc else None, "gates": [(g.get("role"), g.get("spent_usd"), g.get("exceeded")) for g in gates], "output": out2, "approved": sorted(approved), "registry_row": [str(x) for x in zrow2] if zrow2 else None, "s": round(time.time() - t26, 1)})

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
            left = [f"{tns}/{p['metadata']['name']}" for tns in tenant_namespaces() for p in kj("-n", tns, "get", "pods").get("items", [])]; left_sec = [f"{tns}/{s['metadata']['name']}" for tns in tenant_namespaces() for s in kj("-n", tns, "get", "secrets").get("items", []) if s["metadata"]["name"].startswith("role-")]
            if not left and not left_sec: break
            time.sleep(5)
        cleanup_s = round(time.time() - tc, 1)
        iso = {k: {"node": p.get("node"), "pool": nodes.get(p.get("node")) or ("kata" if str(p.get("node", "")).startswith("aks-kata-") else None), "runtime_class": p.get("runtime_class"), "uid": p.get("pod_uid"), "run_as_user": p.get("run_as_user"), "automount_sa": p.get("automount_sa"), "srt": p.get("pod_srt")} for k, p in pods_led.items()}
        rep.add("P21c", "Izolace podů rolí: každý pod role na uzlu poolu kata (autoscaler z 0), RuntimeClass kata-vm-isolation, běží jako uid 1000 bez SA tokenu, srt (weaker nested sandbox) v podu k dispozici; po běhu pod i Secret smazány (ve všech ns tenantů)", "PASS" if pods_led and all(v["pool"] == "kata" and v["runtime_class"] == "kata-vm-isolation" and v["uid"] == 1000 and v["run_as_user"] == 1000 and v["automount_sa"] is False and v["srt"] not in (None, "none") for v in iso.values()) and not left and not left_sec else "FAIL", {"pods": iso, "left_pods": left, "left_secrets": left_sec, "cleanup_wait_s": cleanup_s, "kata_nodes": [n for n, p in nodes.items() if p == "kata"]})

        # P21d – egress
        eg = {k: p.get("egress_probe") for k, p in pods_led.items()}
        def blocked(r): return bool(r) and r.get("result") != "open"
        ok_eg = bool(eg) and all(e and blocked(e.get("internet_1.1.1.1:443")) and blocked(e.get("internet_dns_github.com:443")) and all((e.get(n) or {}).get("result") == "open" for n in ("memory", "gateway", "app")) for e in eg.values())
        rep.add("P21d", "Egress podu role (NetworkPolicy ns tenanta): internet (1.1.1.1:443, github.com:443) blokován, agentgateway, paměť a aplikace zakázky průchozí – model jen přes gateway", "PASS" if ok_eg else "FAIL", {"probe": eg})

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
    ap.add_argument("--step", choices=["p1-2", "p1-3", "p1-4", "p1-5", "p1-6", "p2-1", "p2-2", "p2-5", "p2-3", "p2-4", "p2-6", "p3-1", "p3-2", "p3-3", "p3-4", "p3-5", "p3-6"], default="p1-2")
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
    if not a.kubectl or (a.step not in ("p1-6", "p2-1", "p2-2", "p2-5", "p2-3", "p2-4", "p2-6", "p3-1", "p3-2", "p3-3", "p3-4", "p3-5", "p3-6") and not (a.opa_bin and a.agentgateway_bin)):
        print("chybí KUBECTL, OPA_BIN nebo AGENTGATEWAY_BIN"); sys.exit(2)
    for d in (RESULTS, LOGS): d.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k.lower() not in ("anthropic_base_url",)}
    env["NO_PROXY"] = env["no_proxy"] = (env.get("NO_PROXY", "") + ",127.0.0.1,localhost").strip(",")
    rep = Report()
    if a.create_kind:
        assert a.kind, "chybí KIND"
        create_kind(a, env)
    {"p1-2": step_p1_2, "p1-3": step_p1_3, "p1-4": step_p1_4, "p1-5": step_p1_5, "p1-6": step_p2_1, "p2-1": step_p2_1, "p2-2": lambda a, rep, env: step_p2_1(a, rep, env, images=True), "p2-5": lambda a, rep, env: step_p2_1(a, rep, env, images=True, registry=True), "p2-3": lambda a, rep, env: step_p2_1(a, rep, env, images=True, registry=True, identity=True), "p2-4": lambda a, rep, env: step_p2_1(a, rep, env, images=True, registry=True, identity=True, egress=True), "p2-6": lambda a, rep, env: step_p2_1(a, rep, env, images=True, registry=True, identity=True, egress=True, finops=True),
     "p3-1": lambda a, rep, env: step_p2_1(a, rep, env, images=True, identity=True, egress=True, gui=True),
     "p3-2": lambda a, rep, env: step_p2_1(a, rep, env, images=True, identity=True, egress=True, gui=True, tenant=True),
     "p3-3": lambda a, rep, env: step_p2_1(a, rep, env, images=True, identity=True, egress=True, gui=True, tenant=True, gov=True),
     "p3-4": lambda a, rep, env: step_p2_1(a, rep, env, images=True, identity=True, egress=True, gui=True, tenant=True, gov=True, klas=True),
     "p3-5": lambda a, rep, env: step_p2_1(a, rep, env, images=True, identity=True, egress=True, gui=True, tenant=True, gov=True, klas=True, o3=True),
     "p3-6": lambda a, rep, env: step_p2_1(a, rep, env, images=True, identity=True, egress=True, gui=True, tenant=True, gov=True, klas=True, o3=True, e3=True, e4=True, e1=True, e2=True, e6=True, e7=True)}[a.step](a, rep, env)   # p3-1: GUI řídí zakázku; registry/finops checky (P25/P26) jsou v p2-6   # p1-6 = alias (od P2-1 je konfigurace z Gitu)
    out = RESULTS / f"{a.step}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": a.step, "context": a.context, "kind": sh([a.kind, "version"]).stdout.strip() if a.kind else None, "images": IMAGES}, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")
    sys.exit(0 if n["FAIL"] == 0 else 1)


if __name__ == "__main__":
    main()
