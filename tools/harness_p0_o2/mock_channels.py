"""
mock_channels.py – mock reálných kanálů k lidem (P3-4, čl. 50(1) T7): e-mail zákazníkovi a komentář v ticketu zákazníka. Platforma do nich
píše přes adaptér (app.py notify_customer) s disclosure z definice role a značením generovaného obsahu (T8: generated_by). Mock jen ukládá
zprávy: POST /email, POST /tickets/{id}/comments, GET /_debug/messages (harness K1d/K1e). Ostrý provoz: SMTP relay / helpdesk API za gateway.
"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI, Request

app = FastAPI()
MSGS: list = []


@app.post("/email")
async def email(req: Request):
    b = await req.json()
    m = {"ts": time.time(), "channel": "email", "to": b.get("to"), "subject": b.get("subject"), "body": b.get("body", ""), "headers": b.get("headers") or {}, "generated_by": b.get("generated_by"), "zakazka": b.get("zakazka")}
    MSGS.append(m); del MSGS[:-200]
    return {"ok": True, "id": len(MSGS)}


@app.post("/tickets/{tid}/comments")
async def ticket_comment(tid: str, req: Request):
    b = await req.json()
    m = {"ts": time.time(), "channel": "ticket", "ticket": tid, "body": b.get("body", ""), "generated_by": b.get("generated_by"), "zakazka": b.get("zakazka")}
    MSGS.append(m); del MSGS[:-200]
    return {"ok": True, "id": len(MSGS)}


@app.get("/_debug/messages")
async def dbg(): return {"messages": MSGS[-100:]}


@app.get("/health")
async def health(): return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("MOCK_CHANNELS_PORT", "9804")), log_level="warning")
