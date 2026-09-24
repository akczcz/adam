#!/usr/bin/env python3
"""
Smoke test Workeru s Adamovou znalostní bází.

Ověřuje to, co slibujeme kolegům: autentizace drží, legacy éra (kterou používá
Claude connector) funguje, moderní 2026-07-28 taky, a oba nástroje vracejí
data ze znalostní báze.

Spuštění (proti lokálnímu wrangler dev):
    ../tools/.venv-smoke/bin/python scripts/smoke_worker.py http://127.0.0.1:8787 <TOKEN>

Proti nasazenému Workeru se jen vymění URL.
"""

import json
import sys

import httpx

LEGACY = "2025-11-25"
MODERN = "2026-07-28"

results: list[tuple[str, bool]] = []


def verdict(ok: bool, detail: str) -> None:
    print(f"  {'✅ OK    ' if ok else '❌ CHYBA '} {detail}")
    results.append((detail, ok))


def parse(r: httpx.Response):
    text = r.text
    if "data:" in text[:400]:
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
    try:
        return r.json()
    except Exception:
        return {"_raw": text[:300]}


def rpc(c, base, token, method, params=None, *, era=LEGACY, mid=1):
    """Pošle JSON-RPC request. era=LEGACY jede handshake cestou, era=MODERN envelope."""
    body = {"jsonrpc": "2.0", "id": mid, "method": method}
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"

    if era == MODERN:
        params = dict(params or {})
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": MODERN,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        headers["MCP-Protocol-Version"] = MODERN
        headers["Mcp-Method"] = method
        name_key = {"tools/call": "name", "resources/read": "uri"}.get(method)
        if name_key and params.get(name_key) is not None:
            headers["Mcp-Name"] = str(params[name_key])

    if params is not None:
        body["params"] = params
    r = c.post(f"{base}/mcp", json=body, headers=headers, timeout=30)
    return r, parse(r)


def legacy_init(c, base, token):
    return rpc(
        c, base, token, "initialize",
        {
            "protocolVersion": LEGACY,
            "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "1.0"},
        },
    )


def main(base: str, token: str) -> int:
    print("=" * 74)
    print(f"SMOKE TEST WORKERU – {base}")
    print("=" * 74)

    with httpx.Client() as c:
        print("\n[1] Health check je dostupný bez tokenu")
        r = c.get(f"{base}/health", timeout=15)
        d = r.json() if r.status_code == 200 else {}
        verdict(
            r.status_code == 200 and d.get("status") == "ok",
            f"GET /health → {r.status_code}, {d.get('documents')} dokumentů",
        )

        print("\n[2] Bez Authorization hlavičky → 401")
        r, _ = rpc(c, base, None, "tools/list")
        verdict(
            r.status_code == 401 and "bearer" in r.headers.get("www-authenticate", "").lower(),
            f"→ {r.status_code}, WWW-Authenticate: {r.headers.get('www-authenticate', '(chybí)')}",
        )

        print("\n[3] Špatný token → 401")
        r, _ = rpc(c, base, "spatny-token-xxxxx", "tools/list")
        verdict(r.status_code == 401, f"→ {r.status_code}")

        print("\n[4] Legacy initialize (cesta, kterou jede Claude connector)")
        r, d = legacy_init(c, base, token)
        pv = d.get("result", {}).get("protocolVersion")
        verdict("result" in d, f"→ {r.status_code}, protocolVersion={pv}")

        print("\n[5] tools/list vrací oba nástroje")
        r, d = rpc(c, base, token, "tools/list")
        names = sorted(t["name"] for t in d.get("result", {}).get("tools", []))
        verdict(
            names == ["protocol_status", "search_knowledge"],
            f"→ {names}",
        )

        print("\n[6] resources/list vrací dokumenty")
        r, d = rpc(c, base, token, "resources/list")
        res = d.get("result", {}).get("resources", [])
        verdict(len(res) >= 5, f"→ {len(res)} resources, např. {res[0]['uri'] if res else '—'}")

        print("\n[7] resources/read vrátí obsah mcp.md")
        r, d = rpc(c, base, token, "resources/read", {"uri": "knowledge://protocols/mcp"})
        contents = d.get("result", {}).get("contents", [])
        text = contents[0].get("text", "") if contents else ""
        verdict(
            "2026-07-28" in text and "Odstraněno vs. deprecated" in text,
            f"→ {len(text)} znaků, obsahuje sekci o deprecated: {'ano' if 'deprecated' in text else 'NE'}",
        )

        print("\n[8] search_knowledge najde relevantní pasáž")
        r, d = rpc(
            c, base, token, "tools/call",
            {"name": "search_knowledge", "arguments": {"query": "deprecated Roots Sampling", "limit": 3}},
        )
        out = d.get("result", {}).get("content", [{}])[0].get("text", "")
        verdict(
            "Roots" in out and "MCP" in out,
            f"→ {len(out)} znaků; první nadpis: {out.splitlines()[0][:70] if out else '—'}",
        )

        print("\n[9] search_knowledge na nesmysl vrátí srozumitelnou hlášku")
        r, d = rpc(
            c, base, token, "tools/call",
            {"name": "search_knowledge", "arguments": {"query": "zzzqqq neexistujici vyraz"}},
        )
        out = d.get("result", {}).get("content", [{}])[0].get("text", "")
        verdict("nic k" in out.lower() or "Dostupné dokumenty" in out, f"→ {out[:80]}")

        print("\n[10] protocol_status vrací strukturovaná data")
        r, d = rpc(
            c, base, token, "tools/call",
            {"name": "protocol_status", "arguments": {"protocol": "mcp"}},
        )
        sc = d.get("result", {}).get("structuredContent", {})
        verdict(
            sc.get("zralost") == "stable" and bool(sc.get("otevrene_otazky")),
            f"→ zralost={sc.get('zralost')}, ověřeno={sc.get('naposledy_overeno')}, "
            f"zdrojů={len(sc.get('primarni_zdroje', []))}",
        )

        print("\n[11] protocol_status na neznámý protokol → isError, ne pád")
        r, d = rpc(
            c, base, token, "tools/call",
            {"name": "protocol_status", "arguments": {"protocol": "neexistuje"}},
        )
        res = d.get("result", {})
        verdict(res.get("isError") is True, f"→ isError={res.get('isError')}")

        print("\n[12] Moderní 2026-07-28 éra funguje taky")
        r, d = rpc(c, base, token, "tools/list", era=MODERN)
        tools = d.get("result", {}).get("tools", [])
        verdict(len(tools) == 2, f"→ {r.status_code}, {len(tools)} nástrojů přes stateless envelope")

    print("\n" + "=" * 74)
    ok = sum(1 for _, v in results if v)
    print(f"SOUHRN: {ok}/{len(results)} prošlo")
    print("=" * 74)
    if ok != len(results):
        print("\nNEPROŠLO:")
        for detail, v in results:
            if not v:
                print(f"  - {detail}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1].rstrip("/"), sys.argv[2]))
