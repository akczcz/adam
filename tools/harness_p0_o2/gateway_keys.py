"""
gateway_keys.py – klíče agentgateway role × zakázka vydává aplikace při založení zakázky (P2-1), ne harness.

Šablona klíčů s rozpočty per role = rolegen (ConfigMap rolegen-build, soubor apikeys-template.yaml, placeholder {zakazka}).
Pro zakázku: hodnota klíče per role → sha256 do ConfigMapy `agentgateway-keys` (slévá ji sidecar gateway_merge.py do configu,
gateway hot-reloaduje); hodnoty vydává a drží OpenBao (P2-6: entropie `sys/tools/random`, KV v2 `secret/zakazky/<id>/gateway-keys`,
aplikace přes auth kubernetes – když je P0_BAO_KV), jinak Secret `zakazka-keys-<id>` (kind/P0). Gateway i Git znají jen hash.
Po zápisu se čeká, než gateway klíč přijme (ConfigMap volume se propaguje do ~60 s): sonda = minimální request s klíčem, 401 → ještě ne.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets as _secrets
import threading
import time

import httpx
import yaml

import role_pod

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
_CACHE: dict = {}
_LOCK = threading.Lock()


def _ns():
    try: return open(f"{SA_DIR}/namespace").read().strip()
    except FileNotFoundError: return os.environ.get("P0_NAMESPACE", "platform-data")


def _safe(zid): return re.sub(r"[^a-z0-9-]", "-", zid.lower()).strip("-")[:40]


def _template():
    p = os.path.join(os.environ.get("P0_ROLE_OPTIONS_DIR", "/rolegen"), "apikeys-template.yaml")
    return yaml.safe_load(open(p).read())["policies"]["apiKey"]


def _sub(v, zid, tenant=None):
    tenant = tenant or os.environ.get("P0_TENANT", "acme")   # P3-2: šablona z Gitu má placeholder {tenant} (render_k8s --tenant "{tenant}")
    if isinstance(v, str): return v.replace("{zakazka}", zid).replace("{tenant}", tenant)
    if isinstance(v, dict): return {k: _sub(x, zid, tenant) for k, x in v.items()}
    if isinstance(v, list): return [_sub(x, zid, tenant) for x in v]
    return v


def _probe_targets():
    """URL všech replik gateway (headless služba → A záznamy podů); když DNS nic nevrátí, aspoň ClusterIP URL."""
    import socket
    from urllib.parse import urlparse
    base = os.environ.get("P0_LLM_URL", "http://agentgateway:4100").rstrip("/"); u = urlparse(base)
    headless = os.environ.get("P0_GATEWAY_HEADLESS", "agentgateway-headless")
    if "." in (u.hostname or "") and not headless.count("."): headless = headless + "." + u.hostname.split(".", 1)[1]   # agentgateway.platform-data.svc → agentgateway-headless.platform-data.svc
    try: ips = sorted({ai[4][0] for ai in socket.getaddrinfo(headless, u.port or 4100, type=socket.SOCK_STREAM)})
    except OSError: ips = []
    return [f"http://{ip}:{u.port or 4100}" for ip in ips] or [base]


_HASHES: dict = {}; _SOURCE: dict = {}


def _bao_kv_path(zid): return f"{os.environ['P0_BAO_KV']}/data/zakazky/{_safe(zid)}/gateway-keys"


def _bao_headers():
    import app   # token aplikace (auth kubernetes, P2-3)
    return {"X-Vault-Token": app.bao_token()}


def _bao_random_hex(n=10):
    """Entropie klíče z OpenBao (sys/tools/random) – klíč 'vydává' OpenBao; při výpadku endpointu lokální secrets."""
    try:
        r = httpx.post(f"{os.environ['P0_BAO_ADDR']}/v1/sys/tools/random/{n}", json={"format": "hex"}, headers=_bao_headers(), timeout=5); r.raise_for_status()
        return r.json()["data"]["random_bytes"], "openbao"
    except Exception:
        return _secrets.token_hex(n), "local"


def key_hashes(zid):
    """{role: sha256 hex} klíčů zakázky – z cache, jinak z ConfigMapy agentgateway-keys (metadata.zakazka)."""
    if zid in _HASHES: return _HASHES[zid]
    cm = role_pod.k8s("GET", f"/api/v1/namespaces/{_ns()}/configmaps/agentgateway-keys")
    cur = yaml.safe_load((cm.get("data") or {}).get("keys.yaml") or "[]") or []
    _HASHES[zid] = {(c.get("metadata") or {}).get("role"): c["keyHash"].split(":", 1)[1] for c in cur if (c.get("metadata") or {}).get("zakazka") == zid}
    return _HASHES[zid]


def keys_source(zid): return _SOURCE.get(zid) or ("openbao" if os.environ.get("P0_BAO_KV") else "secret")


def block_tenant(tenant, ledger=None, block=True):
    """Stop tenanta (P3-3, autonomie.md T5): všem klíčům tenanta v ConfigMapě agentgateway-keys nastavit limit 0 (onBudgetExceeded Block → 429 na každý
    request; gateway klíč jinak neumí vypnout); resume = limity zpět ze šablony rolegen. Hodnoty klíčů v OpenBao se nemění (audit)."""
    ns = _ns(); tpl = {k["metadata"]["role"]: k for k in _template()["keys"]}; n = 0
    for attempt in range(6):
        cm = role_pod.k8s("GET", f"/api/v1/namespaces/{ns}/configmaps/agentgateway-keys")
        cur = yaml.safe_load((cm.get("data") or {}).get("keys.yaml") or "[]") or []; n = 0
        for k in cur:
            md = k.get("metadata") or {}
            if md.get("tenant") != tenant: continue
            if block:
                for b in k.get("budgets", []): b["limit"]["amount"] = 0
                md["blocked"] = "tenant-stop"
            else:
                k["budgets"] = [dict(b) for b in (tpl.get(md.get("role")) or {}).get("budgets", k.get("budgets", []))]; md.pop("blocked", None)
            n += 1
        cm["data"] = {"keys.yaml": yaml.safe_dump(cur, sort_keys=False, allow_unicode=True)}
        try: role_pod.k8s("PUT", f"/api/v1/namespaces/{ns}/configmaps/agentgateway-keys", cm); break
        except RuntimeError as e:
            if "409" not in str(e) or attempt == 5: raise
            time.sleep(0.5)
    # P3-5/P3-6 nález: ConfigMap se do replik gateway propaguje nezávisle (~40–70 s). Stop musí počkat, až blokace PLATÍ na všech replikách (429),
    # jinak replika načte blokovanou konfiguraci až po resume a role spuštěná po resume dostane 429; resume pak čeká na 200 na všech replikách.
    probe = next(((md["zakazka"], md["role"]) for k in cur for md in [k.get("metadata") or {}] if md.get("tenant") == tenant and md.get("zakazka") in _CACHE and md.get("role") in _CACHE[md["zakazka"]]), None)
    if probe:
        val = _CACHE[probe[0]][probe[1]]; t1 = time.time(); targets = _probe_targets(); status = {}; want = 429 if block else 200
        body = {"model": os.environ.get("P0_MODEL", "claude-haiku-4-5"), "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
        while time.time() - t1 < float(os.environ.get("P0_GATEWAY_KEYS_WAIT_S", "240")):
            for t in targets:
                try: status[t] = httpx.post(f"{t}/v1/messages", json=body, headers={"x-api-key": val, "anthropic-version": "2023-06-01"}, timeout=20).status_code
                except Exception as e: status[t] = type(e).__name__
            if targets and all(v == want for v in status.values()): break
            time.sleep(3)
        prop = {"s": round(time.time() - t1, 1), "status": status, "want": want, "key": f"{probe[0]}/{probe[1]}", "replicas": len(targets)}
    else: prop = {"skipped": "žádný klíč tenanta v cache procesu"}
    if ledger: ledger("GATEWAY_KEYS_BLOCK" if block else "GATEWAY_KEYS_UNBLOCK", tenant=tenant, keys=n, propagation=prop)
    return n


CAP_BUDGET = "zakazka-30d-block"   # P3-6 (E3): strop zakázky i v gateway – rozpočet per klíč = strop zakázky (agentgateway 1.6 rozpočty jen per klíč; součet napříč rolemi hlídá orchestrátor budget_gate)


def cap_budget(cap_usd):
    return {"name": CAP_BUDGET, "limit": {"unit": "USD", "amount": float(cap_usd)}, "window": {"rolling": "30d"}, "onBudgetExceeded": "Block"}


def set_cap(zid, cap_usd, ledger=None, probe_key=None):
    """P3-6 (E3): navýšení stropu zakázky z HITL `rozpocet` – rozpočet `zakazka-30d-block` všech klíčů zakázky v ConfigMapě = nový strop; pak sonda,
    až gateway (všechny repliky) klíč zase pustí (propagace ConfigMapy ~40–70 s per replika). Vrací {keys, propagation}."""
    ns = _ns(); n = 0
    for attempt in range(6):
        cm = role_pod.k8s("GET", f"/api/v1/namespaces/{ns}/configmaps/agentgateway-keys")
        cur = yaml.safe_load((cm.get("data") or {}).get("keys.yaml") or "[]") or []; n = 0
        for k in cur:
            if (k.get("metadata") or {}).get("zakazka") != zid: continue
            k["budgets"] = [b for b in k.get("budgets", []) if b.get("name") != CAP_BUDGET] + [cap_budget(cap_usd)]; n += 1
        cm["data"] = {"keys.yaml": yaml.safe_dump(cur, sort_keys=False, allow_unicode=True)}
        try: role_pod.k8s("PUT", f"/api/v1/namespaces/{ns}/configmaps/agentgateway-keys", cm); break
        except RuntimeError as e:
            if "409" not in str(e) or attempt == 5: raise
            time.sleep(0.5)
    prop = None
    val = probe_key or next(iter((_CACHE.get(zid) or {}).values()), None)
    if val:
        t1 = time.time(); targets = _probe_targets(); status = {}
        body = {"model": os.environ.get("P0_MODEL", "claude-haiku-4-5"), "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
        while time.time() - t1 < float(os.environ.get("P0_GATEWAY_KEYS_WAIT_S", "240")):
            for t in targets:
                try: status[t] = httpx.post(f"{t}/v1/messages", json=body, headers={"x-api-key": val, "anthropic-version": "2023-06-01"}, timeout=20).status_code
                except Exception as e: status[t] = type(e).__name__
            if targets and all(v == 200 for v in status.values()): break
            time.sleep(3)
        prop = {"s": round(time.time() - t1, 1), "status": status, "replicas": len(targets)}
    if ledger: ledger("GATEWAY_KEYS_CAP", zakazka=zid, cap_usd=float(cap_usd), keys=n, propagation=prop)
    return {"keys": n, "propagation": prop}


def issue(zid, ledger=None, tenant=None, cap_usd=None):
    """Vrátí {role: klíč} pro zakázku; vydá je, pokud ještě nejsou (idempotentní přes OpenBao KV, resp. Secret). cap_usd (P3-6 E3): strop zakázky
    jako rozpočet `zakazka-30d-block` každého klíče – gateway vrátí 429 i bez orchestrátoru."""
    with _LOCK:
        if zid in _CACHE: return _CACHE[zid]
        ns = _ns(); sname = f"zakazka-keys-{_safe(zid)}"; use_bao = bool(os.environ.get("P0_BAO_KV") and os.environ.get("P0_BAO_ADDR"))
        if use_bao:
            r = httpx.get(f"{os.environ['P0_BAO_ADDR']}/v1/{_bao_kv_path(zid)}", headers=_bao_headers(), timeout=5)
            if r.status_code == 200:
                keys = r.json()["data"]["data"]; _CACHE[zid] = keys; _SOURCE[zid] = "openbao"; return keys
            if r.status_code != 404: r.raise_for_status()
        else:
            try:
                sec = role_pod.k8s("GET", f"/api/v1/namespaces/{ns}/secrets/{sname}")
                import base64
                keys = json.loads(base64.b64decode(sec["data"]["keys.json"]).decode()); _CACHE[zid] = keys; _SOURCE[zid] = "secret"; return keys
            except RuntimeError as e:
                if "404" not in str(e): raise
        t0 = time.time(); tpl = _template(); keys, entries = {}, []; entropy = set()
        for k in tpl["keys"]:
            role = k["metadata"]["role"]; rnd, src = _bao_random_hex(10) if use_bao else (_secrets.token_hex(10), "local"); entropy.add(src)
            val = f"sk-gw-{_safe(zid)}-{role}-{rnd}"
            e = _sub({kk: v for kk, v in k.items() if kk != "keyHash"}, zid, tenant); e["keyHash"] = "sha256:" + hashlib.sha256(val.encode()).hexdigest()
            if cap_usd is not None: e["budgets"] = [b for b in e.get("budgets", []) if b.get("name") != CAP_BUDGET] + [cap_budget(cap_usd)]
            keys[role] = val; entries.append(e)
        # ConfigMap agentgateway-keys: get → union (bez starých klíčů této zakázky) → update s resourceVersion (409 → opakovat)
        for attempt in range(6):
            cm = role_pod.k8s("GET", f"/api/v1/namespaces/{ns}/configmaps/agentgateway-keys")
            cur = yaml.safe_load((cm.get("data") or {}).get("keys.yaml") or "[]") or []
            cur = [c for c in cur if (c.get("metadata") or {}).get("zakazka") != zid] + entries
            cm["data"] = {"keys.yaml": yaml.safe_dump(cur, sort_keys=False, allow_unicode=True)}
            try: cm = role_pod.k8s("PUT", f"/api/v1/namespaces/{ns}/configmaps/agentgateway-keys", cm); break
            except RuntimeError as e:
                if "409" not in str(e) or attempt == 5: raise
                time.sleep(0.5)
        if use_bao:   # hodnoty klíčů drží OpenBao (KV v2), ne Kubernetes Secret
            r = httpx.post(f"{os.environ['P0_BAO_ADDR']}/v1/{_bao_kv_path(zid)}", json={"data": keys, "options": {"cas": 0}}, headers=_bao_headers(), timeout=5); r.raise_for_status(); _SOURCE[zid] = "openbao"
        else:
            role_pod.k8s("POST", f"/api/v1/namespaces/{ns}/secrets", {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": sname, "labels": {"app": "zakazka-keys", "platform.zakazka": _safe(zid)}}, "type": "Opaque", "stringData": {"keys.json": json.dumps(keys)}}); _SOURCE[zid] = "secret"
        # propagace: ConfigMap volume (kubelet sync, per pod nezávisle) → sidecar merge → hot reload. Sonda s klíčem první role proti KAŽDÉ replice
        # (headless služba → IP podů); přes ClusterIP by sonda trefila jednu repliku a role pak dostala 401 z druhé (P21b 2026-10-25).
        probe_role = next(iter(keys)); t1 = time.time()
        targets = _probe_targets()
        body = {"model": os.environ.get("P0_MODEL", "claude-haiku-4-5"), "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
        status = {t: None for t in targets}; done = {}
        while time.time() - t1 < float(os.environ.get("P0_GATEWAY_KEYS_WAIT_S", "240")) and len(done) < len(targets):
            for t in targets:
                if t in done: continue
                try:
                    r = httpx.post(f"{t}/v1/messages", json=body, headers={"x-api-key": keys[probe_role], "anthropic-version": "2023-06-01", "x-zakazka": zid}, timeout=20); status[t] = r.status_code
                    if r.status_code != 401: done[t] = round(time.time() - t1, 1)
                except Exception: status[t] = "conn"
            if len(done) < len(targets): time.sleep(3)
        wait_s = max(done.values()) if len(done) == len(targets) else None
        _HASHES[zid] = {e["metadata"]["role"]: e["keyHash"].split(":", 1)[1] for e in entries}
        if ledger: ledger("GATEWAY_KEYS_ISSUED", zakazka=zid, roles=sorted(keys), hashes=[e["keyHash"][7:19] for e in entries], configmap_rv=cm.get("metadata", {}).get("resourceVersion"),
                          secret=None if use_bao else sname, keys_source=_SOURCE.get(zid), entropy=sorted(entropy), kv_path=_bao_kv_path(zid) if use_bao else None, propagation_s=wait_s, probe_status=200 if len(done) == len(targets) and all(v == 200 for v in status.values()) else status, replicas_probed=len(targets), propagation_by_replica=done,
                          total_s=round(time.time() - t0, 1), budgets_block_24h={e["metadata"]["role"]: next((b["limit"]["amount"] for b in e["budgets"] if b["name"].endswith("24h-block")), None) for e in entries})
        _CACHE[zid] = keys; return keys
