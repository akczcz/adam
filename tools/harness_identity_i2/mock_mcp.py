"""
Mock MCP resource server pro harness I2.

Není to MCP implementace – je to *resource server*, který dělá přesně to, co MCP spec
2026-07-28 ukládá: vyžaduje Bearer token, ověří podpis proti JWKS, ověří `iss` a `aud`
(RFC 8707 – audience musí být tento server), a zaznamená claimy, které dorazily.
Tím harness vidí, co gateway po token exchange skutečně doručila: `sub` (uživatel),
`act` (agent), `scope`, `aud`.

Endpointy:
  GET  /.well-known/oauth-protected-resource   RFC 9728 PRM
  POST /mcp                                    JSON-RPC: tools/call {name, arguments}
  GET  /_debug/requests, DELETE /_debug/requests

Prostředí:
  MCP_PORT (9800), MCP_ISSUER, MCP_JWKS_URL, MCP_AUDIENCE (mcp-tickets)
"""
from __future__ import annotations

import json
import os
import time

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from jwt import PyJWKClient

app = FastAPI()
PORT = int(os.getenv("MCP_PORT", "9800"))
ISSUER = os.getenv("MCP_ISSUER", "http://127.0.0.1:8080/realms/platform")
JWKS_URL = os.getenv("MCP_JWKS_URL", ISSUER + "/protocol/openid-connect/certs")
AUDIENCE = os.getenv("MCP_AUDIENCE", "mcp-tickets")
RECORDED: list[dict] = []
_jwks = PyJWKClient(JWKS_URL, cache_keys=True)

TOOLS = {
    "lookup_ticket": lambda a: {"ticket_id": a.get("ticket_id"), "status": "OPEN"},
    "delete_ticket": lambda a: {"ticket_id": a.get("ticket_id"), "deleted": True},
}
CLAIM_KEYS = ("iss", "sub", "aud", "azp", "scope", "act", "may_act", "preferred_username", "client_id", "typ", "exp")


def _unauthorized(msg: str, status: int = 401):
    hdr = f'Bearer resource_metadata="http://127.0.0.1:{PORT}/.well-known/oauth-protected-resource", error="invalid_token", error_description="{msg}"'
    return JSONResponse({"error": "invalid_token", "error_description": msg}, status_code=status, headers={"WWW-Authenticate": hdr})


@app.get("/.well-known/oauth-protected-resource")
async def prm():
    return {"resource": f"http://127.0.0.1:{PORT}", "authorization_servers": [ISSUER], "bearer_methods_supported": ["header"], "scopes_supported": ["tickets:read", "tickets:write"]}


@app.post("/mcp")
async def mcp(request: Request):
    raw = await request.body()
    auth = request.headers.get("authorization", "")
    rec = {"ts": time.time(), "headers": {k.lower(): v for k, v in request.headers.items() if k.lower() != "authorization"}, "auth_scheme": auth.split(" ", 1)[0] if auth else None, "claims": None, "verdict": None}
    RECORDED.append(rec)
    if not auth.lower().startswith("bearer "):
        rec["verdict"] = "no_token"
        return _unauthorized("missing bearer token")
    token = auth.split(" ", 1)[1].strip()
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256", "ES256", "PS256"], audience=AUDIENCE, issuer=ISSUER, options={"require": ["exp", "iss", "aud"]})
    except jwt.InvalidAudienceError as e:
        rec["claims"] = {k: v for k, v in jwt.decode(token, options={"verify_signature": False}).items() if k in CLAIM_KEYS}
        rec["verdict"] = f"aud_mismatch: {e}"
        return _unauthorized("audience mismatch (RFC 8707)")
    except Exception as e:
        rec["verdict"] = f"invalid: {type(e).__name__}: {e}"
        return _unauthorized(f"invalid token: {type(e).__name__}")
    rec["claims"] = {k: claims.get(k) for k in CLAIM_KEYS if k in claims}
    try:
        body = json.loads(raw)
    except Exception:
        rec["verdict"] = "bad_json"
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}}, status_code=400)
    if body.get("method") != "tools/call":
        rec["verdict"] = "unsupported_method"
        return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "only tools/call"}}
    name = (body.get("params") or {}).get("name")
    args = (body.get("params") or {}).get("arguments") or {}
    scopes = set((claims.get("scope") or "").split())
    need = "tickets:write" if name == "delete_ticket" else "tickets:read"
    if need not in scopes:
        rec["verdict"] = f"insufficient_scope: need {need}, have {sorted(scopes)}"
        return JSONResponse({"error": "insufficient_scope"}, status_code=403, headers={"WWW-Authenticate": f'Bearer error="insufficient_scope", scope="{need}"'})
    if name not in TOOLS:
        rec["verdict"] = "unknown_tool"
        return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32602, "message": f"unknown tool {name}"}}
    rec["verdict"] = f"ok:{name}"
    return {"jsonrpc": "2.0", "id": body.get("id"), "result": {"content": [{"type": "text", "text": json.dumps(TOOLS[name](args))}], "isError": False}}


@app.get("/_debug/requests")
async def debug():
    return RECORDED


@app.delete("/_debug/requests")
async def clear():
    RECORDED.clear()
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
