"""
Harness R1 – rolegen: z roles/*.yaml vzniknou konfigurace všech vrstev a každou ověří nástroj té vrstvy.

  R1a  Generování je deterministické (dva běhy = stejné hashe) a pokrývá všechny role; registr rolí (T12) má sha zdroje
  R1b  OPA roles.rego + build/opa/data.json: rozhodnutí per role odpovídají autonomie.md (tabulka případů)
  R1c  srt 0.0.81 přijme vygenerované settings každé role (`srt -s build/srt/<role>.json -c true`)
  R1d  agentgateway 1.6.0 `--validate-only` přijme konfiguraci s vygenerovanými apiKey rozpočty a egress allow-listem
  R1e  Inspect AI načte vygenerovanou approval policy (approval_policies_from_config)
  R1f  Pod spec: non-root, SA token off, RuntimeClass, drop ALL, seccomp Localhost – pro všechny role se sandboxem
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ROLES = ROOT / "knowledge/organization/roles"
BUILD, RESULTS, LOGS = HERE / "build", HERE / "results", HERE / "logs"
SRT = ROOT / "tools/harness_sandbox_s1/node_modules/.bin/srt"


class Report:
    def __init__(self): self.checks = []
    def add(self, cid, name, status, detail):
        self.checks.append({"id": cid, "name": name, "status": status, "detail": detail})
        print(f"  {dict(PASS='✅', FAIL='❌', INFO='ℹ️', SKIP='⏭️')[status]} {cid} {name}: {json.dumps(detail, ensure_ascii=False)[:420]}")


def tree_hash(d: Path):
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file(): h.update(str(p.relative_to(d)).encode()); h.update(p.read_bytes())
    return h.hexdigest()[:16]


def gen():
    r = subprocess.run([sys.executable, str(HERE / "rolegen.py"), "--roles", str(ROLES), "--out", str(BUILD), "--tenant", "acme", "--zakazka", "Z1"], capture_output=True, text=True)
    if r.returncode: raise SystemExit(r.stderr)
    return json.loads(r.stdout)


CASES = [  # (popis, input, očekávané allow, očekávaný reason)
    ("vývojář čte soubor z repa", {"role": "vyvojar", "tool": {"server": "repo", "action": "read_file"}}, True, "tool_allowed"),
    ("vývojář zapisuje přímo do repa", {"role": "vyvojar", "tool": {"server": "repo", "action": "write_file"}}, False, "tool_denied"),
    ("vývojář merguje PR", {"role": "vyvojar", "tool": {"server": "pr", "action": "merge"}}, False, "tool_denied"),
    ("vývojář přiřazuje issue člověku (příloha III)", {"role": "vyvojar", "tool": {"server": "issues", "action": "assign"}}, False, "tool_denied"),
    ("vývojář push na větev zakázky", {"role": "vyvojar", "tenant": "acme", "http": {"service": "git", "path": "/acme/platform.git/git-receive-pack", "method": "POST", "branch": "zakazka/Z1/ukol-1"}}, True, "git_push_branch"),
    ("vývojář push do main", {"role": "vyvojar", "tenant": "acme", "http": {"service": "git", "path": "/acme/platform.git/git-receive-pack", "method": "POST", "branch": "main"}}, False, "receive_pack_protected_branch"),
    ("vývojář fetch cizího tenanta", {"role": "vyvojar", "tenant": "acme", "http": {"service": "git", "path": "/beta/x.git/info/refs", "method": "GET"}}, False, "no_rule"),
    ("vývojář schvaluje fakt v paměti", {"role": "vyvojar", "memory": {"op": "approve", "scope": "firma", "type": "fakt", "sensitivity": "internal"}}, False, "no_rule"),
    ("vývojář navrhuje poučení", {"role": "vyvojar", "memory": {"op": "write", "scope": "firma", "type": "pouceni"}}, True, "memory_propose"),
    ("vývojář čte personal data zákazníka", {"role": "vyvojar", "memory": {"op": "read", "scope": "zakaznik", "type": "fakt", "sensitivity": "personal"}}, False, "no_rule"),
    ("vývojář vypíná sandbox", {"role": "vyvojar", "tool": {"server": "repo", "action": "read_file"}, "input_flags": ["Bash.dangerouslyDisableSandbox"]}, False, "dangerous_tool_input"),
    ("reviewer schvaluje fakt firma/internal", {"role": "reviewer", "memory": {"op": "approve", "scope": "firma", "type": "fakt", "sensitivity": "internal"}}, True, "memory_approve"),
    ("reviewer schvaluje personal", {"role": "reviewer", "memory": {"op": "approve", "scope": "zakaznik", "type": "fakt", "sensitivity": "personal"}}, False, "no_rule"),
    ("reviewer push kamkoli", {"role": "reviewer", "tenant": "acme", "http": {"service": "git", "path": "/acme/platform.git/git-receive-pack", "method": "POST", "branch": "zakazka/Z1/x"}}, False, "receive_pack_forbidden"),
    ("reviewer merguje", {"role": "reviewer", "tool": {"server": "pr", "action": "merge"}}, False, "tool_denied"),
    ("reviewer zapomíná zdroj", {"role": "reviewer", "memory": {"op": "forget"}}, False, "memory_forget_human_only"),
    ("neznámá role", {"role": "hacker", "tool": {"server": "pr", "action": "merge"}}, False, "unknown_role"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opa-bin", default=os.getenv("OPA_BIN", shutil.which("opa") or ""))
    ap.add_argument("--agentgateway-bin", default=os.getenv("AGENTGATEWAY_BIN", shutil.which("agentgateway") or ""))
    a = ap.parse_args()
    for d in (RESULTS, LOGS): d.mkdir(exist_ok=True)
    rep = Report()
    shutil.rmtree(BUILD, ignore_errors=True); g1 = gen(); h1 = tree_hash(BUILD)
    shutil.rmtree(BUILD, ignore_errors=True); gen(); h2 = tree_hash(BUILD)
    reg = json.loads((BUILD / "registry/roles.json").read_text())
    rep.add("R1a", "Generování deterministické, pokrývá všechny role; registr rolí (T12) nese verzi, vlastníka, SPIFFE ID a sha zdroje", "PASS" if h1 == h2 and len(reg) == len(g1["roles"]) and all(r["source_sha256_16"] for r in reg) else "FAIL", {"roles": g1["roles"], "files": len(g1["files"]), "hash": h1, "registry": [(r["role"], r["version"], r["owner"]) for r in reg]})

    # R1b OPA
    procs = []
    try:
        opa = subprocess.Popen([a.opa_bin, "run", "--server", "--addr", "127.0.0.1:8182", str(HERE / "policies"), str(BUILD / "opa/data.json")], stdout=open(LOGS / "opa.log", "wb"), stderr=subprocess.STDOUT)
        procs.append(opa); time.sleep(1.5)
        results = []
        for desc, inp, want_allow, want_reason in CASES:
            d = httpx.post("http://127.0.0.1:8182/v1/data/authz/decision", json={"input": inp}, timeout=5).json().get("result") or {}
            results.append({"case": desc, "allow": d.get("allow"), "reason": d.get("reason"), "ok": d.get("allow") == want_allow and d.get("reason") == want_reason})
        bad = [r for r in results if not r["ok"]]
        rep.add("R1b", f"OPA roles.rego + vygenerovaná data: {len(CASES)} případů podle autonomie.md (merge/push main/assign/approve deny, branch push/propose allow)", "PASS" if not bad else "FAIL", {"failed": bad, "passed": len(results) - len(bad)})
    finally:
        for p in procs: p.terminate()

    # R1c srt
    srt_res = {}
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    for f in sorted((BUILD / "srt").glob("*.json")):
        cfg = json.loads(f.read_text()); cfg["filesystem"]["allowWrite"] = ["/tmp"]  # /work v kontejneru harnessu neexistuje
        tmp = LOGS / f.name; tmp.write_text(json.dumps(cfg))
        r = subprocess.run([str(SRT), "-s", str(tmp), "-c", "echo srt-ok"], capture_output=True, text=True, timeout=60, env=env)
        srt_res[f.stem] = {"exit": r.returncode, "ok": "srt-ok" in r.stdout, "err": r.stderr.strip()[-160:] if r.returncode else ""}
    rep.add("R1c", "srt 0.0.81 přijme vygenerované settings každé role (schéma: parentProxy objekt, deniedDomains povinné, mandatoryDenySearchDepth)", "PASS" if srt_res and all(v["ok"] for v in srt_res.values()) else "FAIL", srt_res)

    # R1d agentgateway --validate-only
    keys = yaml.safe_load((BUILD / "agentgateway" / "apikeys-acme-Z1.yaml").read_text())
    egress = yaml.safe_load((BUILD / "agentgateway/egress-allowlist.yaml").read_text())
    for k in keys["policies"]["apiKey"]["keys"]: k["keyHash"] = "sha256:" + hashlib.sha256(k["keyHash"].encode()).hexdigest()  # placeholder → platný formát
    cfg = {"config": {"enableIpv6": False, "database": {"url": str(LOGS / "agentgateway-budgets.db")}}, "binds": [{"port": 3128, "tunnelProtocol": "connect", "listeners": []}],
           "gateways": {"llm": {"port": 4100}, "secure": {"port": 443, "listeners": [{"name": "public-egress", "hostname": "*", "protocol": "TLS"}]}},
           "llm": {"gateways": "llm", "models": [{"name": "*", "provider": "anthropic", "params": {"apiKey": "sk-ant-placeholder"}}]},
           "routes": [{"name": "llm-keys", "gateways": "llm", "policies": keys["policies"], "backends": [{"host": "127.0.0.1:9"}]}],
           "tcpRoutes": egress["tcpRoutes"]}
    cfgp = LOGS / "agentgateway-validate.yaml"; cfgp.write_text(yaml.safe_dump(cfg, sort_keys=False))
    r = subprocess.run([a.agentgateway_bin, "-f", str(cfgp), "--validate-only"], capture_output=True, text=True, timeout=60, env=env | {"ANTHROPIC_API_KEY": "x"})
    rep.add("R1d", "agentgateway 1.6.0 --validate-only přijme apiKey.keys[] s budgets (USD/24h/30d, Audit|Block) a egress tcpRoute z rolí", "PASS" if r.returncode == 0 else "FAIL", {"exit": r.returncode, "note": "budgets vyžadují config.database (sqlite/postgres) a metadata.name na klíči", "budgets": [(k["metadata"]["role"], len(k["budgets"])) for k in keys["policies"]["apiKey"]["keys"]], "egress_hosts": egress["tcpRoutes"][0]["hostnames"], "stderr": (r.stdout + r.stderr).strip()[-300:] if r.returncode else ""})

    # R1e Inspect approval
    try:
        sys.path.insert(0, str(ROOT / "tools/harness_eval_o2"))
        from inspect_ai.approval._policy import approval_policies_from_config
        loaded = {f.stem: len(approval_policies_from_config(str(f))) for f in sorted((BUILD / "inspect").glob("*-approval.yaml"))}
        rep.add("R1e", "Inspect AI načte vygenerované approval policy (fnmatch nad `sandboxed_bash(cmd=*git-receive-pack*`)", "PASS" if loaded and all(v >= 1 for v in loaded.values()) else "FAIL", {"policies": loaded, "sample": yaml.safe_load((BUILD / "inspect/vyvojar-approval.yaml").read_text())})
    except Exception as e:
        rep.add("R1e", "Inspect AI načte vygenerované approval policy", "FAIL", {"error": repr(e)[:200]})

    # R1f pod spec
    pods = {}
    for f in sorted((BUILD / "k8s").glob("*-pod.yaml")):
        p = yaml.safe_load(f.read_text()); sc = p["spec"]["securityContext"]; c = p["spec"]["containers"][0]
        pods[f.stem] = {"runtimeClass": p["spec"].get("runtimeClassName"), "nonroot": sc.get("runAsNonRoot"), "sa_token": p["spec"]["automountServiceAccountToken"], "drop": c["securityContext"]["capabilities"]["drop"], "seccomp": sc["seccompProfile"]["type"],
                        "ok": bool(p["spec"].get("runtimeClassName")) and sc.get("runAsNonRoot") is True and p["spec"]["automountServiceAccountToken"] is False and c["securityContext"]["capabilities"]["drop"] == ["ALL"] and sc["seccompProfile"]["type"] == "Localhost"}
    rep.add("R1f", "Pod spec rolí: RuntimeClass (Kata), non-root, SA token off, capabilities drop ALL, seccomp Localhost", "PASS" if pods and all(v["ok"] for v in pods.values()) else "FAIL", pods)

    out = RESULTS / f"r1-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"meta": {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "roles": g1["roles"], "build_hash": h1}, "checks": rep.checks}, ensure_ascii=False, indent=1))
    n = {s: sum(1 for c in rep.checks if c["status"] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    print(f"== výsledek: {n} -> {out.relative_to(HERE)}")
    sys.exit(0 if n["FAIL"] == 0 else 1)


if __name__ == "__main__":
    main()
