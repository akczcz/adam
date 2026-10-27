"""
agui.py – AG-UI server platformy (P3-1): jeden kanál k lidem nad celou firmou. Thread = zakázka (instance Dapr workflow), run = „sleduj
zakázku do dalšího rozhodovacího bodu“. Spec AG-UI 1.0 (ag-ui-protocol 1.0.0): RUN_STARTED s protocolVersion, role jako subagenti
(SUBAGENT_STARTED/FINISHED), předání artefaktů jako TEXT_MESSAGE role → člověk (disclosure čl. 50 z definice role, kanál `agui`, vkládá
platforma – T7), aktivity (ACTIVITY_SNAPSHOT), stav zakázky (STATE_SNAPSHOT); HITL = RUN_FINISHED outcome=interrupt (interrupt id
`hitl:<bod>:<hash>`), rozhodnutí člověka = RunAgentInput.resume [{interruptId, status: resolved, payload: {decision, reason}}] –
důvod povinný (T6, org.approvals.reason ≥ 10 znaků), approval token podepsaný transitem jako dřív, workflow se nemění (raise_event).
Stop = forwardedProps.action=stop (pause workflow + ukončení podů rolí zakázky) → outcome=cancelled.

Autorizace na transportu (spec ji neřeší): Bearer token Keycloaku (RS256 z JWKS P0_KC_JWKS_URL, iss P0_KC_ISSUER, realm role `human`,
tenant z claimu `tenant_id`); thread cizího tenanta = 404. Login člověka pro GUI: POST /agui/login (password grant přes klient
P0_GUI_CLIENT – zjednodušení P3-1; Authorization Code + PKCE v prohlížeči = P3-6). Bez Keycloaku (lokální fixture) HS256 dev tokeny
z P0_AGUI_DEV_USERS. Zdroj pravdy pro události je ledger aplikace (JSONL) – GUI nevidí nic, co není v auditu.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from ag_ui.core import (PROTOCOL_VERSION, ActivitySnapshotEvent, CustomEvent, EventType, Interrupt, RunAgentInput, RunErrorEvent,
                        RunFinishedCancelledOutcome, RunFinishedEvent, RunFinishedInterruptOutcome, RunFinishedSuccessOutcome, RunStartedEvent,
                        StateSnapshotEvent, SubagentErrorEvent, SubagentFinishedEvent, SubagentFinishedSuccessOutcome, SubagentStartedEvent,
                        TextMessageContentEvent, TextMessageEndEvent, TextMessageStartEvent)
from ag_ui.encoder import EventEncoder

router = APIRouter(prefix="/agui")
CTX: dict = {}   # dodá app.py: ledger, read_ledger, wf_state, create, approve, reject, stop, disclosure, root_dir
THREAD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,39}$")
MIN_REASON = 10   # org.approvals CHECK (length(reason) >= 10) – proti automation bias (metriky.md T6)
RUN_MAX_S = float(os.environ.get("P0_AGUI_RUN_MAX_S", "1800"))
BOD_PROCESS = {"H1": "P1", "H1a": "P1", "H2": "P2", "H4": "P4", "H5": "P5", "rozpocet": "X2", "klasifikace": "P1a", "dialog": "P1"}
BOD_ACTION = {"H1": "zadani.accept", "H1a": "pravnik.stanovisko", "H2": "navrh.accept", "H4": "pr.merge", "H5": "deploy.apply", "rozpocet": "budget.raise", "klasifikace": "zadani.classify"}
WAIT_EVENTS = ("HITL_WAIT", "DIALOG_WAIT", "KLASIFIKACE_WAIT")   # P3-4: + dotazník klasifikační brány (interrupt reason=klasifikace)
ARTIFACT_FILE = {"account": "artifacts/zadani.md", "architekt": "artifacts/adr.md", "reviewer": "artifacts/review.md"}


# --- identita člověka -------------------------------------------------------------------------------------------------
_JWKS = None
DEV_SECRET = os.environ.get("O1_APPROVAL_SECRET", "o1-transit-key")


def _jwks():
    global _JWKS
    url = os.environ.get("P0_KC_JWKS_URL")
    if url and _JWKS is None: _JWKS = jwt.PyJWKClient(url, cache_keys=True, lifespan=300)
    return _JWKS


def user_from_request(req: Request) -> dict:
    """{sub, name, tenant, roles} z Bearer tokenu; 401 bez platného tokenu, 403 bez role human."""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): raise HTTPException(401, "chybí Bearer token")
    raw = auth[7:].strip()
    try:
        if _jwks():
            key = _jwks().get_signing_key_from_jwt(raw).key
            c = jwt.decode(raw, key, algorithms=["RS256"], issuer=os.environ.get("P0_KC_ISSUER"), options={"verify_aud": False, "require": ["exp", "sub", "iss"]})
        else:
            c = jwt.decode(raw, DEV_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except Exception as e:
        raise HTTPException(401, f"neplatný token: {type(e).__name__}")
    roles = c.get("roles") or (c.get("realm_access") or {}).get("roles") or []
    if "human" not in roles: raise HTTPException(403, "GUI je pro lidi (realm role human)")
    if not c.get("tenant_id"): raise HTTPException(403, "token bez tenant_id")
    # klient harness-human nemá scope `profile` (preferred_username) a realm v clusteru se znovu neimportuje → jméno z loginu (cache sub → username); P3-2: scope v realmu
    return {"sub": c["sub"], "name": c.get("preferred_username") or c.get("name") or _NAMES.get(c["sub"]) or c["sub"], "tenant": c["tenant_id"], "roles": roles, "exp": c.get("exp")}


_NAMES: dict = {}


@router.post("/login")
async def login(req: Request):
    b = await req.json(); user, pw = (b.get("username") or "").strip(), b.get("password") or ""
    kc = os.environ.get("P0_KC_TOKEN_URL")
    if kc:
        r = await asyncio.to_thread(httpx.post, kc, data={"grant_type": "password", "client_id": os.environ.get("P0_GUI_CLIENT", "harness-human"), "username": user, "password": pw}, timeout=15)
        ok = r.status_code == 200
        CTX["ledger"]("GUI_LOGIN", user=user, ok=ok, idp="keycloak", http=r.status_code)
        if not ok: raise HTTPException(401, "přihlášení odmítnuto")
        j = r.json(); c = jwt.decode(j["access_token"], options={"verify_signature": False})
        if c.get("sub"): _NAMES[c["sub"]] = c.get("preferred_username") or user
        return {"access_token": j["access_token"], "refresh_token": j.get("refresh_token"), "expires_in": j.get("expires_in"), "user": {"sub": c.get("sub"), "name": c.get("preferred_username", user), "tenant": c.get("tenant_id"), "roles": c.get("roles")}}
    users = json.loads(os.environ.get("P0_AGUI_DEV_USERS", "{}"))   # lokální fixture bez Keycloaku
    u = users.get(user)
    CTX["ledger"]("GUI_LOGIN", user=user, ok=bool(u and u.get("password") == pw), idp="dev")
    if not u or u.get("password") != pw: raise HTTPException(401, "přihlášení odmítnuto")
    exp = int(time.time()) + 900; base = {"sub": f"dev:{user}", "preferred_username": user, "tenant_id": u.get("tenant_id", "acme"), "roles": u.get("roles", ["human"])}
    tok = jwt.encode(base | {"exp": exp, "iss": "dev"}, DEV_SECRET, algorithm="HS256")
    return {"access_token": tok, "refresh_token": jwt.encode(base | {"typ": "refresh", "exp": int(time.time()) + 3600}, DEV_SECRET, algorithm="HS256"), "expires_in": 900, "user": {"sub": f"dev:{user}", "name": user, "tenant": u.get("tenant_id", "acme"), "roles": u.get("roles", ["human"])}}


@router.post("/refresh")
async def refresh(req: Request):
    """Obnova tokenu (access token Keycloaku 15 min, dlouhá zakázka v GUI ho přežije – P3-2 nález): refresh_token → nový access token přes server."""
    b = await req.json(); rt = b.get("refresh_token") or ""
    kc = os.environ.get("P0_KC_TOKEN_URL")
    if kc:
        r = await asyncio.to_thread(httpx.post, kc, data={"grant_type": "refresh_token", "client_id": os.environ.get("P0_GUI_CLIENT", "harness-human"), "refresh_token": rt}, timeout=15)
        if r.status_code != 200: raise HTTPException(401, "refresh odmítnut")
        j = r.json(); c = jwt.decode(j["access_token"], options={"verify_signature": False})
        if c.get("sub") and c.get("preferred_username"): _NAMES[c["sub"]] = c["preferred_username"]
        return {"access_token": j["access_token"], "refresh_token": j.get("refresh_token"), "expires_in": j.get("expires_in")}
    try: c = jwt.decode(rt, DEV_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except Exception: raise HTTPException(401, "refresh odmítnut")
    if c.get("typ") != "refresh": raise HTTPException(401, "refresh odmítnut")
    exp = int(time.time()) + 900; base = {k: c[k] for k in ("sub", "preferred_username", "tenant_id", "roles") if k in c}
    return {"access_token": jwt.encode(base | {"exp": exp, "iss": "dev"}, DEV_SECRET, algorithm="HS256"), "refresh_token": jwt.encode(base | {"typ": "refresh", "exp": int(time.time()) + 3600}, DEV_SECRET, algorithm="HS256"), "expires_in": 900}


@router.get("/me")
async def me(req: Request):
    return user_from_request(req)


# --- thready (zakázky) -----------------------------------------------------------------------------------------------
def thread_entries(zid):
    return [e for e in CTX["read_ledger"]() if e.get("zakazka") == zid]


def thread_start(zid):
    return next((e for e in CTX["read_ledger"]() if e.get("kind") == "ZAKAZKA_START" and e.get("zakazka") == zid), None)


def thread_of_tenant(zid, user):
    """ZAKAZKA_START threadu musí nést tenant uživatele – jinak 404 (cizí thread neexistuje)."""
    s = thread_start(zid)
    if not s: return None
    if (s.get("tenant") or os.environ.get("P0_TENANT", "acme")) != user["tenant"] and user["tenant"] != PLATFORM_TENANT: raise HTTPException(404, "thread neexistuje")
    return s


PLATFORM_TENANT = "platform"   # P3-2: průřezový tenant (governance) – vidí všechny thready, zakázky nezakládá


def pending_interrupt(entries):
    """Poslední HITL_WAIT / DIALOG_WAIT / KLASIFIKACE_WAIT bez pozdějšího rozhodnutí (resp. odpovědi) → záznam čekání; jinak None. Dialog (P3-3): otázky Account zadavateli; klasifikace (P3-4): K1–K6."""
    waits = [(i, e) for i, e in enumerate(entries) if e.get("kind") == "NOTIFY" and e.get("event") in WAIT_EVENTS]
    if not waits: return None
    i, w = waits[-1]
    if w.get("event") == "KLASIFIKACE_WAIT":
        later = [e for e in entries[i + 1:] if e.get("kind") in ("KLASIFIKACE", "KLASIFIKACE_RAISED") or (e.get("kind") == "NOTIFY" and e.get("event") == "KLASIFIKACE_TIMEOUT")]
    elif w.get("event") == "DIALOG_WAIT":
        later = [e for e in entries[i + 1:] if e.get("kind") == "NOTIFY" and e.get("event") in ("DIALOG_ANSWER", "DIALOG_TIMEOUT", "DIALOG_LIMIT")]
    else:
        later = [e for e in entries[i + 1:] if e.get("kind") == "NOTIFY" and e.get("event") in ("HITL_APPROVED", "HITL_TIMEOUT", "HITL_INVALID_TOKEN", "HITL_REJECTED") and e.get("bod") == w.get("bod")]
    if later: return None
    return w


def interrupt_id(w): return f"{'dialog' if w.get('event') == 'DIALOG_WAIT' else 'klasifikace' if w.get('event') == 'KLASIFIKACE_WAIT' else 'hitl'}:{w['bod']}:{w.get('artifact_hash')}"


def state_of(zid, entries):
    st = CTX["wf_state"](zid) or {}
    start = next((e for e in entries if e.get("kind") == "ZAKAZKA_START"), {})
    bud = next((e for e in reversed(entries) if e.get("kind") in ("BUDGET", "BUDGET_GATE")), {})
    roles = {}
    for e in entries:
        if e.get("kind") == "ROLE_GATE": roles[e["role"]] = "running" if e.get("passed") else "blocked"
        if e.get("kind") == "AGENT_RUN": roles[e["role"]] = "error" if e.get("error") else "done"
    w = pending_interrupt(entries)
    out = st.get("output") or {}
    kl = next((e for e in reversed(entries) if e.get("kind") == "KLASIFIKACE"), {}); sla = [e for e in entries if e.get("kind") == "SLA_BREACH"]
    return {"id": zid, "tenant": start.get("tenant") or os.environ.get("P0_TENANT", "acme"), "status": st.get("status"), "stav": out.get("stav") or ("čeká na " + w["bod"] if w else ("běží" if st.get("status") == "RUNNING" else st.get("status"))),
            "bod": w.get("bod") if w else out.get("bod"), "budget_usd": start.get("budget_usd"), "spent_usd": bud.get("spent_usd"), "roles": roles, "started": start.get("ts"), "poptavka": start.get("poptavka"),
            "profile": kl.get("profile"), "sensitivity": kl.get("sensitivity"), "sla_breaches": [e.get("bod") for e in sla]}


@router.get("/threads")
async def threads(req: Request):
    u = user_from_request(req)
    L = CTX["read_ledger"](); out = []
    for s in [e for e in L if e.get("kind") == "ZAKAZKA_START" and ((e.get("tenant") or os.environ.get("P0_TENANT", "acme")) == u["tenant"] or u["tenant"] == PLATFORM_TENANT)]:
        zid = s["zakazka"]; out.append(state_of(zid, [e for e in L if e.get("zakazka") == zid]))
    return {"tenant": u["tenant"], "threads": sorted(out, key=lambda t: -(t.get("started") or 0)), "tenants": [t["id"] for t in CTX.get("tenants") or []]}


# --- ledger → AG-UI události --------------------------------------------------------------------------------------------
def _artifact_text_path(zid, rel):
    try: return open(os.path.join(CTX["root_dir"], zid, rel), encoding="utf-8", errors="replace").read()[:4000]
    except Exception: return ""


def _artifact_text(zid, e):
    """Obsah artefaktu k předání (čte se z adresáře zakázky v podu aplikace – AG-UI server běží tamtéž)."""
    root = f"{CTX['root_dir']}/{zid}"; frm = e.get("frm")
    if frm == "vyvojar":
        run = next((x for x in reversed(thread_entries(zid)) if x.get("kind") == "AGENT_RUN" and x.get("role") == "vyvojar"), {})
        files = run.get("files") or []
        return "Soubory PR:\n" + "\n".join(f"- {f['path']} (sha256 {f['sha256']})" for f in files[:40]) + ("\n\n" + (run.get("result_text") or "")[:1500])
    p = "artifacts/otazky.md" if str(e.get("artifact", "")).startswith("otazky://") else ARTIFACT_FILE.get(frm)
    try:
        if p: return open(os.path.join(root, p), encoding="utf-8", errors="replace").read()[:6000]
    except Exception: pass
    return ""


def events_for(zid, entries, start_idx=0, subagents=None):
    """Deterministické mapování záznamů ledgeru [start_idx:] na AG-UI události (id odvozená z indexu → replay je idempotentní)."""
    subagents = subagents if subagents is not None else {}
    ev = []
    def act(i, typ, content, sub=None):
        ev.append(ActivitySnapshotEvent(type=EventType.ACTIVITY_SNAPSHOT, message_id=f"{zid}:{i}", activity_type=typ, content=content, replace=True, subagent_run_id=sub, timestamp=int(entries[i].get("ts", 0) * 1000)))
    def msg(i, role, name, text, sub=None):
        mid = f"{zid}:{i}:msg"; ts = int(entries[i].get("ts", 0) * 1000)
        ev.append(TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=mid, role=role, name=name, subagent_run_id=sub, timestamp=ts))
        ev.append(TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=mid, delta=text or "(prázdné)", subagent_run_id=sub, timestamp=ts))
        ev.append(TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=mid, subagent_run_id=sub, timestamp=ts))
    for i in range(start_idx, len(entries)):
        e = entries[i]; k = e.get("kind"); role = e.get("role"); sub = subagents.get(role)
        if k == "ZAKAZKA_START":
            msg(i, "user", e.get("by") or "zadavatel", e.get("poptavka") or "")
            act(i, "zakazka", {"budget_usd": e.get("budget_usd"), "tenant": e.get("tenant"), "channel": e.get("channel")})
        elif k == "ROLE_GATE":
            sub = subagents[role] = f"{zid}:{role}:{i}"
            if e.get("passed"):
                ev.append(SubagentStartedEvent(type=EventType.SUBAGENT_STARTED, subagent_run_id=sub, name=role, description=f"eval gate {e.get('gate')} v{e.get('version')}", timestamp=int(e.get("ts", 0) * 1000)))
            else:
                ev.append(SubagentErrorEvent(type=EventType.SUBAGENT_ERROR, subagent_run_id=sub, message=f"role {role} bez prošlého eval gate", timestamp=int(e.get("ts", 0) * 1000)))
        elif k == "BUDGET_GATE": act(i, "budget_gate", {"role": role, "spent_usd": e.get("spent_usd"), "limit_usd": e.get("limit_usd"), "exceeded": e.get("exceeded"), "source": e.get("source")}, sub)
        elif k == "BUDGET_EXCEEDED": act(i, "budget", {"role": role, "source": e.get("source"), "spent_usd": e.get("spent_usd"), "limit_usd": e.get("limit_usd"), "escalate_to": e.get("escalate_to")}, sub)
        elif k == "BUDGET": act(i, "budget", {"spent_usd": e.get("spent_usd"), "limit_usd": e.get("limit_usd"), "source": e.get("source"), "by_role": e.get("by_role")})
        elif k == "ROLE_POD_CREATE": act(i, "pod", {"role": role, "pod": e.get("pod"), "runtime_class": e.get("runtime_class"), "image": e.get("image"), "state": "created"}, sub)
        elif k == "ROLE_POD": act(i, "pod", {"role": role, "pod": e.get("pod"), "phase": e.get("phase"), "node": e.get("node"), "t_start_s": e.get("t_start_s"), "t_run_s": e.get("t_run_s"), "identity": (e.get("identity") or {}).get("spiffe_id"), "state": "finished"}, sub)
        elif k == "ROLE_POD_ERROR": act(i, "pod", {"role": role, "pod": e.get("pod"), "error": e.get("error"), "state": "error"}, sub)
        elif k == "TOOL": act(i, "tool", {"role": role, "tool": e.get("tool"), "http": e.get("http"), "allowed": e.get("allowed")}, sub)
        elif k == "HANDOFF":
            disc = CTX["disclosure"](e.get("frm"), "agui")
            msg(i, "assistant", e.get("frm"), f"> {disc}\n\n**Předání → {e.get('to')}** · artefakt `{e.get('artifact')}` · hash `{e.get('hash')}`\n\n{_artifact_text(zid, e)}", subagents.get(e.get("frm")))
            act(i, "handoff", {"from": e.get("frm"), "to": e.get("to"), "artifact": e.get("artifact"), "hash": e.get("hash"), "cost_usd": e.get("cost_usd"), "verdict": e.get("verdict")}, subagents.get(e.get("frm")))
        elif k == "AGENT_RUN":
            sub = subagents.get(role) or f"{zid}:{role}:{i}"
            if e.get("error"): ev.append(SubagentErrorEvent(type=EventType.SUBAGENT_ERROR, subagent_run_id=sub, message=str(e.get("error"))[:300], timestamp=int(e.get("ts", 0) * 1000)))
            else: ev.append(SubagentFinishedEvent(type=EventType.SUBAGENT_FINISHED, subagent_run_id=sub, outcome=SubagentFinishedSuccessOutcome(type="success"), result={"role": role, "cost_usd": e.get("cost_usd"), "tool_uses": e.get("tool_uses"), "via": e.get("via"), "num_turns": e.get("num_turns")}, timestamp=int(e.get("ts", 0) * 1000)))
        elif k == "PUBLISHED": act(i, "published", {"kind": e.get("publish_kind"), "number": e.get("number"), "url": e.get("url"), "mode": e.get("mode")})
        elif k == "NOTIFY":
            evn = e.get("event")
            if evn and evn.startswith("HITL_"): act(i, "hitl", {"state": evn[5:].lower(), "bod": e.get("bod"), "artifact_hash": e.get("artifact_hash"), "by": e.get("by"), "timeout_s": e.get("timeout_s"), "sla_s": e.get("sla_s"), "result": e.get("result"), "reason": e.get("reason")})
            elif evn and evn.startswith("KLASIFIKACE_"): act(i, "klasifikace", {"state": evn[12:].lower(), "bod": "klasifikace", "timeout_s": e.get("timeout_s"), "sla_s": e.get("sla_s"), "result": e.get("result")})
            elif evn and evn.startswith("DIALOG_"):
                act(i, "dialog", {"state": evn[7:].lower(), "round": e.get("round"), "by": e.get("by"), "answer": e.get("answer"), "result": e.get("result")})
                if evn == "DIALOG_ANSWER": msg(i, "user", e.get("by") or "zadavatel", str(e.get("answer") or ""))
            else: act(i, "notify", {k2: v for k2, v in e.items() if k2 not in ("ts", "kind")})
        elif k in ("PDP", "EXECUTED", "EXECUTOR_REFUSED"): act(i, "executor", {"kind": k, "action": e.get("action"), "actor": e.get("actor") or e.get("by"), "decision": e.get("decision"), "applied": e.get("applied"), "reason": e.get("reason")})
        elif k in ("APPROVAL_RAISED", "APPROVAL_REJECTED"): act(i, "approval", {"decision": "approve" if k == "APPROVAL_RAISED" else "reject", "bod": e.get("bod"), "by": e.get("by"), "reason": e.get("reason"), "channel": e.get("channel")})
        elif k in ("STOP", "RESUME"): act(i, "stop", {"kind": k.lower(), "by": e.get("by"), "reason": e.get("reason"), "pods_killed": e.get("pods_killed")})
        elif k in ("REGISTRY_AGENT", "DIALOG_RAISED"): act(i, "registry" if k == "REGISTRY_AGENT" else "dialog", {k2: v for k2, v in e.items() if k2 not in ("ts", "kind", "zakazka")})
        elif k == "KLASIFIKACE": act(i, "klasifikace", {"state": "done", "profile": e.get("profile"), "sensitivity": e.get("sensitivity"), "by": e.get("by"), "yes": ",".join(q for q, v in (e.get("answers") or {}).items() if v) or "-", "registry": e.get("registry"), "opa_http": e.get("opa_http"), "hash": e.get("hash")})   # P3-4
        elif k == "KLASIFIKACE_RAISED": act(i, "klasifikace", {"state": "answered", "by": e.get("by"), "channel": e.get("channel"), "yes": ",".join(q for q, v in (e.get("answers") or {}).items() if v) or "-"})
        elif k == "SLA_BREACH": act(i, "sla", {"state": "breach", "bod": e.get("bod"), "sla_s": e.get("sla_s"), "escalated_to": e.get("escalated_to"), "registry": e.get("registry"), "result": e.get("result")})   # P3-4: SLA eskalace, zakázka čeká dál
        elif k in ("CHANNEL_SENT", "CHANNEL_DRYRUN", "CHANNEL_ERROR"): act(i, "channel", {"state": k[8:].lower(), "channel": e.get("channel"), "to": e.get("to"), "role": e.get("role"), "http": e.get("http"), "generated_by": e.get("generated_by"), "disclosure": e.get("disclosure"), "hash": e.get("hash"), "error": e.get("error")})   # P3-4: N3 čl. 50 naostro
        elif k == "REGISTRY_ZAKAZKA": act(i, "registry", {"status": e.get("status"), "spent_usd": e.get("spent_usd"), "written": e.get("written")})
    return ev


# --- run ------------------------------------------------------------------------------------------------------------------
def _validate_resume(inp: RunAgentInput, zid, entries):
    """Rozhodnutí člověka musí patřit k otevřenému interruptu a nést důvod – jinak 422 ještě před streamem."""
    out = []
    w = pending_interrupt(entries)
    for r in inp.resume or []:
        p = r.payload if isinstance(r.payload, dict) else {}
        if not w or r.interrupt_id != interrupt_id(w): raise HTTPException(409, "interrupt není otevřený (jiný bod nebo artefakt)")
        if w.get("event") == "DIALOG_WAIT":   # P3-3: odpověď zadavatele na otázky Account – text, ne approval
            answer = (p.get("answer") or "").strip()
            if len(answer) < 3: raise HTTPException(422, "odpověď na otázky Account je povinná")
            out.append({"kind": "dialog", "answer": answer, "interrupt_id": r.interrupt_id}); continue
        if w.get("event") == "KLASIFIKACE_WAIT":   # P3-4: dotazník K1–K6 – každá otázka zodpovězena (bool), důvod volitelný
            ans = p.get("answers") if isinstance(p.get("answers"), dict) else None
            keys = [q[0] for q in CTX.get("klas_questions") or []]
            if ans is None or any(k not in ans or not isinstance(ans[k], bool) for k in keys): raise HTTPException(422, f"klasifikace vyžaduje odpovědi ano/ne na {', '.join(keys)}")
            out.append({"kind": "klasifikace", "answers": {k: ans[k] for k in keys}, "reason": (p.get("reason") or "").strip() or None, "interrupt_id": r.interrupt_id}); continue
        reason = (p.get("reason") or "").strip()
        if len(reason) < MIN_REASON: raise HTTPException(422, f"důvod rozhodnutí je povinný (≥ {MIN_REASON} znaků) – org.approvals.reason, T6")
        decision = "reject" if r.status == "cancelled" or p.get("decision") == "reject" else "approve"
        out.append({"kind": "hitl", "bod": w["bod"], "artifact_hash": w.get("artifact_hash"), "decision": decision, "reason": reason, "interrupt_id": r.interrupt_id})
    return out


@router.post("/run")
async def run(req: Request):
    u = user_from_request(req)
    try: inp = RunAgentInput.model_validate(await req.json())
    except Exception as e: raise HTTPException(422, f"RunAgentInput: {str(e)[:200]}")
    zid = inp.thread_id
    if not THREAD_RE.match(zid or ""): raise HTTPException(422, "threadId: [A-Za-z0-9][A-Za-z0-9_.-]{2,39}")
    fp = inp.forwarded_props if isinstance(inp.forwarded_props, dict) else {}
    start = thread_of_tenant(zid, u)
    created = False
    if not start:
        if fp.get("action") or inp.resume: raise HTTPException(404, "thread neexistuje")
        if u["tenant"] == PLATFORM_TENANT: raise HTTPException(403, "tenant platform zakázky nezakládá (průřez)")
        if "klasifikace" in fp and (not isinstance(fp["klasifikace"], dict) or any(not isinstance(fp["klasifikace"].get(q[0]), bool) for q in CTX.get("klas_questions") or [])): raise HTTPException(422, "forwardedProps.klasifikace: odpovědi ano/ne na K1–K6")
        user_msgs = [m for m in inp.messages if getattr(m, "role", None) == "user"]
        text = user_msgs[-1].content if user_msgs else None
        if not isinstance(text, str) or not text.strip(): raise HTTPException(422, "nový thread = první zpráva uživatele je poptávka")
        await asyncio.to_thread(CTX["create"], zid, text.strip(), u, fp)
        created = True
    entries = thread_entries(zid)
    decisions = _validate_resume(inp, zid, entries) if inp.resume else []
    for d in decisions:
        if d["kind"] == "dialog": await asyncio.to_thread(CTX["answer"], zid, u, d["answer"]); continue
        if d["kind"] == "klasifikace": await asyncio.to_thread(CTX["classify"], zid, u, d["answers"], d["reason"]); continue
        await asyncio.to_thread(CTX["approve"] if d["decision"] == "approve" else CTX["reject"], zid, d["bod"], d["artifact_hash"], u, d["reason"])
    stopped = None
    if fp.get("action") == "stop":
        if len((fp.get("reason") or "").strip()) < MIN_REASON: raise HTTPException(422, "stop vyžaduje důvod (≥ 10 znaků)")
        stopped = await asyncio.to_thread(CTX["stop"], zid, u, fp["reason"].strip())
    run_id = inp.run_id or str(uuid.uuid4())
    enc = EventEncoder()

    async def stream():
        t0 = time.time(); subagents = {}; resolved = {d["interrupt_id"] for d in decisions}; last_ping = time.time()
        yield enc.encode(RunStartedEvent(type=EventType.RUN_STARTED, thread_id=zid, run_id=run_id, protocol_version=PROTOCOL_VERSION, parent_run_id=inp.parent_run_id, timestamp=int(t0 * 1000)))
        ents = thread_entries(zid)
        for e in events_for(zid, ents, 0, subagents): yield enc.encode(e)
        yield enc.encode(StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state_of(zid, ents)))
        if created: yield enc.encode(CustomEvent(type=EventType.CUSTOM, name="thread_created", value={"threadId": zid, "by": u["name"]}))
        if stopped is not None:
            yield enc.encode(CustomEvent(type=EventType.CUSTOM, name="stopped", value=stopped))
            yield enc.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=zid, run_id=run_id, outcome=RunFinishedCancelledOutcome(type="cancelled"), result=state_of(zid, thread_entries(zid))))
            return
        n = len(ents)
        while True:
            if await req.is_disconnected(): return
            ents = thread_entries(zid)
            if len(ents) > n:
                for e in events_for(zid, ents, n, subagents): yield enc.encode(e)
                n = len(ents); yield enc.encode(StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state_of(zid, ents)))
            w = pending_interrupt(ents)
            if w and interrupt_id(w) not in resolved:
                art = next((e for e in reversed(ents) if e.get("kind") == "HANDOFF" and e.get("hash") == w.get("artifact_hash")), {})
                exp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(w.get("ts", t0) + float(w.get("timeout_s") or 0))) if w.get("timeout_s") else None
                if w.get("event") == "KLASIFIKACE_WAIT":   # P3-4: dotazník klasifikační brány (A2UI zatím ne – vlastní schéma formuláře, viz p3-zakaznik.md)
                    qs = [{"id": q, "text": t, "yes": y} for q, t, y in (CTX.get("klas_questions") or [])]
                    itr = Interrupt(id=interrupt_id(w), reason="klasifikace", message="Klasifikační brána P1a (AI Act příloha III, čl. 5): odpovězte ano/ne na K1–K6 – profil rizika zakázky určí platforma", expires_at=exp,
                                    response_schema={"type": "object", "required": ["answers"], "properties": {"answers": {"type": "object", "required": [q["id"] for q in qs], "properties": {q["id"]: {"type": "boolean", "title": q["text"]} for q in qs}}, "reason": {"type": "string"}}},
                                    metadata={"bod": "klasifikace", "artifact_hash": w.get("artifact_hash"), "process": "P1a", "action": "zadani.classify", "questions": qs, "sla_s": w.get("sla_s")})
                elif w.get("event") == "DIALOG_WAIT":
                    itr = Interrupt(id=interrupt_id(w), reason="dialog", message=f"Account má upřesňující otázky (kolo {w.get('round')}) – odpovězte", expires_at=exp,
                                    response_schema={"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string", "minLength": 3}}},
                                    metadata={"bod": "dialog", "round": w.get("round"), "artifact_hash": w.get("artifact_hash"), "artifact": art.get("artifact"), "from": "account", "questions": _artifact_text_path(zid, "artifacts/otazky.md")})
                else:
                    itr = Interrupt(id=interrupt_id(w), reason="approval", message=f"Schválení {w['bod']} – rozhodněte s důvodem (T6)", expires_at=exp,
                                    response_schema={"type": "object", "required": ["decision", "reason"], "properties": {"decision": {"enum": ["approve", "reject"]}, "reason": {"type": "string", "minLength": MIN_REASON}}},
                                    metadata={"bod": w["bod"], "artifact_hash": w.get("artifact_hash"), "artifact": art.get("artifact"), "from": art.get("frm"), "action": BOD_ACTION.get(w["bod"], w["bod"]), "process": BOD_PROCESS.get(w["bod"])})
                yield enc.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=zid, run_id=run_id, outcome=RunFinishedInterruptOutcome(type="interrupt", interrupts=[itr]), result=state_of(zid, ents)))
                return
            st = CTX["wf_state"](zid) or {}
            if st.get("status") in ("COMPLETED", "FAILED", "TERMINATED"):
                yield enc.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=zid, run_id=run_id, outcome=RunFinishedSuccessOutcome(type="success"), result=state_of(zid, ents)))
                return
            if st.get("status") == "SUSPENDED":
                yield enc.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=zid, run_id=run_id, outcome=RunFinishedCancelledOutcome(type="cancelled"), result=state_of(zid, ents)))
                return
            if time.time() - t0 > RUN_MAX_S:
                yield enc.encode(RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=zid, run_id=run_id, outcome=RunFinishedSuccessOutcome(type="success"), result=state_of(zid, ents), metadata={"continues": True}))
                return
            if time.time() - last_ping > 15: yield ": ping\n\n"; last_ping = time.time()
            await asyncio.sleep(1.0)

    return StreamingResponse(stream(), media_type=enc.get_content_type(), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/threads/{zid}")
async def thread_get(zid: str, req: Request):
    u = user_from_request(req)
    if not thread_of_tenant(zid, u): raise HTTPException(404, "thread neexistuje")
    ents = thread_entries(zid)
    w = pending_interrupt(ents)
    return {"state": state_of(zid, ents), "interrupt": ({"id": interrupt_id(w), "bod": w["bod"], "artifact_hash": w.get("artifact_hash")} if w else None), "entries": len(ents)}


# --- governance (P3-3): čtení přes Governance MCP (org_reader, RLS per tenant), akce přes aplikaci (zápis org.*) -----------------------
GOV_URL = os.environ.get("P0_GOV_URL", "")


@router.get("/gov/resources")
async def gov_resources(req: Request):
    u = user_from_request(req)
    if not GOV_URL: raise HTTPException(503, "Governance MCP není nakonfigurován (P0_GOV_URL)")
    r = await asyncio.to_thread(httpx.get, f"{GOV_URL}/resources", headers={"Authorization": req.headers.get("Authorization", "")}, timeout=15)
    return r.json() if r.status_code == 200 else JSONResponse(r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:200]}, status_code=r.status_code)


@router.post("/gov/tools/{name}")
async def gov_tool(name: str, req: Request):
    """Proxy na Governance MCP s tokenem člověka (identita a tenant zůstávají jeho – AG-UI server nic nepřebarvuje)."""
    user_from_request(req)
    if not GOV_URL: raise HTTPException(503, "Governance MCP není nakonfigurován (P0_GOV_URL)")
    try: args = await req.json()
    except Exception: args = {}
    r = await asyncio.to_thread(httpx.post, f"{GOV_URL}/tools/{name}", json=args or {}, headers={"Authorization": req.headers.get("Authorization", "")}, timeout=30)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"detail": r.text[:300]}
    return body if r.status_code == 200 else JSONResponse(body, status_code=r.status_code)


@router.get("/gov/export.jsonl")
async def gov_export(req: Request):
    user_from_request(req)
    r = await asyncio.to_thread(httpx.get, f"{GOV_URL}/export.jsonl", headers={"Authorization": req.headers.get("Authorization", "")}, timeout=60)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(r.text, status_code=r.status_code, headers={"Content-Disposition": "attachment; filename=org-export.jsonl"})


def _platform_or_owner(u, tenant):
    if u["tenant"] != PLATFORM_TENANT and u["tenant"] != tenant: raise HTTPException(403, "jen tenant platform nebo vlastník tenanta")


@router.post("/gov/autonomy")
async def gov_autonomy(req: Request):
    """Posun autonomie role × tenant (metriky.md §6): nahoru jen při splněných podmínkách (409 s důvody), vždy s důvodem člověka → org.role_autonomy + agent_events."""
    u = user_from_request(req); b = await req.json()
    role, tenant, level, reason = b.get("role"), b.get("tenant") or u["tenant"], b.get("level"), (b.get("reason") or "").strip()
    _platform_or_owner(u, tenant)
    if len(reason) < MIN_REASON: raise HTTPException(422, "důvod je povinný (≥ 10 znaků)")
    res = await asyncio.to_thread(CTX["autonomy"], role, tenant, level, u, reason)
    CTX["ledger"]("AUTONOMY_CHANGE", role=role, tenant=tenant, level=level, by=u["name"], ok=res.get("ok"), reasons=res.get("reasons"), channel="agui")
    if not res.get("ok"): return JSONResponse(res, status_code=409)
    return res


@router.post("/gov/tenant/{tenant}/stop")
async def gov_tenant_stop(tenant: str, req: Request):
    u = user_from_request(req); b = await req.json(); reason = (b.get("reason") or "").strip()
    _platform_or_owner(u, tenant)
    if len(reason) < MIN_REASON: raise HTTPException(422, "stop tenanta vyžaduje důvod (≥ 10 znaků)")
    return await asyncio.to_thread(CTX["stop_tenant"], tenant, u, reason)


@router.post("/gov/tenant/{tenant}/resume")
async def gov_tenant_resume(tenant: str, req: Request):
    u = user_from_request(req); b = await req.json(); reason = (b.get("reason") or "").strip()
    _platform_or_owner(u, tenant)
    if len(reason) < MIN_REASON: raise HTTPException(422, "resume tenanta vyžaduje důvod (≥ 10 znaků)")
    return await asyncio.to_thread(CTX["resume_tenant"], tenant, u, reason)


@router.get("/klasifikace")
async def klas_questions(req: Request):
    """P3-4: otázky klasifikační brány K1–K6 (autonomie.md) pro formulář nové zakázky v GUI – odpovědi jdou s poptávkou (forwardedProps.klasifikace) nebo jako resume interruptu."""
    user_from_request(req)
    return {"questions": [{"id": q, "text": t, "yes": y} for q, t, y in (CTX.get("klas_questions") or [])], "profiles": ["standard", "high-risk-III/4", "high-risk-III/2", "nejasne", "odmitnout"]}


@router.get("/capabilities")
async def capabilities():
    return {"protocolVersion": PROTOCOL_VERSION, "humanInTheLoop": {"supported": True, "approvals": True, "interrupts": True, "feedback": False, "approveWithEdits": False},
            "multiAgent": {"subagents": True}, "state": {"snapshots": True}, "transport": "sse", "threads": "zakazka", "auth": "keycloak-bearer"}
