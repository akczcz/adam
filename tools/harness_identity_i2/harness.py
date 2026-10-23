"""
Harness I2 – propagace identity uživatele agent → gateway → MCP server.

Falsifikuje tvrzení z knowledge/identity/standardy.md a overview.md:
  I2a  MCP server odmítne původní uživatelský token (RFC 8707 audience) – passthrough nesmí fungovat
  I2b  Po token exchange (RFC 8693) dorazí k MCP token s aud = MCP server, sub = uživatel, azp = gateway
  I2c  Keycloak V2 exchange bez enforceru umí UPSCOPE (scope, který uživatel neměl) – past
  I2d  S `downscope-assertion-grant-enforcer` je upscope odmítnut (invalid_scope)
  I2e  `act` claim nese identitu agenta (RFC 8693 delegace) – měří se, zda Keycloak 26.8 vydá
  I2f  Autorizace per nástroj na gateway: `delete_ticket` zamítnut před MCP, `lookup_ticket` projde
  I2g  Audit: gateway log nese sub + rozhodnutí; MCP vidí původ requestu
  I2h  Latence exchange (první vs. cache)

Režimy:
  --path direct        harness dělá exchange sám proti Keycloaku (referenční cesta, musí projít)
  --path agentgateway  exchange a autorizaci dělá agentgateway (configs/agentgateway.yaml)
  --authz cel|opa      jen pro agentgateway: CEL pravidla v gateway, nebo extAuthz → OPA

Komponenty spouští harness sám: Keycloak 26.8.1 (start-dev, --import-realm), mock_mcp.py,
agentgateway (AGENTGATEWAY_BIN), OPA (OPA_BIN, jen --authz opa).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
RESULTS, LOGS, CFG = HERE / "results", HERE / "logs", HERE / "logs" / "cfg"
KC_PORT, MCP_PORT, GW_PORT, OPA_PORT = 8080, 9800, 4300, 9191
KC = f"http://127.0.0.1:{KC_PORT}"
ISSUER = f"{KC}/realms/platform"
TOKEN_URL = f"{ISSUER}/protocol/openid-connect/token"
MCP = f"http://127.0.0.1:{MCP_PORT}"
GW = f"http://127.0.0.1:{GW_PORT}"
TE = "urn:ietf:params:oauth:grant-type:token-exchange"
AT_TYPE = "urn:ietf:params:oauth:token-type:access_token"


# ---------- procesy ----------

def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url: str, timeout: float, ok=(200,)) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if httpx.get(url, timeout=2).status_code in ok:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


class Proc:
    def __init__(self, name: str, cmd: list[str], env: dict, log: Path, cwd: str | None = None):
        self.name, self.log = name, open(log, "wb")
        self.p = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)

    def stop(self):
        try:
            os.killpg(self.p.pid, signal.SIGTERM)
            self.p.wait(timeout=25)
        except Exception:
            try:
                os.killpg(self.p.pid, signal.SIGKILL)
            except Exception:
                pass
        self.log.close()


def base_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("JAVA_TOOL_OPTIONS", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ANTHROPIC_BASE_URL")}
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
    return env


def start_keycloak(kc_home: str, features: str, env: dict) -> Proc:
    assert port_free(KC_PORT), f"port {KC_PORT} obsazen"
    imp = Path(kc_home) / "data" / "import"
    imp.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "configs" / "realm-platform.json", imp / "realm-platform.json")
    shutil.rmtree(Path(kc_home) / "data" / "h2", ignore_errors=True)  # čistý stav při každém běhu
    kenv = env | {"KC_BOOTSTRAP_ADMIN_USERNAME": "admin", "KC_BOOTSTRAP_ADMIN_PASSWORD": "admin"}
    cmd = [f"{kc_home}/bin/kc.sh", "start-dev", "--http-port", str(KC_PORT), "--hostname-strict=false", "--import-realm"] + ([f"--features={features}"] if features else [])
    p = Proc("keycloak", cmd, kenv, LOGS / "keycloak.log")
    assert wait_http(f"{ISSUER}/.well-known/openid-configuration", 180), "Keycloak nenaběhl (logs/keycloak.log)"
    return p


def start_mock(env: dict) -> Proc:
    assert port_free(MCP_PORT)
    p = Proc("mock_mcp", [sys.executable, str(HERE / "mock_mcp.py")], env | {"MCP_PORT": str(MCP_PORT), "MCP_ISSUER": ISSUER, "MCP_AUDIENCE": "mcp-tickets"}, LOGS / "mock_mcp.log")
    assert wait_http(f"{MCP}/health", 30), "mock MCP nenaběhl"
    return p


def render(src: Path, dst: Path, **kw) -> Path:
    txt = src.read_text()
    for k, v in kw.items():
        txt = txt.replace("{{" + k + "}}", str(v))
    dst.write_text(txt)
    return dst


def start_opa(opa_bin: str, env: dict) -> Proc:
    assert port_free(OPA_PORT)
    cmd = [opa_bin, "run", "--server", "--addr", "127.0.0.1:8181", "--set", f"plugins.envoy_ext_authz_grpc.addr=127.0.0.1:{OPA_PORT}", "--set", "plugins.envoy_ext_authz_grpc.path=envoy/authz/result", "--set", "decision_logs.console=true", "--skip-version-check", "--log-format", "json", str(HERE / "policies")]
    p = Proc("opa", cmd, env, LOGS / "opa.log")
    assert wait_http("http://127.0.0.1:8181/health", 30), "OPA nenaběhl (logs/opa.log)"
    return p


def start_gateway(agw_bin: str, authz: str, scope: str, env: dict) -> Proc:
    assert port_free(GW_PORT)
    CFG.mkdir(parents=True, exist_ok=True)
    src = HERE / "configs" / f"agentgateway-{authz}.yaml"
    cfg = render(src, CFG / "agentgateway.yaml", PORT=GW_PORT, ISSUER=ISSUER, TOKEN_URL=TOKEN_URL, MCP_PORT=MCP_PORT, OPA_PORT=OPA_PORT, SCOPE=scope)
    p = Proc("agentgateway", [agw_bin, "-f", str(cfg)], env, LOGS / "agentgateway.log")
    assert wait_http("http://127.0.0.1:19001/healthz/ready", 60), "agentgateway není ready (logs/agentgateway.log)"
    return p


# ---------- Keycloak helpers ----------

def claims(tok: str) -> dict:
    p = tok.split(".")[1]
    p += "=" * (-len(p) % 4)
    d = json.loads(base64.urlsafe_b64decode(p))
    return {k: d.get(k) for k in ("sub", "azp", "aud", "scope", "act", "may_act", "preferred_username") if k in d}


def user_token(scope: str = "openid") -> str:
    r = httpx.post(TOKEN_URL, data={"grant_type": "password", "client_id": "frontend", "username": "alice", "password": "alice", "scope": scope}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def exchange(subject: str, scope: str | None, audience: str | None = "mcp-tickets", actor: str | None = None) -> tuple[int, dict]:
    data = {"grant_type": TE, "subject_token": subject, "subject_token_type": AT_TYPE, "requested_token_type": AT_TYPE}
    if audience:
        data["audience"] = audience
    if scope is not None:
        data["scope"] = scope
    if actor:
        data["actor_token"] = actor
        data["actor_token_type"] = AT_TYPE
    r = httpx.post(TOKEN_URL, data=data, auth=("gateway", "gateway-secret"), timeout=10)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


def set_downscope_policy(enabled: bool):
    tok = httpx.post(f"{KC}/realms/master/protocol/openid-connect/token", data={"grant_type": "password", "client_id": "admin-cli", "username": "admin", "password": "admin"}, timeout=10).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pol = httpx.get(f"{KC}/admin/realms/platform/client-policies/policies", headers=h, timeout=10).json()
    for x in pol.get("policies", []):
        x["enabled"] = enabled
    r = httpx.put(f"{KC}/admin/realms/platform/client-policies/policies", headers=h, json=pol, timeout=10)
    assert r.status_code == 204, r.text


_HDRS: dict = {}


def mcp_call(base: str, token: str, tool: str, **hdrs) -> httpx.Response:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {"ticket_id": "T-1"}}}
    return httpx.post(f"{base}/mcp", json=body, headers={"Authorization": f"Bearer {token}", **_HDRS, **hdrs}, timeout=15)


def mcp_recorded() -> list[dict]:
    return httpx.get(f"{MCP}/_debug/requests", timeout=5).json()


def mcp_clear():
    httpx.delete(f"{MCP}/_debug/requests", timeout=5)


# ---------- report ----------

class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, name, status, detail):
        self.checks.append({"id": cid, "name": name, "status": status, "detail": detail})
        print(f"  {dict(PASS='✅', FAIL='❌', INFO='ℹ️', SKIP='⏭️')[status]} {cid} {name}: {json.dumps(detail, ensure_ascii=False)[:320]}")


# ---------- kontroly ----------

def run_direct(rep: Report):
    """Referenční cesta: harness = gateway. Měří chování Keycloaku a MCP mocku bez agentgateway."""
    at = user_token()
    uc = claims(at)
    rep.add("I0", "Subject token uživatele (frontend) nemá audience MCP serveru", "PASS" if "mcp-tickets" not in (uc["aud"] if isinstance(uc["aud"], list) else [uc["aud"]]) else "FAIL", uc)

    mcp_clear()
    r = mcp_call(MCP, at, "lookup_ticket")
    rec = mcp_recorded()[-1]
    rep.add("I2a", "Passthrough uživatelského tokenu MCP server odmítne (RFC 8707 aud)", "PASS" if r.status_code == 401 and str(rec["verdict"]).startswith("aud_mismatch") else "FAIL", {"status": r.status_code, "verdict": rec["verdict"], "www-authenticate": r.headers.get("www-authenticate", "")[:120]})

    set_downscope_policy(False)
    t0 = time.perf_counter()
    st, j = exchange(at, "tickets:read")
    dt1 = time.perf_counter() - t0
    ex = claims(j["access_token"]) if st == 200 else j
    mcp_clear()
    r = mcp_call(MCP, j.get("access_token", "x"), "lookup_ticket") if st == 200 else None
    rec = mcp_recorded()[-1] if r is not None else {}
    ok = st == 200 and ex.get("aud") == "mcp-tickets" and ex.get("sub") == uc.get("sub") and ex.get("azp") == "gateway" and r is not None and r.status_code == 200
    rep.add("I2b", "Exchange: aud=mcp-tickets, sub=uživatel, azp=gateway; MCP přijme", "PASS" if ok else "FAIL", {"exchange_status": st, "token": ex, "mcp_status": getattr(r, "status_code", None), "mcp_saw": rec.get("claims")})

    st, j = exchange(at, "tickets:write")
    rep.add("I2c", "Bez enforceru: exchange vydá scope, který uživatel neměl (UPSCOPE = past)", "INFO", {"status": st, "scope": claims(j["access_token"]).get("scope") if st == 200 else j, "upscoped": st == 200 and "tickets:write" in (claims(j["access_token"]).get("scope") or "")})

    a = httpx.post(TOKEN_URL, data={"grant_type": "client_credentials"}, auth=("agent", "agent-secret"), timeout=10).json().get("access_token")
    st, j = exchange(at, "tickets:read", actor=a)
    ex = claims(j["access_token"]) if st == 200 else j
    rep.add("I2e", "Delegace: `act` claim nese agenta (actor_token)", "PASS" if st == 200 and ex.get("act") else "FAIL", {"status": st, "act": ex.get("act") if isinstance(ex, dict) else None, "response": ex if st != 200 else "ok, ale bez act", "note": "Keycloak 26.8: delegace je preview feature (token-exchange-delegation) a vyžaduje souhlas uživatele v prohlížeči + FGAP V2 permission"})

    set_downscope_policy(True)
    st, j = exchange(at, "tickets:write")
    rep.add("I2d", "S downscope-assertion-grant-enforcer je upscope odmítnut", "PASS" if st == 400 and j.get("error") == "invalid_scope" else "FAIL", {"status": st, "body": j})
    st, j = exchange(at, "tickets:read")
    rep.add("I2d'", "S enforcerem: exchange na audience, kterou subject token nemá (mcp-tickets)", "INFO", {"status": st, "body": j if st != 200 else claims(j["access_token"]), "note": "enforcer kontroluje i audience → buď user token nese aud každého MCP serveru (koliduje s I2a), nebo enforcer vypnout a upscope hlídat jinde"})
    st, j = exchange(at, "tickets:read", audience=None)
    rep.add("I2d''", "S enforcerem: exchange bez audience parametru", "INFO", {"status": st, "token": claims(j["access_token"]) if st == 200 else j})
    set_downscope_policy(False)

    lat = []
    for _ in range(10):
        t = time.perf_counter()
        exchange(at, "tickets:read")
        lat.append((time.perf_counter() - t) * 1000)
    rep.add("I2h", "Latence exchange u Keycloaku (ms, bez cache)", "INFO", {"first_ms": round(dt1 * 1000, 1), "p50": round(statistics.median(lat), 1), "p95": round(sorted(lat)[8], 1)})


def run_gateway(rep: Report, authz: str, gw_log: Path, opa_log: Path | None):
    at = user_token()
    uc = claims(at)
    set_downscope_policy(False)  # enforcer vyžaduje audience v subject tokenu (viz direct I2d'); gateway žádá jen konfigurovaný scope
    agent_tok = httpx.post(TOKEN_URL, data={"grant_type": "client_credentials"}, auth=("agent", "agent-secret"), timeout=10).json().get("access_token", "")
    global _HDRS
    _HDRS = {"x-agent-token": agent_tok}

    mcp_clear()
    t0 = time.perf_counter()
    r = mcp_call(GW, at, "lookup_ticket")
    dt1 = time.perf_counter() - t0
    rec = mcp_recorded()
    saw = rec[-1] if rec else {}
    c = saw.get("claims") or {}
    ok = r.status_code == 200 and c.get("aud") == "mcp-tickets" and c.get("sub") == uc.get("sub") and c.get("azp") == "gateway" and str(saw.get("verdict", "")).startswith("ok:")
    rep.add("I2b", "Přes agentgateway: MCP dostal vyměněný token (aud=mcp-tickets, sub=uživatel, azp=gateway)", "PASS" if ok else "FAIL", {"status": r.status_code, "body": r.text[:160], "mcp_saw": c, "verdict": saw.get("verdict"), "upstream_requests": len(rec)})
    rep.add("I2b'", "Scope doručený MCP je podmnožinou scope uživatele", "PASS" if ok and set((c.get("scope") or "").split()) <= set((uc.get("scope") or "").split()) else ("FAIL" if ok else "SKIP"), {"user_scope": uc.get("scope"), "mcp_scope": c.get("scope")})
    rep.add("I2e", "Delegace: `act` claim u MCP", "PASS" if c.get("act") else "FAIL", {"act": c.get("act"), "note": "viz direct běh"})

    mcp_clear()
    r = mcp_call(GW, at, "delete_ticket")
    rec = mcp_recorded()
    rep.add("I2f", f"Autorizace ({authz}): delete_ticket zamítnut na gateway, MCP ho nevidí", "PASS" if r.status_code in (401, 403) and not rec else "FAIL", {"status": r.status_code, "body": r.text[:160], "reached_mcp": len(rec)})
    mcp_clear()
    r = mcp_call(GW, at, "lookup_ticket")
    rep.add("I2f'", f"Autorizace ({authz}): lookup_ticket projde", "PASS" if r.status_code == 200 else "FAIL", {"status": r.status_code})

    r = mcp_call(GW, "not-a-jwt", "lookup_ticket")
    rep.add("I2i", "Neplatný token gateway odmítne (401), nic nevymění", "PASS" if r.status_code == 401 else "FAIL", {"status": r.status_code})

    time.sleep(1)
    gl = gw_log.read_text(errors="replace")
    sub = uc.get("sub") or "?"
    rep.add("I2g", "Audit: gateway log obsahuje sub uživatele a rozhodnutí", "PASS" if sub in gl else "FAIL", {"sub_in_gateway_log": sub in gl, "lines_with_sub": sum(1 for l in gl.splitlines() if sub in l), "deny_logged": any(("403" in l or "denied" in l.lower()) for l in gl.splitlines())})
    if opa_log:
        ol = opa_log.read_text(errors="replace")
        rep.add("I2g'", "Audit: OPA decision log obsahuje rozhodnutí", "PASS" if "decision_id" in ol else "FAIL", {"decisions": ol.count("decision_id"), "sample": next((l[:300] for l in ol.splitlines() if "decision_id" in l and "delete_ticket" in l), None)})

    lat = []
    for _ in range(10):
        t = time.perf_counter()
        mcp_call(GW, at, "lookup_ticket")
        lat.append((time.perf_counter() - t) * 1000)
    rep.add("I2h", "Latence tools/call přes gateway vč. exchange (ms)", "INFO", {"first_ms": round(dt1 * 1000, 1), "p50": round(statistics.median(lat), 1), "p95": round(sorted(lat)[8], 1)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", choices=["direct", "agentgateway"], required=True)
    ap.add_argument("--authz", choices=["cel", "opa"], default="cel")
    ap.add_argument("--kc-home", default=os.getenv("KC_HOME", ""))
    ap.add_argument("--kc-features", default="", help="např. token-exchange-delegation,parameterized-scopes")
    ap.add_argument("--agentgateway-bin", default=os.getenv("AGENTGATEWAY_BIN", shutil.which("agentgateway") or ""))
    ap.add_argument("--opa-bin", default=os.getenv("OPA_BIN", shutil.which("opa") or ""))
    ap.add_argument("--exchange-scope", default="tickets:read", help="scope, který gateway žádá při exchange")
    a = ap.parse_args()
    if not a.kc_home:
        print("chybí --kc-home / KC_HOME (rozbalený keycloak-26.8.1)"); sys.exit(2)
    RESULTS.mkdir(exist_ok=True); LOGS.mkdir(exist_ok=True)
    env = base_env()
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = env["NO_PROXY"]
    rep, procs = Report(), []
    meta = {"path": a.path, "authz": a.authz if a.path == "agentgateway" else None, "kc_features": a.kc_features, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        procs.append(start_keycloak(a.kc_home, a.kc_features, env))
        procs.append(start_mock(env))
        print(f"== {a.path} / authz={a.authz} / kc_features={a.kc_features or '-'}")
        if a.path == "direct":
            run_direct(rep)
        else:
            if not a.agentgateway_bin:
                print("chybí AGENTGATEWAY_BIN"); sys.exit(2)
            opa_log = None
            if a.authz == "opa":
                if not a.opa_bin:
                    print("chybí OPA_BIN"); sys.exit(2)
                procs.append(start_opa(a.opa_bin, env)); opa_log = LOGS / "opa.log"
            procs.append(start_gateway(a.agentgateway_bin, a.authz, a.exchange_scope, env))
            meta["gateway_version"] = json.loads(subprocess.check_output([a.agentgateway_bin, "--version"], text=True)).get("version")
            run_gateway(rep, a.authz, LOGS / "agentgateway.log", opa_log)
            if a.authz == "opa":
                opa_proc = next(p for p in procs if p.name == "opa")
                opa_proc.stop(); procs.remove(opa_proc)
                time.sleep(1)
                r = mcp_call(GW, user_token(), "lookup_ticket")
                rep.add("I2j", "Výpadek PDP (OPA zastaven): gateway fail-closed s denyWithStatus 503", "PASS" if r.status_code == 503 else "FAIL", {"status": r.status_code, "body": r.text[:120]})
    finally:
        for p in reversed(procs):
            p.stop()
    meta["keycloak"] = "26.8.1"
    out = RESULTS / f"{a.path}{'-' + a.authz if a.path == 'agentgateway' else ''}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": meta, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
