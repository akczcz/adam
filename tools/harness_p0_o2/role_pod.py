"""
role_pod.py – role zakázky jako Kubernetes Pod (P1-6). Aplikace (Dapr aktivita) založí v ns rolí Secret (token role pro paměť,
klíč gateway role × zakázka, token běhu) a Pod z obrazu platformy s `role_runner.py`: Kata RuntimeClass, uzel poolu `kata`,
non-root, bez SA tokenu, drop ALL, seccomp RuntimeDefault, egress jen podle NetworkPolicy ns (gateway, paměť, aplikace, DNS).
Artefakty zakázky si pod stáhne a vrátí přes HTTP API aplikace (/zakazky/{id}/files), výsledek pošle na /runs/{run_id}/result.
Aplikace čeká na fázi podu (Succeeded/Failed), zapíše ROLE_POD do ledgeru (uzel, runtime, časy, egress probe) a pod i Secret smaže.

SVID z SPIRE v podu role zatím není: Workload API je unix socket agenta přes hostPath, který do Kata VM nevede (P2: spiffe-csi/agent v VM).
Proměnné aplikace: P0_ROLE_RUNTIME=pod, P0_ROLE_IMAGE (bez šablony), P0_ROLE_IMAGE_REGISTRY (P2-2: registry.platform.internal → ACR v šabloně), P0_ROLE_NAMESPACE (platform-roles), P0_ARTIFACT_API (FQDN služby zakazka),
P0_ROLE_RUNTIME_CLASS (kata-vm-isolation; "none" = bez RuntimeClass, kind), P0_ROLE_NODE_SELECTOR (JSON), P0_ROLE_TIMEOUT_S, P0_ROLE_KEEP_PODS.
"""
from __future__ import annotations

import json
import os
import re
import secrets as _secrets
import time
from datetime import datetime, timezone

import httpx

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
RUNS: dict = {}   # run_id -> {"token", "result", "role", "zakazka"}


def _host():
    return f"https://{os.environ.get('KUBERNETES_SERVICE_HOST', 'kubernetes.default.svc')}:{os.environ.get('KUBERNETES_SERVICE_PORT', '443')}"


def k8s(method, path, body=None, raw=False, timeout=30):
    """Kubernetes API s tokenem ServiceAccountu aplikace (čte se při každém volání – bound token rotuje)."""
    tok = open(f"{SA_DIR}/token").read().strip()
    r = httpx.request(method, _host() + path, json=body, headers={"Authorization": f"Bearer {tok}"}, verify=f"{SA_DIR}/ca.crt", timeout=timeout)
    if r.status_code >= 300: raise RuntimeError(f"k8s {method} {path} → {r.status_code}: {r.text[:300]}")
    return r.text if raw else (r.json() if r.text else {})


def _ts(s):
    try: return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except Exception: return None


def new_run(role, zid):
    rid = re.sub(r"[^a-z0-9]", "", zid.lower())[-10:] + _secrets.token_hex(3)
    RUNS[rid] = {"token": _secrets.token_urlsafe(24), "result": None, "role": role, "zakazka": zid, "created": time.time()}
    return rid


def _template(role):
    """Šablona podu z rolegen (ConfigMap rolegen-build, pod-<role>.yaml = build/k8s/<role>-pod.yaml) – P2-2: pole z definice role, ne z env."""
    od = os.environ.get("P0_ROLE_OPTIONS_DIR"); p = f"{od}/pod-{role}.yaml" if od else None
    if p and os.path.exists(p):
        import yaml
        return yaml.safe_load(open(p).read())
    return None


def manifests(run_id, role, z, prompt, tool_names, *, token, key, role_opts_json, srt_json):
    """Secret + Pod běhu role. Vrací (ns, name, secret, pod, info); info = {template, overrides, image} pro ledger a check P22b."""
    ns = os.environ.get("P0_ROLE_NAMESPACE", "platform-roles"); name = f"role-{role}-{run_id}"; tenant = os.environ.get("P0_TENANT", "acme")
    rc = os.environ.get("P0_ROLE_RUNTIME_CLASS", "kata-vm-isolation")
    env = {k: os.environ[k] for k in ("P0_LLM_URL", "P0_MEMORY_URL", "P0_MODEL", "P0_MAX_TURNS", "P0_CLI_MAX_RETRIES", "P0_GITHUB_REPO",
                                      "ANTHROPIC_WORKSPACE_ID", "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST") if os.environ.get(k)}
    env |= {"P0_ROLE_RUNTIME": "local", "P0_ROLE": role, "P0_ZAKAZKA": json.dumps(z, ensure_ascii=False), "P0_PROMPT": prompt, "P0_TOOLS": ",".join(tool_names),
            "P0_RUN_ID": run_id, "P0_ARTIFACT_API": os.environ.get("P0_ARTIFACT_API", "http://zakazka:8010"),
            "P0_ROLE_OPTIONS_JSON": role_opts_json or "", "P0_SRT_SETTINGS_JSON": srt_json or "", "P0_SRT": os.environ.get("P0_ROLE_SRT", "/opt/node/bin/srt"),
            "HOME": "/tmp/home", "O1_LEDGER": "/tmp/role-ledger.jsonl", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    labels = {"app": "role", "platform.role": role, "role": role, "platform.zakazka": re.sub(r"[^A-Za-z0-9_.-]", "-", z["id"])[:63], "platform.run": run_id}
    secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": ns, "labels": labels}, "type": "Opaque",
              "stringData": {"P0_ROLE_TOKEN": token, "P0_ROLE_KEYS": json.dumps({"*": {role: key}}), "P0_RUN_TOKEN": RUNS[run_id]["token"]}}
    runtime_c = {"command": ["python", "/app/harness_p0_o2/role_runner.py"], "envFrom": [{"secretRef": {"name": name}}], "imagePullPolicy": os.environ.get("P0_ROLE_IMAGE_PULL", "Always"),
                 "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}
    runtime_spec = {"nodeSelector": json.loads(os.environ.get("P0_ROLE_NODE_SELECTOR", '{"pool": "kata"}')),
                    "tolerations": [{"key": "sandbox", "operator": "Equal", "value": "kata", "effect": "NoSchedule"}],
                    "restartPolicy": "Never", "activeDeadlineSeconds": int(os.environ.get("P0_ROLE_TIMEOUT_S", "900")), "volumes": [{"name": "tmp", "emptyDir": {}}]}
    if not runtime_spec["nodeSelector"]: runtime_spec.pop("nodeSelector"); runtime_spec.pop("tolerations")
    # P2-3: identita role = SVID ze SPIRE agenta jako sidecaru (Kata: hostPath socket DaemonSet agenta do VM nevede). Agent se atestuje
    # k8s_psat projektovaným tokenem SA `role` (jen v sidecaru; kontejner role token nemá), workload přes unix uid ve sdíleném PID ns.
    svid = os.environ.get("P0_ROLE_IDENTITY") == "svid"
    if svid:
        env |= {"P0_ROLE_IDENTITY": "svid", "SPIFFE_ENDPOINT_SOCKET": "unix:///run/spire/sockets/agent.sock", "P0_TENANT": tenant}
        runtime_c["volumeMounts"] = runtime_c["volumeMounts"] + [{"name": "spire-sockets", "mountPath": "/run/spire/sockets"}]
        runtime_spec |= {"serviceAccountName": os.environ.get("P0_ROLE_SA", "role"), "shareProcessNamespace": True,
                         "initContainers": [{"name": "spire-agent", "image": os.environ.get("P0_ROLE_SPIRE_AGENT_IMAGE", "ghcr.io/spiffe/spire-agent:1.14.2"), "restartPolicy": "Always",
                                             "args": ["-config", "/run/spire/config/agent.conf"],
                                             "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}, "runAsUser": 1000, "runAsGroup": 1000},
                                             "volumeMounts": [{"name": "spire-agent-config", "mountPath": "/run/spire/config", "readOnly": True}, {"name": "spire-sockets", "mountPath": "/run/spire/sockets"},
                                                              {"name": "spire-data", "mountPath": "/run/spire/data"}, {"name": "spire-token", "mountPath": "/var/run/secrets/tokens", "readOnly": True}],
                                             "resources": {"requests": {"cpu": "20m", "memory": "32Mi"}, "limits": {"memory": "128Mi"}}}]}
        # Kata: emptyDir bez media je adresář hostitele přes virtiofs – unix socket na něm nejde (agent se atestoval, workload „failed to connect“, P23c 2026-10-25);
        # medium Memory = tmpfs uvnitř guestu
        runtime_spec["volumes"] = runtime_spec["volumes"] + [{"name": "spire-sockets", "emptyDir": {"medium": "Memory", "sizeLimit": "4Mi"}}, {"name": "spire-data", "emptyDir": {"medium": "Memory", "sizeLimit": "16Mi"}},
                                                             {"name": "spire-agent-config", "configMap": {"name": os.environ.get("P0_ROLE_SPIRE_AGENT_CONFIG", "spire-agent-pod")}},
                                                             {"name": "spire-token", "projected": {"sources": [{"serviceAccountToken": {"path": "spire-agent", "expirationSeconds": 7200, "audience": "spire-server"}}]}}]
    # P2-4: egress přes gateway CONNECT – CA gateway z ConfigMapy (terminace git/mirror), cíle sondy role_runner; token git má jen gateway
    if os.environ.get("P0_ROLE_CA_CONFIGMAP"):
        env |= {"P0_CA": "/etc/platform/ca/ca.crt", "SSL_CERT_FILE": "/etc/platform/ca/ca.crt", "CURL_CA_BUNDLE": "/etc/platform/ca/ca.crt", "GIT_SSL_CAINFO": "/etc/platform/ca/ca.crt",
                "REQUESTS_CA_BUNDLE": "/etc/platform/ca/ca.crt", "PIP_CERT": "/etc/platform/ca/ca.crt", "NODE_EXTRA_CA_CERTS": "/etc/platform/ca/ca.crt", "npm_config_cafile": "/etc/platform/ca/ca.crt"}
        runtime_c["volumeMounts"] = runtime_c["volumeMounts"] + [{"name": "platform-ca", "mountPath": "/etc/platform/ca", "readOnly": True}]
        runtime_spec["volumes"] = runtime_spec["volumes"] + [{"name": "platform-ca", "configMap": {"name": os.environ["P0_ROLE_CA_CONFIGMAP"]}}]
    for k in ("P0_ROLE_GIT_URL", "P0_ROLE_MIRROR_URL", "P0_ROLE_EGRESS_PROXY"):
        if os.environ.get(k): env[k.replace("P0_ROLE_", "P0_")] = os.environ[k]
    tpl = _template(role); overrides = []
    if tpl:
        # P2-2: pole z definice role (RuntimeClass, non-root, SA token, drop ALL, resources, env, labels, image) jsou ze šablony; aplikace doplní jen běh
        spec = tpl["spec"]; c = spec["containers"][0]
        reg = os.environ.get("P0_ROLE_IMAGE_REGISTRY")
        if reg and c["image"].startswith("registry.platform.internal/"): c["image"] = reg.rstrip("/") + c["image"][len("registry.platform.internal"):]; overrides.append("image.registry")
        elif not reg and os.environ.get("P0_ROLE_IMAGE"): c["image"] = os.environ["P0_ROLE_IMAGE"]; overrides.append("image")   # kind bez registru rolí
        sc = spec.setdefault("securityContext", {})
        if (sc.get("seccompProfile") or {}).get("type") == "Localhost": sc["seccompProfile"] = {"type": "RuntimeDefault"}; overrides.append("securityContext.seccompProfile")   # profil na uzlu není; v Kata guestu se profil podu neaplikuje
        for k, v in (("runAsGroup", sc.get("runAsUser", 1000)), ("fsGroup", sc.get("runAsUser", 1000))):
            if k not in sc: sc[k] = v; overrides.append(f"securityContext.{k}")
        tl = {k: str(v).replace("{{wf}}", run_id).replace("{tenant}", tenant).replace("{workflow_instance}", run_id) for k, v in (tpl.get("metadata", {}).get("labels") or {}).items()}
        labels = tl | labels
        tenv = {e["name"]: e.get("value", "") for e in c.get("env", [])}
        c["env"] = [{"name": k, "value": v} for k, v in (tenv | env).items()]; overrides.append("env+")
        c.update(runtime_c); overrides += ["command", "envFrom", "imagePullPolicy", "volumeMounts"]
        if rc and rc != "none" and spec.get("runtimeClassName") != rc: spec["runtimeClassName"] = rc; overrides.append("runtimeClassName")
        if rc == "none": spec.pop("runtimeClassName", None); overrides.append("runtimeClassName-")
        spec.update(runtime_spec); overrides += [f"{k}" for k in runtime_spec]
        if svid: spec["securityContext"]["fsGroup"] = spec["securityContext"].get("runAsUser", 1000)   # socket agenta čitelný pro roli
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": labels, "annotations": {"platform.template": f"pod-{role}.yaml"}}, "spec": spec}
    else:
        spec = {"automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "runAsGroup": 1000, "fsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "role", "image": os.environ["P0_ROLE_IMAGE"], "env": [{"name": k, "value": v} for k, v in env.items()],
                                "resources": {"requests": {"cpu": "250m", "memory": "512Mi"}, "limits": {"cpu": "2", "memory": os.environ.get("P0_ROLE_MEMORY", "1536Mi")}},
                                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}} | runtime_c], **runtime_spec}
        if rc and rc != "none": spec["runtimeClassName"] = rc
        pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": labels}, "spec": spec}
    return ns, name, secret, pod, {"template": bool(tpl), "overrides": overrides, "image": pod["spec"]["containers"][0]["image"]}


def gc_orphans(ns, ledger):
    """Sirotci po pádu/restartu aplikace (pod aplikace zabit uprostřed běhu role → pod a Secret běhu nikdo nesmazal; AKS 2026-10-25):
    smazat pody rolí ve fázi Succeeded/Failed nebo starší než timeout + 10 min, a Secrety běhů bez živého podu. Aktivní běhy tohoto procesu se nechávají."""
    active = {f"role-{r['role']}-{rid}" for rid, r in RUNS.items()}
    try:
        pods = k8s("GET", f"/api/v1/namespaces/{ns}/pods?labelSelector=app%3Drole").get("items", [])
        alive = set()
        for p in pods:
            name = p["metadata"]["name"]; ph = p.get("status", {}).get("phase"); age = time.time() - (_ts(p["metadata"].get("creationTimestamp", "")) or time.time())
            if name in active: alive.add(name); continue
            if ph in ("Succeeded", "Failed") or age > int(os.environ.get("P0_ROLE_TIMEOUT_S", "900")) + 600:
                for kind in ("pods", "secrets"):
                    try: k8s("DELETE", f"/api/v1/namespaces/{ns}/{kind}/{name}")
                    except Exception: pass
                ledger("ROLE_POD_GC", pod=name, phase=ph, age_s=round(age), zakazka=p["metadata"].get("labels", {}).get("platform.zakazka"))
            else: alive.add(name)
        for sec in k8s("GET", f"/api/v1/namespaces/{ns}/secrets?labelSelector=app%3Drole").get("items", []):
            name = sec["metadata"]["name"]
            if name not in alive and name not in active:
                try: k8s("DELETE", f"/api/v1/namespaces/{ns}/secrets/{name}"); ledger("ROLE_POD_GC", secret=name)
                except Exception: pass
    except Exception as e:
        ledger("ROLE_POD_GC_ERROR", error=f"{type(e).__name__}: {str(e)[:200]}")


def pod_run(role, z, prompt, tool_names, *, token, key, ledger, root_dir):
    """Spustí roli jako pod a vrátí výsledek ve tvaru agent_run (text, cost, files, work, arts, error, budget_exceeded)."""
    gc_orphans(os.environ.get("P0_ROLE_NAMESPACE", "platform-roles"), ledger)
    rid = new_run(role, z["id"])
    od = os.environ.get("P0_ROLE_OPTIONS_DIR")
    ro = open(f"{od}/{role}.json").read() if od and os.path.exists(f"{od}/{role}.json") else ""
    srt = open(f"{od}/srt-{role}.json").read() if od and os.path.exists(f"{od}/srt-{role}.json") else ""
    ns, name, secret, pod, info = manifests(rid, role, z, prompt, tool_names, token=token, key=key, role_opts_json=ro, srt_json=srt)
    timeout = int(os.environ.get("P0_ROLE_TIMEOUT_S", "900")) + 300   # + čas na alokaci Kata uzlu autoscalerem z 0
    t0 = time.time(); p = {}; phase = "Pending"
    try:
        k8s("POST", f"/api/v1/namespaces/{ns}/secrets", secret)
        k8s("POST", f"/api/v1/namespaces/{ns}/pods", pod)
        ledger("ROLE_POD_CREATE", zakazka=z["id"], role=role, pod=name, namespace=ns, runtime_class=pod["spec"].get("runtimeClassName"), image=info["image"], srt=bool(srt), role_options=bool(ro), template=info["template"], overrides=info["overrides"])
        while time.time() - t0 < timeout:
            p = k8s("GET", f"/api/v1/namespaces/{ns}/pods/{name}")
            phase = p.get("status", {}).get("phase", "Pending")
            if phase in ("Succeeded", "Failed"): break
            time.sleep(3)
    except Exception as e:
        ledger("ROLE_POD_ERROR", zakazka=z["id"], role=role, pod=name, error=f"{type(e).__name__}: {str(e)[:300]}")
    logs = ""
    try: logs = k8s("GET", f"/api/v1/namespaces/{ns}/pods/{name}/log?tailLines=60", raw=True)
    except Exception as e: logs = f"(log nedostupný: {str(e)[:120]})"
    res = RUNS[rid]["result"]
    if res is None:
        for line in reversed(logs.splitlines()):
            if line.startswith("RESULT::"):
                try: res = json.loads(line[8:])
                except Exception: pass
                break
    sidecar = None
    if pod["spec"].get("initContainers"):   # P2-3: stav a log sidecaru spire-agent (důkaz atestace / příčina chybějícího SVID)
        try: sidecar = {"status": next((c.get("state") for c in (p.get("status", {}).get("initContainerStatuses") or []) if c.get("name") == "spire-agent"), None), "restarts": next((c.get("restartCount") for c in (p.get("status", {}).get("initContainerStatuses") or []) if c.get("name") == "spire-agent"), None),
                        "log": k8s("GET", f"/api/v1/namespaces/{ns}/pods/{name}/log?container=spire-agent&tailLines=25", raw=True)[-1500:]}
        except Exception as e: sidecar = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    st = p.get("status", {}); cs = (st.get("containerStatuses") or [{}])[0]; term = (cs.get("state") or {}).get("terminated") or {}
    created = _ts(p.get("metadata", {}).get("creationTimestamp", "")); sched = next((_ts(c.get("lastTransitionTime", "")) for c in st.get("conditions", []) if c.get("type") == "PodScheduled" and c.get("status") == "True"), None)
    started, finished = _ts(term.get("startedAt", "")), _ts(term.get("finishedAt", ""))
    ledger("ROLE_POD", zakazka=z["id"], role=role, pod=name, namespace=ns, phase=phase, node=p.get("spec", {}).get("nodeName"), runtime_class=p.get("spec", {}).get("runtimeClassName"),
           run_as_user=(p.get("spec", {}).get("securityContext") or {}).get("runAsUser"), automount_sa=p.get("spec", {}).get("automountServiceAccountToken"),
           exit_code=term.get("exitCode"), reason=term.get("reason"), result_received=res is not None,
           t_schedule_s=round(sched - created, 1) if sched and created else None, t_start_s=round(started - created, 1) if started and created else None,
           t_run_s=round(finished - started, 1) if finished and started else None, t_total_s=round(time.time() - t0, 1),
           egress_probe=(res or {}).get("egress_probe"), pod_uid=(res or {}).get("uid"), pod_srt=(res or {}).get("srt"), log_tail=None if res is not None else logs[-800:],
           image=info["image"], template=info["template"], overrides=info["overrides"], image_tools=(res or {}).get("image_tools"), image_role=(res or {}).get("image_role"),
           resources=pod["spec"]["containers"][0].get("resources"), identity=(res or {}).get("identity"), svid_sidecar=bool(pod["spec"].get("initContainers")), svid_sidecar_state=sidecar)
    if not os.environ.get("P0_ROLE_KEEP_PODS"):
        for kind in ("pods", "secrets"):
            try: k8s("DELETE", f"/api/v1/namespaces/{ns}/{kind}/{name}")
            except Exception: pass
    RUNS.pop(rid, None)
    work, arts = f"{root_dir}/work", f"{root_dir}/artifacts"
    if res is None:
        return {"text": f"AGENT_ERROR pod {phase}", "cost": None, "files": [], "work": work, "arts": arts,
                "error": f"PodFailed: phase={phase} exit={term.get('exitCode')} reason={term.get('reason')}", "budget_exceeded": False}
    return {"text": res.get("text", ""), "cost": res.get("cost"), "files": res.get("files") or [], "work": work, "arts": arts, "error": res.get("error"), "budget_exceeded": bool(res.get("budget_exceeded"))}
