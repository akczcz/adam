#!/usr/bin/env python3
"""
Sonda pro dvě OTEVŘENÉ otázky z knowledge/protocols/mcp.md:
  - Podporuje Microsoft Foundry Agent Service revizi 2026-07-28?
  - Podporuje Claude API MCP connector 2026-07-28?

Rešerší se uzavřít nedaly (chybí primární zdroj). Tohle je zavře empiricky:
pošle 2026-era request BEZ handshake a podívá se, co endpoint odpoví.

Spuštění:
    tools/.venv-smoke/bin/python tools/probe_remote_mcp.py <URL> [--token TOKEN]

Interpretace:
  HTTP 200 + result                     → endpoint 2026-07-28 umí
  -32022 UnsupportedProtocolVersion     → umí MCP, ale NE tuto revizi
  -32600 / "Missing session ID"         → legacy stateful (2025-era)
  401/403                               → špatný token, o revizi to nic neříká
"""

import argparse
import json
import sys

import httpx

MODERN = "2026-07-28"


def probe(url: str, token: str | None) -> int:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "server/discover",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN,
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {"name": "adam-probe", "version": "1.0"},
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MODERN,
        "Mcp-Method": "server/discover",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"POST {url}")
    print(f"  MCP-Protocol-Version: {MODERN}, bez initialize handshake\n")
    try:
        r = httpx.post(url, json=body, headers=headers, timeout=30)
    except Exception as e:
        print(f"❌ spojení selhalo: {e}")
        return 2

    print(f"HTTP {r.status_code}")
    text = r.text
    data = None
    if "data:" in text[:400]:
        for line in text.splitlines():
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                break
    else:
        try:
            data = r.json()
        except Exception:
            print(f"  tělo (neparsovatelné): {text[:300]}")
            return 2

    print(json.dumps(data, indent=2, ensure_ascii=False)[:800])
    print()

    if r.status_code in (401, 403):
        print("⚠️  NEJASNÉ – autorizace selhala, o podpoře revize to neříká nic.")
        return 2
    if data and "result" in data:
        print(f"✅ Endpoint ODPOVĚDĚL na 2026-07-28 bez handshake → revizi podporuje.")
        return 0
    code = (data or {}).get("error", {}).get("code")
    msg = (data or {}).get("error", {}).get("message", "")
    if code == -32022:
        print("❌ -32022 UnsupportedProtocolVersion → MCP umí, 2026-07-28 NE.")
    elif "session" in msg.lower():
        print("❌ Vyžaduje session → legacy stateful transport (2025-era).")
    else:
        print(f"⚠️  NEJASNÉ – kód {code}: {msg}")
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="MCP endpoint (Foundry / Claude connector / vlastní server)")
    ap.add_argument("--token", default=None, help="Bearer token")
    a = ap.parse_args()
    sys.exit(probe(a.url, a.token))
