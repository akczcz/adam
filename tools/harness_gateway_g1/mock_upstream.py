"""
Mock Anthropic Messages API.

Není to emulace modelu – je to *záznamník*. Odpovídá pevně danými zprávami
a ukládá přesně to, co k němu gateway doručila (hlavičky i tělo), aby harness
mohl porovnat vstup klienta s tím, co dorazilo upstream.

Chování řízené názvem modelu:
  mock-error       -> 400 s tělem ve tvaru Anthropic error
  mock-overloaded  -> 529 overloaded_error
  cokoliv jiného   -> 200; pokud request má `tools` a poslední zpráva není
                      tool_result, odpoví tool_use; jinak textem.

Proměnné prostředí:
  MOCK_PORT          port (default 9777)
  MOCK_EVENT_DELAY   prodleva v sekundách mezi SSE eventy (default 0.25) –
                     slouží k detekci bufferování streamu v gateway
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
RECORDED: list[dict] = []
EVENT_DELAY = float(os.getenv("MOCK_EVENT_DELAY", "0.25"))

USAGE = {
    "input_tokens": 11,
    "cache_creation_input_tokens": 2048,
    "cache_read_input_tokens": 4096,
    "output_tokens": 7,
    "cache_creation": {"ephemeral_5m_input_tokens": 2048, "ephemeral_1h_input_tokens": 0},
    "service_tier": "standard",
}


def _record(request: Request, body: dict | None, raw: bytes, path: str) -> None:
    RECORDED.append(
        {
            "ts": time.time(),
            "path": path,
            "method": request.method,
            "headers": {k.lower(): v for k, v in request.headers.items()},
            "body": body,
            "raw_len": len(raw),
            "client": request.client.host if request.client else None,
        }
    )


def _needs_tool_call(body: dict) -> bool:
    if not body.get("tools"):
        return False
    # Nástroj volej, dokud v historii není skutečné volání nástroje (ToolSearch Claude Code nestačí).
    for m in body.get("messages") or []:
        if m.get("role") != "assistant":
            continue
        for b in m.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") != "ToolSearch":
                return False
    return True


def _last_user_text(body: dict) -> str:
    for m in reversed(body.get("messages") or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _memory_message(body: dict) -> dict | None:
    """Harness M1: „naivní“ model nad paměťovými nástroji (search_memory / read_document / create_memory).

    - prompt s „paměti“ → search_memory(query=<prompt>), pak konec
    - prompt s „Přečti dokument <ref>“ → read_document(ref); když výsledek obsahuje [INJECT], model injekci POSLECHNE
      a zavolá create_memory(requested_status="approved") s instruovaným obsahem – zastavit ho musí PEP, ne mock.
    """
    tools = body.get("tools") or []
    names = {str(t.get("name", "")) for t in tools}
    if not names & {"search_memory", "read_document", "create_memory"}:
        return None
    calls, last_tool_result = [], ""
    for m in body.get("messages") or []:
        for b in (m.get("content") or []) if isinstance(m.get("content"), list) else []:
            if b.get("type") == "tool_use":
                calls.append(b["name"])
            if b.get("type") == "tool_result":
                c = b.get("content")
                last_tool_result = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    prompt = _last_user_text(body)
    tu = None
    if not calls:
        if "Přečti dokument" in prompt and "read_document" in names:
            ref = next((w for w in prompt.split() if w.startswith("doc://")), "doc://unknown").rstrip(".,")
            tu = ("read_document", {"ref": ref})
        elif "search_memory" in names:
            tu = ("search_memory", {"query": prompt})
    elif calls == ["read_document"] and "[INJECT]" in last_tool_result and "create_memory" in names:
        inj = last_tool_result.split("[INJECT]", 1)[1].split("[/INJECT]", 1)[0]
        fact = inj.split("fakt:", 1)[1].strip().strip("'\"") if "fakt:" in inj else inj.strip()
        ref = next((w for w in prompt.split() if w.startswith("doc://")), "doc://unknown").rstrip(".,")
        tu = ("create_memory", {"content": fact, "requested_status": "approved", "sources": [{"ref": ref, "kind": "document"}], "confidence": 0.9})
    elif calls == ["read_document"] and "create_memory" in names:
        ref = next((w for w in prompt.split() if w.startswith("doc://")), "doc://unknown").rstrip(".,")
        tu = ("create_memory", {"content": last_tool_result[:120], "requested_status": "proposed", "sources": [{"ref": ref, "kind": "document"}], "confidence": 0.6})
    if tu:
        content = [{"type": "text", "text": "Zavolám nástroj."}, {"type": "tool_use", "id": f"toolu_mock_{uuid.uuid4().hex[:8]}", "name": tu[0], "input": tu[1]}]
        stop = "tool_use"
    else:
        content = [{"type": "text", "text": "MOCK_OK: " + (last_tool_result[:160] if last_tool_result else "")}]
        stop = "end_turn"
    return {"id": f"msg_mock_{uuid.uuid4().hex[:12]}", "type": "message", "role": "assistant", "model": body.get("model", "mock"), "content": content, "stop_reason": stop, "stop_sequence": None, "usage": dict(USAGE)}


def _message(body: dict) -> dict:
    mid = f"msg_mock_{uuid.uuid4().hex[:12]}"
    mm = _memory_message(body)
    if mm is not None:
        return mm
    if _needs_tool_call(body):
        tools = body["tools"]
        names = [str(t.get("name", "")) for t in tools]
        # Harness O2: prompt „Smaž…“ → model zkusí delete_ticket (má ho zastavit approval policy, ne mock)
        want = "delete_ticket" if "Smaž" in _last_user_text(body) else "lookup_ticket"
        tool = next((t for t in tools if want in str(t.get("name", ""))), None)
        if tool is None and want == "delete_ticket":
            tool = next((t for t in tools if "lookup_ticket" in str(t.get("name", ""))), None)
        if tool is not None:
            name = tool["name"]
            args = {"ticket_id": "T-1"}
        elif "ToolSearch" in names:
            # Claude Code drží MCP nástroje jako deferred: model je musí nejdřív načíst přes ToolSearch.
            name = "ToolSearch"
            args = {"query": "select:mcp__harness__lookup_ticket", "max_results": 1}
        else:
            tool = tools[0]
            name = tool.get("name", "tool")
            props = (tool.get("input_schema") or {}).get("properties") or {}
            args = {k: "harness" for k in props}
        content = [
            {"type": "text", "text": "Zavolám nástroj."},
            {"type": "tool_use", "id": f"toolu_mock_{uuid.uuid4().hex[:8]}", "name": name, "input": args},
        ]
        stop = "tool_use"
    else:
        content = [{"type": "text", "text": "MOCK_OK"}]
        stop = "end_turn"
    return {
        "id": mid,
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "mock"),
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": dict(USAGE),
    }


async def _sse(body: dict):
    msg = _message(body)

    def ev(name: str, data: dict) -> bytes:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()

    start_usage = {k: v for k, v in USAGE.items() if k != "output_tokens"} | {"output_tokens": 1}
    yield ev("message_start", {"type": "message_start", "message": {**msg, "content": [], "stop_reason": None, "usage": start_usage}})
    await asyncio.sleep(EVENT_DELAY)
    yield ev("ping", {"type": "ping"})
    await asyncio.sleep(EVENT_DELAY)
    for i, block in enumerate(msg["content"]):
        if block["type"] == "text":
            yield ev("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            await asyncio.sleep(EVENT_DELAY)
            half = len(block["text"]) // 2
            for piece in (block["text"][:half], block["text"][half:]):
                yield ev("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": piece}})
                await asyncio.sleep(EVENT_DELAY)
        else:
            yield ev("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}})
            await asyncio.sleep(EVENT_DELAY)
            yield ev("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
            await asyncio.sleep(EVENT_DELAY)
        yield ev("content_block_stop", {"type": "content_block_stop", "index": i})
    yield ev("ping", {"type": "ping"})
    await asyncio.sleep(EVENT_DELAY)
    yield ev("message_delta", {"type": "message_delta", "delta": {"stop_reason": msg["stop_reason"], "stop_sequence": None}, "usage": dict(USAGE)})
    yield ev("message_stop", {"type": "message_stop"})


@app.post("/v1/messages")
async def messages(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw)
    except Exception:
        body = None
    _record(request, body, raw, "/v1/messages")
    rid = f"req_mock_{uuid.uuid4().hex[:10]}"
    headers = {"request-id": rid, "x-mock-upstream": "1"}
    if body is None:
        return JSONResponse({"type": "error", "error": {"type": "invalid_request_error", "message": "mock: body is not JSON"}}, status_code=400, headers=headers)
    model = body.get("model", "")
    if model == "mock-error":
        return JSONResponse({"type": "error", "error": {"type": "invalid_request_error", "message": "mock: deliberately invalid request"}, "request_id": rid}, status_code=400, headers=headers)
    if model == "mock-overloaded":
        return JSONResponse({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}, "request_id": rid}, status_code=529, headers=headers)
    if body.get("stream"):
        return StreamingResponse(_sse(body), media_type="text/event-stream", headers=headers | {"cache-control": "no-cache"})
    return JSONResponse(_message(body), headers=headers)


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    raw = await request.body()
    body = json.loads(raw) if raw else None
    _record(request, body, raw, "/v1/messages/count_tokens")
    return JSONResponse({"input_tokens": 4242}, headers={"x-mock-upstream": "1"})


@app.get("/v1/models")
async def models(request: Request):
    _record(request, None, b"", "/v1/models")
    return {"data": [{"id": "claude-haiku-4-5", "type": "model", "display_name": "mock"}], "has_more": False, "first_id": None, "last_id": None}


@app.get("/_debug/requests")
async def debug_requests():
    return RECORDED


@app.delete("/_debug/requests")
async def debug_clear():
    RECORDED.clear()
    return Response(status_code=204)


@app.get("/health")
async def health():
    return {"ok": True}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(path: str, request: Request):
    raw = await request.body()
    _record(request, None, raw, "/" + path + ("?" + str(request.query_params) if request.query_params else ""))
    return JSONResponse({"type": "error", "error": {"type": "not_found_error", "message": f"mock: unknown path /{path}"}}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("MOCK_PORT", "9777")), log_level="warning")
