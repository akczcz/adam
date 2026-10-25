"""
gateway_keys.py – klíče agentgateway role × zakázka vydává aplikace při založení zakázky (P2-1), ne harness.

Šablona klíčů s rozpočty per role = rolegen (ConfigMap rolegen-build, soubor apikeys-template.yaml, placeholder {zakazka}).
Pro zakázku: náhodná hodnota klíče per role → sha256 do ConfigMapy `agentgateway-keys` (slévá ji sidecar gateway_merge.py do configu,
gateway hot-reloaduje), hodnoty do Secretu `zakazka-keys-<id>` (přežijí restart aplikace; v cíli je vydá OpenBao – P2-6).
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


def _sub(v, zid):
    if isinstance(v, str): return v.replace("{zakazka}", zid)
    if isinstance(v, dict): return {k: _sub(x, zid) for k, x in v.items()}
    if isinstance(v, list): return [_sub(x, zid) for x in v]
    return v


def issue(zid, ledger=None):
    """Vrátí {role: klíč} pro zakázku; vydá je, pokud ještě nejsou (idempotentní přes Secret)."""
    with _LOCK:
        if zid in _CACHE: return _CACHE[zid]
        ns = _ns(); sname = f"zakazka-keys-{_safe(zid)}"
        try:
            sec = role_pod.k8s("GET", f"/api/v1/namespaces/{ns}/secrets/{sname}")
            import base64
            keys = json.loads(base64.b64decode(sec["data"]["keys.json"]).decode()); _CACHE[zid] = keys; return keys
        except RuntimeError as e:
            if "404" not in str(e): raise
        t0 = time.time(); tpl = _template(); keys, entries = {}, []
        for k in tpl["keys"]:
            role = k["metadata"]["role"]; val = f"sk-gw-{_safe(zid)}-{role}-{_secrets.token_hex(10)}"
            e = _sub({kk: v for kk, v in k.items() if kk != "keyHash"}, zid); e["keyHash"] = "sha256:" + hashlib.sha256(val.encode()).hexdigest()
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
        role_pod.k8s("POST", f"/api/v1/namespaces/{ns}/secrets", {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": sname, "labels": {"app": "zakazka-keys", "platform.zakazka": _safe(zid)}}, "type": "Opaque", "stringData": {"keys.json": json.dumps(keys)}})
        # propagace: ConfigMap volume (kubelet sync) → sidecar merge → hot reload; sonda s klíčem první role
        probe_role = next(iter(keys)); wait_s = None; status = None
        url = os.environ.get("P0_LLM_URL", "http://agentgateway:4100").rstrip("/") + "/v1/messages"
        body = {"model": os.environ.get("P0_MODEL", "claude-haiku-4-5"), "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]}
        t1 = time.time()
        while time.time() - t1 < float(os.environ.get("P0_GATEWAY_KEYS_WAIT_S", "240")):
            try:
                r = httpx.post(url, json=body, headers={"x-api-key": keys[probe_role], "anthropic-version": "2023-06-01", "x-zakazka": zid}, timeout=20); status = r.status_code
                if status != 401: wait_s = round(time.time() - t1, 1); break
            except Exception: status = "conn"
            time.sleep(3)
        if ledger: ledger("GATEWAY_KEYS_ISSUED", zakazka=zid, roles=sorted(keys), hashes=[e["keyHash"][7:19] for e in entries], configmap_rv=cm.get("metadata", {}).get("resourceVersion"),
                          secret=sname, propagation_s=wait_s, probe_status=status, total_s=round(time.time() - t0, 1), budgets_block_24h={e["metadata"]["role"]: next((b["limit"]["amount"] for b in e["budgets"] if b["name"].endswith("24h-block")), None) for e in entries})
        _CACHE[zid] = keys; return keys
