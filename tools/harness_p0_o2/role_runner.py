"""
role_runner.py – entrypoint podu role (P1-6). Běží v Kata podu z obrazu platformy jako uid 1000, bez SA tokenu:
1. z env uloží výstupy rolegen (ClaudeAgentOptions role, srt settings) do souborů; srt (weaker nested sandbox – S1h-3c) jen když je binárka,
2. změří egress (TCP connect: internet má být blokován NetworkPolicy, paměť a aplikace průchozí),
3. stáhne artefakty zakázky z aplikace (/zakazky/{id}/files), spustí `agent_run_local` z app.py (stejný kód jako v procesu aplikace),
4. nahraje artifacts/ a work/ zpět, pošle výsledek a ledger běhu na /runs/{run_id}/result a vypíše RESULT::{json} (záloha z logu podu).
Autentizace k aplikaci: hlavičky X-Run-Id / X-Run-Token (token běhu ze Secretu podu, platí jen pro tento běh).
"""
from __future__ import annotations

import base64
import json
import os
import socket
import sys
import time
from urllib.parse import urlparse

import httpx


def tcp_probe(host, port, timeout=3.0):
    t = time.time()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout): return {"result": "open", "ms": int((time.time() - t) * 1000)}
    except socket.timeout: return {"result": "timeout", "ms": int((time.time() - t) * 1000)}
    except OSError as e: return {"result": f"error:{e.errno or type(e).__name__}", "ms": int((time.time() - t) * 1000)}


def _hp(url, default_port):
    u = urlparse(url); return u.hostname, u.port or default_port


def main():
    role = os.environ["P0_ROLE"]; z = json.loads(os.environ["P0_ZAKAZKA"]); prompt = os.environ["P0_PROMPT"]
    tools = [t for t in os.environ.get("P0_TOOLS", "").split(",") if t]
    api = os.environ["P0_ARTIFACT_API"].rstrip("/"); rid = os.environ["P0_RUN_ID"]
    H = {"X-Run-Id": rid, "X-Run-Token": os.environ.get("P0_RUN_TOKEN", "")}
    os.makedirs("/tmp/home", exist_ok=True)
    od = "/tmp/rolegen"; os.makedirs(od, exist_ok=True)
    if os.environ.get("P0_ROLE_OPTIONS_JSON"):
        open(f"{od}/{role}.json", "w").write(os.environ["P0_ROLE_OPTIONS_JSON"]); os.environ["P0_ROLE_OPTIONS_DIR"] = od
    srt_bin = os.environ.get("P0_SRT", "none")
    if os.environ.get("P0_SRT_SETTINGS_JSON") and srt_bin != "none" and os.path.exists(srt_bin):
        open("/tmp/srt-settings.json", "w").write(os.environ["P0_SRT_SETTINGS_JSON"]); os.environ["P0_SRT_SETTINGS"] = "/tmp/srt-settings.json"
    else:
        os.environ["P0_SRT"] = "none"
    os.environ.setdefault("O1_LEDGER", "/tmp/role-ledger.jsonl")
    for k in ("P0_ROLE_RUNTIME",): os.environ[k] = "local"

    identity = {"kind": "keycloak-token"}
    if os.environ.get("P0_ROLE_IDENTITY") == "svid":
        # P2-3: identita role = JWT-SVID (aud memory) z Workload API sidecaru spire-agent; Keycloak token ze Secretu zůstává záloha
        t_id = time.time(); err = None
        for _ in range(60):
            try:
                from spiffe import WorkloadApiClient
                with WorkloadApiClient() as c:
                    x = c.fetch_x509_svid(); j = c.fetch_jwt_svid(audience={os.environ.get("P0_SVID_AUDIENCE", "memory")})
                    pl = json.loads(base64.urlsafe_b64decode(j.token.split(".")[1] + "==").decode())
                    identity = {"kind": "svid", "spiffe_id": str(j.spiffe_id), "x509_spiffe_id": str(x.spiffe_id), "iss": pl.get("iss"), "aud": pl.get("aud"), "exp_in_s": int(pl.get("exp", 0) - time.time()), "wait_s": round(time.time() - t_id, 1)}
                    os.environ["P0_ROLE_TOKEN"] = j.token; err = None; break
            except Exception as e:
                err = f"{type(e).__name__}: {str(e)[:120]}"; time.sleep(2)
        if identity["kind"] != "svid": identity = {"kind": "keycloak-token", "svid_error": err, "wait_s": round(time.time() - t_id, 1)}
    print("identity=" + json.dumps(identity), flush=True)
    probe = {"internet_1.1.1.1:443": tcp_probe("1.1.1.1", 443), "internet_dns_github.com:443": None}
    try: probe["internet_dns_github.com:443"] = tcp_probe("github.com", 443)
    except Exception as e: probe["internet_dns_github.com:443"] = {"result": f"dns:{type(e).__name__}"}
    for name, url, dp in (("memory", os.environ.get("P0_MEMORY_URL", ""), 9900), ("gateway", os.environ.get("P0_LLM_URL", ""), 4100), ("app", api, 8010)):
        if url:
            h, p = _hp(url, dp)
            try: probe[name] = tcp_probe(h, p)
            except Exception as e: probe[name] = {"result": f"dns:{type(e).__name__}"}
    print("egress_probe=" + json.dumps(probe), flush=True)

    root = f"/tmp/p0-o2/{z['id']}"
    for d in ("work", "artifacts"): os.makedirs(f"{root}/{d}", exist_ok=True)
    try:
        r = httpx.get(f"{api}/zakazky/{z['id']}/files", headers=H, timeout=60)
        files = r.json().get("files", []) if r.status_code == 200 else []
    except Exception as e:
        files = []; print(f"sync-down error: {e}", flush=True)
    for f in files:
        p = os.path.normpath(os.path.join(root, f["root"], f["path"]))
        if not p.startswith(root + os.sep): continue
        os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(base64.b64decode(f["content_b64"]))
    print(f"sync-down files={len(files)}", flush=True)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import app as app_mod
    t0 = time.time()
    res = app_mod.agent_run_local(role, z, prompt, tools)
    agent_s = round(time.time() - t0, 1)

    up = []
    for rootname in ("artifacts", "work"):
        base = os.path.join(root, rootname)
        for d, dirs, names in os.walk(base):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for n in names:
                fp = os.path.join(d, n); rel = os.path.relpath(fp, base)
                if rel.startswith("."): continue
                try: data = open(fp, "rb").read()
                except Exception: continue
                if len(data) > 2_000_000: continue
                up.append({"root": rootname, "path": rel, "content_b64": base64.b64encode(data).decode()})
    try: httpx.post(f"{api}/zakazky/{z['id']}/files", json={"files": up}, headers=H, timeout=120)
    except Exception as e: print(f"sync-up error: {e}", flush=True)
    led = []
    if os.path.exists(os.environ["O1_LEDGER"]):
        for l in open(os.environ["O1_LEDGER"]).read().splitlines():
            try: led.append(json.loads(l))
            except Exception: pass
    out = {k: res.get(k) for k in ("text", "cost", "files", "error", "budget_exceeded")}
    import shutil
    tools_present = {b: bool(shutil.which(b)) for b in ("git", "node", "python3", "srt", "bwrap", "claude")}
    tools_absent = {b: shutil.which(b) is None for b in ("az", "gcloud", "aws", "kubectl", "docker", "helm", "terraform")}   # obraz role bez cloud CLI (role.md sandbox)
    try: image_role = json.loads(open("/etc/platform/role.json").read()); image_role = {"role": image_role.get("role"), "version": image_role.get("version"), "managed_settings": os.path.exists("/etc/claude/managed-settings.json")}
    except Exception: image_role = None
    out |= {"egress_probe": probe, "pod": os.environ.get("HOSTNAME"), "srt": os.environ.get("P0_SRT"), "uid": os.getuid(), "agent_s": agent_s, "uploaded": len(up), "kernel": os.uname().release,
            "image_tools": {"present": tools_present, "absent": tools_absent}, "image_role": image_role, "identity": identity}
    try: httpx.post(f"{api}/runs/{rid}/result", json={"result": out, "ledger": led}, headers=H, timeout=120)
    except Exception as e: print(f"result post error: {e}", flush=True)
    print("RESULT::" + json.dumps(out, ensure_ascii=False)[:30000], flush=True)


if __name__ == "__main__":
    main()
