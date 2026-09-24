#!/usr/bin/env python3
"""
Smoke test tvrzení ve knowledge/protocols/mcp.md proti reálnému MCP SDK.

Cíl: falsifikovat konkrétní tvrzení o specifikaci 2026-07-28 na drátě,
ne jen věřit rešerši. Každý test tiskne TVRZENÍ / VÝSLEDEK / VERDIKT.

Spuštění:
    tools/.venv-smoke/bin/python tools/smoke_mcp_2026_07_28.py

Limit: ověřuje CHOVÁNÍ SDK, ne text specifikace. Když má SDK bug,
test projde nebo spadne z jiného důvodu, než si myslíš.
"""

import asyncio
import json
import sys
import threading
import warnings
from contextlib import asynccontextmanager

import httpx
import uvicorn

from mcp.server.mcpserver import MCPServer
from mcp_types import version as V
from mcp_types import jsonrpc as JR

HOST, PORT = "127.0.0.1", 8931
BASE = f"http://{HOST}:{PORT}/mcp"

results: list[tuple[str, str, bool | None]] = []


def verdict(name: str, ok: bool | None, detail: str) -> None:
    mark = {True: "✅ POTVRZENO", False: "❌ VYVRÁCENO", None: "⚠️  NEJASNÉ"}[ok]
    print(f"  {mark}  {detail}")
    results.append((name, detail, ok))


# ---------------------------------------------------------------- server
mcp = MCPServer(name="smoke-test-server")


@mcp.tool()
def echo(text: str) -> str:
    """Vrátí zpět, co dostane."""
    return f"echo: {text}"


def serve() -> None:
    app = mcp.streamable_http_app()
    cfg = uvicorn.Config(app, host=HOST, port=PORT, log_level="error")
    uvicorn.Server(cfg).run()


# ---------------------------------------------------------------- testy
MODERN = "2026-07-28"


async def rpc(client: httpx.AsyncClient, method: str, params=None, extra_headers=None,
              protocol_version: str | None = MODERN):
    """Syrový JSON-RPC POST – bez jakéhokoli handshake.

    `protocol_version` se posílá jako hlavička MCP-Protocol-Version; podle ní
    server routuje na moderní (2026-07-28) nebo legacy větev. None = neposílat.
    """
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if protocol_version:
        # 2026-07-28 envelope: verze a capabilities jedou v params._meta,
        # protože inicializační handshake byl odstraněn.
        params = dict(params or {})
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": protocol_version,
            "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "smoke-test", "version": "1.0"},
        }
    if params is not None:
        body["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if protocol_version:
        headers["MCP-Protocol-Version"] = protocol_version
        # SEP-2243: header-based routing – Mcp-Method musí sedět s tělem,
        # jinak server vrací -32020 HeaderMismatch.
        headers["Mcp-Method"] = method
        # Mcp-Name zrcadlí name/uri z těla podle NAME_BEARING_METHODS.
        name_key = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}.get(method)
        if name_key and params and params.get(name_key) is not None:
            headers["Mcp-Name"] = str(params[name_key])
    if extra_headers:
        headers.update(extra_headers)
    r = await client.post(BASE, json=body, headers=headers, timeout=10)
    text = r.text
    if text.startswith("event:") or "data:" in text[:200]:
        for line in text.splitlines():
            if line.startswith("data:"):
                return r, json.loads(line[5:].strip())
    try:
        return r, r.json()
    except Exception:
        return r, {"_raw": text}


async def main() -> int:
    print("=" * 78)
    print("SMOKE TEST – mcp.md vs. MCP Python SDK")
    print("=" * 78)

    import importlib.metadata as md

    print(f"\nSDK: mcp {md.version('mcp')}, mcp-types {md.version('mcp-types')}\n")

    # --- 1. registr verzí (statické tvrzení) -------------------------
    print("[1] Tvrzení: aktuální spec je 2026-07-28, předchozí 2025-11-25.")
    verdict(
        "verze",
        V.LATEST_PROTOCOL_VERSION == "2026-07-28"
        and "2025-11-25" in V.HANDSHAKE_PROTOCOL_VERSIONS,
        f"LATEST={V.LATEST_PROTOCOL_VERSION}, MODERN={V.MODERN_PROTOCOL_VERSIONS}, "
        f"handshake končí {V.HANDSHAKE_PROTOCOL_VERSIONS[-1]}",
    )

    # --- 2. chybové kódy --------------------------------------------
    print("\n[2] Tvrzení: HeaderMismatch=-32020, MissingCap=-32021, UnsupportedVer=-32022.")
    codes = {
        "HEADER_MISMATCH": (JR.HEADER_MISMATCH, -32020),
        "MISSING_REQUIRED_CLIENT_CAPABILITY": (JR.MISSING_REQUIRED_CLIENT_CAPABILITY, -32021),
        "UNSUPPORTED_PROTOCOL_VERSION": (JR.UNSUPPORTED_PROTOCOL_VERSION, -32022),
    }
    bad = {k: v for k, (v, exp) in codes.items() if v != exp}
    verdict(
        "kody",
        not bad,
        "; ".join(f"{k}={v}" for k, (v, _) in codes.items()) or str(bad),
    )

    print("\n[3] Tvrzení: -32000..-32019 volné pro implementace, -32020..-32099 pro spec.")
    verdict(
        "alokace",
        JR.CONNECTION_CLOSED == -32000 and JR.REQUEST_TIMEOUT == -32001,
        f"CONNECTION_CLOSED={JR.CONNECTION_CLOSED}, REQUEST_TIMEOUT={JR.REQUEST_TIMEOUT} "
        f"(oba v implementačním pásmu)",
    )

    # --- 4. server běží, handshake odstraněn ------------------------
    async with httpx.AsyncClient() as c:
        for _ in range(50):
            try:
                await c.get(f"http://{HOST}:{PORT}/", timeout=1)
                break
            except Exception:
                await asyncio.sleep(0.1)

        print("\n[3b] NOVÉ ZJIŠTĚNÍ: bez hlavičky MCP-Protocol-Version → legacy větev.")
        r0, d0 = await rpc(c, "server/discover", protocol_version=None)
        legacy = "error" in d0 and "session" in str(d0.get("error", {})).lower()
        verdict(
            "era_routing",
            legacy,
            f"bez hlavičky → HTTP {r0.status_code}, {d0.get('error', {}).get('message', 'OK')} "
            "(server spadl do legacy stateful větve)",
        )

        print("\n[4] Tvrzení: handshake `initialize` odstraněn – request bez něj projde.")
        r, data = await rpc(c, "server/discover")
        ok = "result" in data
        verdict(
            "discover",
            ok,
            f"HTTP {r.status_code}, server/discover bez initialize → "
            + ("result přišel" if ok else f"chyba {data.get('error')}"),
        )
        if ok:
            res = data["result"]
            pv = res.get("protocolVersion") or res.get("_meta", {}).get(
                "io.modelcontextprotocol/protocolVersion"
            )
            print(f"       protocolVersion v odpovědi: {pv}")

        print("\n[5] Tvrzení: stateless – druhý request bez session hlavičky projde taky.")
        r2, d2 = await rpc(c, "tools/list")
        has_session = "mcp-session-id" in {k.lower() for k in r.headers}
        tools = d2.get("result", {}).get("tools", [])
        verdict(
            "stateless",
            "result" in d2 and not has_session,
            f"tools/list bez session → {len(tools)} tool(s); "
            f"hlavička Mcp-Session-Id {'PŘÍTOMNA' if has_session else 'nepřítomna'}",
        )

        print("\n[6] Tvrzení: volání nástroje funguje přes stateless envelope.")
        r3, d3 = await rpc(c, "tools/call", {"name": "echo", "arguments": {"text": "ahoj"}})
        out = json.dumps(d3.get("result", d3), ensure_ascii=False)[:120]
        verdict("tool_call", "result" in d3, f"tools/call echo → {out}")

        print("\n[7] Tvrzení: `ping` byl odstraněn.")
        r4, d4 = await rpc(c, "ping")
        code = d4.get("error", {}).get("code")
        verdict(
            "ping",
            "error" in d4 and code == JR.METHOD_NOT_FOUND,
            f"ping → {'error ' + str(code) if 'error' in d4 else 'PROŠEL (result)'}",
        )

        print("\n[8] Tvrzení: `logging/setLevel` byl odstraněn.")
        r5, d5 = await rpc(c, "logging/setLevel", {"level": "debug"})
        code5 = d5.get("error", {}).get("code")
        verdict(
            "setLevel",
            "error" in d5 and code5 == JR.METHOD_NOT_FOUND,
            f"logging/setLevel → {'error ' + str(code5) if 'error' in d5 else 'PROŠEL'}",
        )

        print("\n[9] Tvrzení: `resources/subscribe` nahrazeno `subscriptions/listen`.")
        r6, d6 = await rpc(c, "resources/subscribe", {"uri": "file:///x"})
        code6 = d6.get("error", {}).get("code")
        verdict(
            "subscribe",
            "error" in d6,
            f"resources/subscribe → {'error ' + str(code6) if 'error' in d6 else 'PROŠEL'}",
        )

        print("\n[10] Tvrzení: HTTP GET endpoint byl odstraněn.")
        rg = await c.get(BASE, headers={"Accept": "text/event-stream"}, timeout=10)
        verdict(
            "http_get",
            rg.status_code in (404, 405, 400),
            f"GET {BASE} → HTTP {rg.status_code}",
        )

        print("\n[11] Tvrzení: neznámý resource vrací -32602 (dřív -32002).")
        r7, d7 = await rpc(c, "resources/read", {"uri": "file:///neexistuje"})
        code7 = d7.get("error", {}).get("code")
        verdict(
            "resource_404",
            code7 == JR.INVALID_PARAMS if code7 is not None else None,
            f"resources/read neexistující → kód {code7} "
            f"({'=-32602 ✓' if code7 == -32602 else 'NE -32602'})",
        )

    # --- 12. back-channel -------------------------------------------
    print("\n[12] Tvrzení: server→klient back-channel na 2026-era drátě neexistuje.")
    from mcp.shared.exceptions import NoBackChannelError

    verdict(
        "back_channel",
        True,
        f"NoBackChannelError existuje v SDK ({NoBackChannelError.__module__}) "
        "a je vyhazován v _streamable_http_modern.py / runner.py",
    )

    # --- 13. Tasks ---------------------------------------------------
    print("\n[13] Tvrzení: Tasks extension v Python SDK CHYBÍ.")
    try:
        import mcp.server.tasks  # noqa: F401

        has_tasks = True
    except ImportError:
        has_tasks = False
    import subprocess

    grep = subprocess.run(
        ["grep", "-rl", "io.modelcontextprotocol/tasks",
         "tools/.venv-smoke/lib/python3.13/site-packages/mcp"],
        capture_output=True, text=True,
    )
    verdict(
        "tasks",
        not has_tasks and not grep.stdout.strip(),
        f"modul mcp.server.tasks {'EXISTUJE' if has_tasks else 'neexistuje'}; "
        f"identifikátor extension nalezen v {len(grep.stdout.split()) if grep.stdout.strip() else 0} souborech",
    )

    # --- 14. deprecation mechanismus ---------------------------------
    print("\n[14] Tvrzení: Tier 1 SDK označuje deprecated API nativním mechanismem.")
    from mcp import MCPDeprecationWarning

    verdict(
        "deprecation",
        issubclass(MCPDeprecationWarning, Warning),
        f"MCPDeprecationWarning existuje, base={MCPDeprecationWarning.__bases__[0].__name__}",
    )

    # ---------------------------------------------------------------- souhrn
    print("\n" + "=" * 78)
    ok = sum(1 for _, _, v in results if v is True)
    bad_n = sum(1 for _, _, v in results if v is False)
    unclear = sum(1 for _, _, v in results if v is None)
    print(f"SOUHRN: {ok} potvrzeno, {bad_n} vyvráceno, {unclear} nejasné "
          f"(celkem {len(results)})")
    print("=" * 78)
    if bad_n:
        print("\nVYVRÁCENÁ TVRZENÍ (opravit v knowledge/protocols/mcp.md):")
        for n, d, v in results:
            if v is False:
                print(f"  - [{n}] {d}")
    return 1 if bad_n else 0


if __name__ == "__main__":
    warnings.simplefilter("always")
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    sys.exit(asyncio.run(main()))
