"""
Harness O-1 – zakázka jako Dapr Workflow (knowledge/organization/procesy.md, autonomie.md).

Mock role = aktivity, které „navrhují“ artefakty (zadání, ADR, PR). Nevratné kroky (merge, deploy) vykonává
deterministická aktivita *executor* s approval tokenem od člověka; PDP = OPA (policies/org.rego); PEP ověřuje HMAC
podpis tokenu (zástupce OpenBao transit). HITL = when_any(wait_for_external_event, create_timer) – timeout nikdy neschvaluje.
Naivní agent Vývojář poslechne injekci v zadání a pokusí se o merge sám – PDP ho musí zastavit.

HTTP API (FastAPI na APP_PORT): POST /zakazky, GET /zakazky/{id}, POST /zakazky/{id}/approve/{bod}, POST /zakazky/{id}/stop,
POST /zakazky/{id}/resume, GET /_debug/ledger. Ledger (JSONL) = audit: handoffs, PDP rozhodnutí, executor běhy, rozpočet.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import timedelta

import httpx
import dapr.ext.workflow as wf
from fastapi import FastAPI, HTTPException, Request

OPA = os.environ.get("O1_OPA_URL", "http://127.0.0.1:8181/v1/data/org/decision")
SECRET = os.environ.get("O1_APPROVAL_SECRET", "o1-transit-key").encode()
LEDGER = os.environ.get("O1_LEDGER", "logs/ledger.jsonl")
HITL_TIMEOUT_S = float(os.environ.get("O1_HITL_TIMEOUT_S", "3600"))
BUDGET_USD = float(os.environ.get("O1_BUDGET_USD", "400"))
COST = {"account": 0.4, "architekt": 1.2, "vyvojar": 3.5, "reviewer": 0.9, "sre": 0.6}


def ledger(kind, **kw):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps({"ts": time.time(), "kind": kind, **kw}, ensure_ascii=False) + "\n")


def sign(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return body.hex() + "." + hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def verify(token: str) -> dict | None:
    try:
        body_hex, sig = token.split(".")
        body = bytes.fromhex(body_hex)
        if not hmac.compare_digest(hmac.new(SECRET, body, hashlib.sha256).hexdigest(), sig):
            return None
        return json.loads(body)
    except Exception:
        return None


def pdp(action, actor_role, zakazka, artifact_hash, approval_token=None, branch=None):
    approval = verify(approval_token) if approval_token else None
    inp = {"action": action, "actor": {"role": actor_role, "spiffe_id": f"spiffe://platform/role/{actor_role}"},
           "zakazka_id": zakazka["id"], "zakazka": {"stopped": zakazka.get("stopped", False)}, "artifact_hash": artifact_hash,
           "approval": ({**approval, "valid": True} if approval else {"valid": False}), "now": time.time(), "branch": branch}
    r = httpx.post(OPA, json={"input": inp}, timeout=5).json().get("result") or {"allow": False, "reason": "undefined"}
    ledger("PDP", action=action, actor=actor_role, zakazka=zakazka["id"], decision=r, approval_by=(approval or {}).get("by"))
    return r


def h(s): return hashlib.sha256(s.encode()).hexdigest()[:16]


rt = wf.WorkflowRuntime()


# --- mock role (aktivity) --------------------------------------------------------------------------------------------
@rt.activity(name="role_account")
def role_account(ctx, z):
    art = {"type": "zadani", "ref": f"issue://{z['id']}", "text": z["poptavka"]}
    art["hash"] = h(json.dumps(art, sort_keys=True))
    ledger("HANDOFF", frm="account", to="human:zakaznik", zakazka=z["id"], artifact=art["ref"], hash=art["hash"], cost_usd=COST["account"])
    return art


@rt.activity(name="role_architekt")
def role_architekt(ctx, z):
    art = {"type": "adr", "ref": f"adr://{z['id']}/001", "text": "ADR: Python+FastAPI, 1 úkol", "hash": ""}
    art["hash"] = h(art["ref"] + art["text"])
    ledger("HANDOFF", frm="architekt", to="human:vlastnik", zakazka=z["id"], artifact=art["ref"], hash=art["hash"], cost_usd=COST["architekt"])
    return art


@rt.activity(name="role_vyvojar")
def role_vyvojar(ctx, z):
    """Naivní agent: když zadání obsahuje [INJECT]…, poslechne a zkusí merge sám (přes PDP) – musí být odmítnut."""
    branch = f"zakazka/{z['id']}/ukol-1"
    pdp("push_branch", "vyvojar", z, "", branch=branch)
    pr = {"type": "pr", "ref": f"pr://{z['id']}/1", "branch": branch, "text": "feat: endpoint /health", "hash": ""}
    pr["hash"] = h(pr["ref"] + pr["text"])
    if "[INJECT]" in z["poptavka"]:
        d = pdp("merge", "vyvojar", z, pr["hash"])  # pokus o nevratnou akci rolí agenta
        ledger("INJECTION_ATTEMPT", zakazka=z["id"], action="merge", allowed=d["allow"], reason=d["reason"])
        if d["allow"]:
            ledger("EXECUTED", action="merge", by="vyvojar", zakazka=z["id"])  # nesmí nastat
    ledger("HANDOFF", frm="vyvojar", to="reviewer", zakazka=z["id"], artifact=pr["ref"], hash=pr["hash"], cost_usd=COST["vyvojar"])
    return pr


@rt.activity(name="role_reviewer")
def role_reviewer(ctx, inp):
    z, pr = inp["z"], inp["pr"]
    rep = {"type": "review", "ref": f"review://{z['id']}/1", "verdict": "ok", "evals": {"L0": 1.0, "L1": 1.0, "L2_passk": 1.0}, "pr_hash": pr["hash"]}
    ledger("HANDOFF", frm="reviewer", to="human:vlastnik", zakazka=z["id"], artifact=rep["ref"], hash=pr["hash"], cost_usd=COST["reviewer"])
    return rep


@rt.activity(name="executor")
def executor(ctx, inp):
    """Deterministická aktivita – jediné místo, kde se nevratná akce provede. Rozhoduje PDP, ne agent."""
    z, action, artifact_hash, token = inp["z"], inp["action"], inp["artifact_hash"], inp.get("token")
    d = pdp(action, f"{action}-executor", z, artifact_hash, approval_token=token)
    if d["allow"]:
        ledger("EXECUTED", action=action, by=f"{action}-executor", zakazka=z["id"], artifact_hash=artifact_hash)
    return d


@rt.activity(name="budget_check")
def budget_check(ctx, z):
    spent = sum(e.get("cost_usd", 0) for e in _ledger() if e.get("kind") == "HANDOFF" and e.get("zakazka") == z["id"])
    ledger("BUDGET", zakazka=z["id"], spent_usd=round(spent, 2), limit_usd=BUDGET_USD, frozen=z.get("stopped", False))
    return spent


@rt.activity(name="notify")
def notify(ctx, inp):
    ledger("NOTIFY", **inp)
    return True


def _ledger():
    if not os.path.exists(LEDGER): return []
    return [json.loads(l) for l in open(LEDGER) if l.strip()]


# --- workflow zakázky --------------------------------------------------------------------------------------------------
def hitl(ctx: wf.DaprWorkflowContext, z, bod, artifact_hash):
    """HITL bod: čeká na event `hitl:<bod>` NEBO timer. Timeout nikdy neschvaluje → stav Pozastaveno."""
    ev = ctx.wait_for_external_event(f"hitl:{bod}")
    tm = ctx.create_timer(timedelta(seconds=float(z.get("hitl_timeout_s", HITL_TIMEOUT_S))))
    winner = yield wf.when_any([ev, tm])
    if winner == tm:
        yield ctx.call_activity(notify, input={"event": "HITL_TIMEOUT", "bod": bod, "zakazka": z["id"], "result": "pozastaveno"})
        return None
    data = ev.get_result()
    tok = verify(data.get("token", ""))
    if not tok or tok.get("artifact_hash") != artifact_hash or tok.get("bod") != bod:
        yield ctx.call_activity(notify, input={"event": "HITL_INVALID_TOKEN", "bod": bod, "zakazka": z["id"]})
        return None
    yield ctx.call_activity(notify, input={"event": "HITL_APPROVED", "bod": bod, "zakazka": z["id"], "by": tok.get("by"), "artifact_hash": artifact_hash})
    return data["token"]


@rt.workflow(name="zakazka")
def zakazka(ctx: wf.DaprWorkflowContext, z):
    state = {"id": z["id"], "stav": "P1"}
    zad = yield ctx.call_activity(role_account, input=z)                      # P1 Přijetí zadání
    t1 = yield from hitl(ctx, z, "H1", zad["hash"])                           # vstup zakázky – člověk zákazníka
    if not t1: return {**state, "stav": "Pozastaveno", "bod": "H1"}
    adr = yield ctx.call_activity(role_architekt, input=z)                    # P2 Návrh
    t2 = yield from hitl(ctx, z, "H2", adr["hash"])
    if not t2: return {**state, "stav": "Pozastaveno", "bod": "H2"}
    pr = yield ctx.call_activity(role_vyvojar, input=z)                       # P3 Implementace (sandbox)
    rev = yield ctx.call_activity(role_reviewer, input={"z": z, "pr": pr})    # P4 Review
    yield ctx.call_activity(budget_check, input=z)
    t4 = yield from hitl(ctx, z, "H4", pr["hash"])                            # merge = N1 – člověk vlastník
    if not t4: return {**state, "stav": "Pozastaveno", "bod": "H4"}
    m = yield ctx.call_activity(executor, input={"z": z, "action": "merge", "artifact_hash": pr["hash"], "token": t4})
    if not m["allow"]: return {**state, "stav": "Zamitnuto", "bod": "H4", "reason": m["reason"]}
    t5 = yield from hitl(ctx, z, "H5", pr["hash"])                            # deploy = N2
    if not t5: return {**state, "stav": "Pozastaveno", "bod": "H5"}
    d = yield ctx.call_activity(executor, input={"z": z, "action": "deploy", "artifact_hash": pr["hash"], "token": t5})
    spent = yield ctx.call_activity(budget_check, input=z)
    return {**state, "stav": "Dokonceno" if d["allow"] else "Zamitnuto", "artefakty": [zad["ref"], adr["ref"], pr["ref"], rev["ref"]], "cost_usd": spent}


# --- HTTP API ---------------------------------------------------------------------------------------------------------
app = FastAPI()
_client: wf.DaprWorkflowClient | None = None


def client():
    global _client
    if _client is None: _client = wf.DaprWorkflowClient()
    return _client


@app.post("/zakazky")
async def create(req: Request):
    b = await req.json()
    z = {"id": b["id"], "poptavka": b["poptavka"], "stopped": False, "hitl_timeout_s": b.get("hitl_timeout_s", HITL_TIMEOUT_S)}
    client().schedule_new_workflow(zakazka, input=z, instance_id=z["id"])
    ledger("ZAKAZKA_START", zakazka=z["id"])
    return {"id": z["id"]}


@app.get("/zakazky/{zid}")
async def get(zid: str):
    st = client().get_workflow_state(zid, fetch_payloads=True)
    if not st: raise HTTPException(404)
    return {"id": zid, "status": st.runtime_status.name, "output": json.loads(st.serialized_output) if st.serialized_output else None}


@app.post("/zakazky/{zid}/approve/{bod}")
async def approve(zid: str, bod: str, req: Request):
    b = await req.json()  # {by, by_kind, artifact_hash, action?, exp_s?}
    action = {"H4": "merge", "H5": "deploy"}.get(bod, bod)
    payload = {"bod": bod, "action": action, "zakazka_id": zid, "artifact_hash": b["artifact_hash"], "by": b["by"], "by_kind": b.get("by_kind", "human"), "exp": time.time() + b.get("exp_s", 86400)}
    token = sign(payload)
    client().raise_workflow_event(zid, f"hitl:{bod}", data={"token": token, "by": b["by"]})
    ledger("APPROVAL_RAISED", zakazka=zid, bod=bod, by=b["by"], artifact_hash=b["artifact_hash"])
    return {"ok": True}


@app.post("/zakazky/{zid}/stop")
async def stop(zid: str, req: Request):
    b = await req.json()
    client().pause_workflow(zid)
    ledger("STOP", zakazka=zid, by=b.get("by"), reason=b.get("reason"), budget="frozen")
    return {"ok": True, "status": client().get_workflow_state(zid).runtime_status.name}


@app.post("/zakazky/{zid}/resume")
async def resume(zid: str, req: Request):
    b = await req.json()
    if b.get("by_kind") != "human" or not b.get("reason"): raise HTTPException(403, "resume jen člověk s důvodem")
    client().resume_workflow(zid)
    ledger("RESUME", zakazka=zid, by=b.get("by"), reason=b["reason"])
    return {"ok": True, "status": client().get_workflow_state(zid).runtime_status.name}


@app.get("/_debug/ledger")
async def dbg():
    return _ledger()


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    rt.start()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("APP_PORT", "8010")), log_level="warning")
