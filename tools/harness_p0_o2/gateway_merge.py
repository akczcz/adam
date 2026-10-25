"""
gateway_merge.py – sidecar agentgateway (P2-1): slévá config z Gitu (ConfigMap agentgateway-config, vlastní Flux) a klíče role × zakázka
(ConfigMap agentgateway-keys, vlastní aplikace zakázky – gateway_keys.py) do jednoho souboru, který agentgateway hot-reloaduje.
Klíče v configu z Gitu (např. harness P1-4/P1-5 na kind) zůstávají; klíče z agentgateway-keys se přidávají (sjednocení podle keyHash).
Proč: Flux by každých 120 s vrátil klíče zapsané přímo do agentgateway-config; dvě ConfigMapy = dva vlastníci bez hádky.

Env: GW_CONFIG_SRC (/config-src/config.yaml), GW_KEYS_SRC (/keys-src/keys.yaml), GW_CONFIG_OUT (/etc/agentgateway/config.yaml), GW_MERGE_INTERVAL_S (2).
"""
from __future__ import annotations

import hashlib
import os
import sys
import time

import yaml

SRC = os.environ.get("GW_CONFIG_SRC", "/config-src/config.yaml")
KEYS = os.environ.get("GW_KEYS_SRC", "/keys-src/keys.yaml")
OUT = os.environ.get("GW_CONFIG_OUT", "/etc/agentgateway/config.yaml")
INTERVAL = float(os.environ.get("GW_MERGE_INTERVAL_S", "2"))


def merge(cfg_text: str, keys_text: str | None) -> str:
    cfg = yaml.safe_load(cfg_text) or {}
    extra = (yaml.safe_load(keys_text) if keys_text else None) or []
    if extra:
        llm = cfg.setdefault("llm", {}); pol = llm.setdefault("policies", {})
        ak = pol.setdefault("apiKey", {"mode": "optional", "location": {"header": {"name": "x-api-key"}}, "keys": []})
        keys = list(ak.get("keys") or []); seen = {k.get("keyHash") for k in keys}
        for k in extra:
            if k.get("keyHash") and k["keyHash"] not in seen: keys.append(k); seen.add(k["keyHash"])
        ak["keys"] = keys
    return yaml.safe_dump(cfg, sort_keys=False)


def read(p):
    try: return open(p).read()
    except FileNotFoundError: return None


def main():
    last = None
    while True:
        src = read(SRC)
        if src is None:
            print(f"gateway_merge: čekám na {SRC}", flush=True); time.sleep(INTERVAL); continue
        out = merge(src, read(KEYS))
        h = hashlib.sha256(out.encode()).hexdigest()
        if h != last:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            tmp = OUT + ".tmp"; open(tmp, "w").write(out); os.replace(tmp, OUT)
            n = len(((yaml.safe_load(out).get("llm") or {}).get("policies") or {}).get("apiKey", {}).get("keys") or [])
            print(f"gateway_merge: zapsán {OUT} sha256={h[:12]} keys={n}", flush=True); last = h
        if os.environ.get("GW_MERGE_ONCE"): return
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
