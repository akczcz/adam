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
IMAGES = ["pgvector/pgvector:pg16", "clickhouse:26.8", "otel/opentelemetry-collector-contrib:0.163.2"]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["p1-2"], default="p1-2")
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
    step_p1_2(a, rep, env)
    out = RESULTS / f"{a.step}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": a.step, "context": a.context, "kind": sh([a.kind, "version"]).stdout.strip() if a.kind else None, "images": IMAGES}, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")
    sys.exit(0 if n["FAIL"] == 0 else 1)


if __name__ == "__main__":
    main()
