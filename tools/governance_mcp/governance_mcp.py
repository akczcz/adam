"""
governance_mcp.py – Governance MCP server (P3-3): jen čtení nad schématem `org` (registr rolí a agentů, zakázky, approvaly, události,
risk register, FinOps, governance report, export) pro lidi (GUI přes AG-UI server). Stejný tvar jako server paměti M1: HTTP, `GET /resources`,
`POST /tools/<name>` (JSON args) – MCP-kompatibilní „tenký“ server bez SDK (žádný model ho nevolá; P3-6: plný MCP transport za gateway).

Identita volajícího = Bearer token Keycloaku člověka (JWKS, realm role `human`; agentní token = 403 – registr čtou lidé, ne agenti);
tenant z claimu `tenant_id` → `SET app.tenant_id` v DB (RLS: tenant vidí jen své řádky, `platform` průřez). DB role `org_reader`
(GOV_DSN) – server nemůže nic zapsat ani kdyby chtěl (U2g). Bez JWKS (lokální fixture) HS256 dev tokeny jako AG-UI.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from decimal import Decimal

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()
DSN = os.environ.get("GOV_DSN", "")
JWKS_URL, ISSUER = os.environ.get("GOV_KC_JWKS_URL"), os.environ.get("GOV_KC_ISSUER")
DEV_SECRET = os.environ.get("O1_APPROVAL_SECRET", "o1-transit-key")
_jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=300) if JWKS_URL else None
PLATFORM = "platform"
T_ITEMS = {"T11": "risk register per use case", "T12": "registr agentů (řádek per instance role)", "T13": "nevratné kroky jen po lidském schválení s důvodem", "T14": "žádný trénink (evidence: žádný fine-tune klíč)", "T15": "klasifikace zakázky (profil rizika) a eval gate verze role"}


def user(req: Request) -> dict:
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): raise HTTPException(401, "chybí Bearer token")
    raw = auth[7:].strip()
    try:
        if _jwks:
            c = jwt.decode(raw, _jwks.get_signing_key_from_jwt(raw).key, algorithms=["RS256"], issuer=ISSUER, options={"verify_aud": False, "require": ["exp", "sub", "iss"]})
        else:
            c = jwt.decode(raw, DEV_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except Exception as e:
        raise HTTPException(401, f"neplatný token: {type(e).__name__}")
    roles = c.get("roles") or (c.get("realm_access") or {}).get("roles") or []
    if "human" not in roles: raise HTTPException(403, "governance čtou lidé (realm role human), ne agenti")
    if not c.get("tenant_id"): raise HTTPException(403, "token bez tenant_id")
    return {"sub": c["sub"], "tenant": c["tenant_id"], "roles": roles, "name": c.get("preferred_username") or c["sub"]}


def conn(tenant: str):
    import psycopg
    c = psycopg.connect(DSN, autocommit=True, connect_timeout=5)
    c.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))
    return c


def rows(c, sql, args=()):
    cur = c.execute(sql, args); cols = [d.name for d in cur.description]
    def v(x):
        if isinstance(x, Decimal): return float(x)
        if isinstance(x, (datetime, date)): return x.isoformat()
        return x
    return [dict(zip(cols, map(v, r))) for r in cur.fetchall()]


def table_exists(c, t): return c.execute("SELECT to_regclass(%s) IS NOT NULL", (f"org.{t}",)).fetchone()[0]


TOOLS = {}


def tool(name, desc):
    def deco(f): TOOLS[name] = (desc, f); return f
    return deco


@tool("tenants", "org.tenants: strop a útrata 30d, profil, stav (stopped = stop tenanta)")
def t_tenants(c, u, a): return rows(c, "SELECT tenant_id, name, profile, budget_usd, spent_usd, role_pods, namespace, status, updated_at FROM org.tenants ORDER BY tenant_id")


@tool("zakazky", "org.zakazky: rozpočet, útrata per role, stav, zdroj klíčů; args {status?, limit?}")
def t_zakazky(c, u, a):
    has_profile = c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='org' AND table_name='zakazky' AND column_name='profile'").fetchone() is not None
    q = f"SELECT zakazka_id, tenant_id, budget_usd, spent_usd, spent_by_role, spend_source, status, keys_source, created_at, updated_at{', profile, klasifikace' if has_profile else ''} FROM org.zakazky"   # P3-4: profil rizika (T15)
    args = []
    if a.get("status"): q += " WHERE status = %s"; args.append(a["status"])
    return rows(c, q + " ORDER BY created_at DESC LIMIT %s", (*args, int(a.get("limit", 200))))


@tool("roles", "org.role_definitions + poslední eval gate per vrstva + úroveň autonomie per role × tenant (org.role_autonomy, výchozí A0)")
def t_roles(c, u, a):
    out = rows(c, "SELECT role_id, version, status, yaml_sha256, git_commit, approved_by, approved_at FROM org.role_definitions ORDER BY role_id, version") if table_exists(c, "role_definitions") else []
    gates = rows(c, "SELECT DISTINCT ON (role_id, role_version, layer) role_id, role_version, layer, metric, value, threshold, passed, evaluated_at FROM org.eval_gates ORDER BY role_id, role_version, layer, evaluated_at DESC") if table_exists(c, "eval_gates") else []
    auto = rows(c, "SELECT role_id, tenant_id, level, changed_by, reason, changed_at FROM org.role_autonomy") if table_exists(c, "role_autonomy") else []
    for r in out:
        r["eval_gates"] = [g for g in gates if g["role_id"] == r["role_id"] and g["role_version"] == r["version"]]
        r["autonomy"] = {x["tenant_id"]: {k: x[k] for k in ("level", "changed_by", "reason", "changed_at")} for x in auto if x["role_id"] == r["role_id"]}
        r["autonomy_max"] = ((c.execute("SELECT yaml->>'autonomy_max' FROM org.role_definitions WHERE role_id = %s AND version = %s", (r["role_id"], r["version"])).fetchone() or [None])[0])
    return out


@tool("agents", "org.agents: instance rolí (SPIFFE ID per běh, klíč, obraz, uzel, cena); args {zakazka_id?, role_id?, limit?}")
def t_agents(c, u, a):
    if not table_exists(c, "agents"): return []
    q = "SELECT agent_id, tenant_id, role_id, role_version, zakazka_id, process_id, model, gateway_key_id, sandbox_profile, image_digest, node, runtime_class, exit_code, cost_usd, created_at FROM org.agents WHERE true"; args = []
    if a.get("zakazka_id"): q += " AND zakazka_id = %s"; args.append(a["zakazka_id"])
    if a.get("role_id"): q += " AND role_id = %s"; args.append(a["role_id"])
    return rows(c, q + " ORDER BY created_at DESC LIMIT %s", (*args, int(a.get("limit", 200))))


@tool("approvals", "org.approvals: rozhodnutí lidí s důvodem (T6); args {zakazka_id?, limit?}")
def t_approvals(c, u, a):
    q = "SELECT approval_id, tenant_id, workflow_instance, process_id, action, artifact_sha, approver, decision, reason, channel, decided_at, expires_at FROM org.approvals WHERE true"; args = []
    if a.get("zakazka_id"): q += " AND workflow_instance = %s"; args.append(a["zakazka_id"])
    return rows(c, q + " ORDER BY decided_at DESC LIMIT %s", (*args, int(a.get("limit", 200))))


@tool("agent_events", "org.agent_events: pozastavení, změna autonomie, porušení (append-only); args {limit?}")
def t_events(c, u, a):
    if not table_exists(c, "agent_events"): return []
    return rows(c, "SELECT event_id, agent_id, role_id, role_version, tenant_id, kind, reason, evidence_ref, actor, created_at FROM org.agent_events ORDER BY created_at DESC LIMIT %s", (int(a.get("limit", 200)),))


@tool("risk_register", "org.risk_register (T11) – per tenant / use case")
def t_risks(c, u, a):
    if not table_exists(c, "risk_register"): return []
    return rows(c, "SELECT risk_id, tenant_id, use_case_id, ai_act_class, category, description, likelihood, impact, controls, owner, status, review_at, updated_at FROM org.risk_register ORDER BY tenant_id, risk_id")


@tool("sla_events", "SLA bodů (procesy.md, P3-4): překročení lhůt HITL bodů per zakázka s eskalací (org.sla_events)")
def t_sla(c, u, a):
    if not table_exists(c, "sla_events"): return []
    return rows(c, "SELECT event_id, tenant_id, zakazka_id, process_id, bod, sla_s, elapsed_s, escalated_to, created_at FROM org.sla_events ORDER BY created_at DESC LIMIT %s", (int(a.get("limit", 200)),))


@tool("finops", "FinOps: per tenant strop vs. útrata 30d (alert ≥ 80 %), per zakázka útrata a per role")
def t_finops(c, u, a):
    ten = rows(c, "SELECT tenant_id, budget_usd, spent_usd, status FROM org.tenants ORDER BY tenant_id")
    for t in ten:
        t["pct"] = round(100 * t["spent_usd"] / t["budget_usd"], 1) if t["budget_usd"] else None; t["alert"] = bool(t["budget_usd"]) and t["spent_usd"] >= 0.8 * t["budget_usd"]
    z = rows(c, "SELECT zakazka_id, tenant_id, budget_usd, spent_usd, spent_by_role, status FROM org.zakazky ORDER BY created_at DESC LIMIT 100")
    for r in z:
        r["pct"] = round(100 * r["spent_usd"] / r["budget_usd"], 1) if r["budget_usd"] else None; r["alert"] = bool(r["budget_usd"]) and r["spent_usd"] >= 0.8 * r["budget_usd"]
    by_role = {}
    for r in z:
        for role, v in (r.get("spent_by_role") or {}).items(): by_role[role] = round(by_role.get(role, 0) + float(v or 0), 6)
    return {"tenants": ten, "zakazky": z, "by_role": by_role, "window": "30d", "source": "org.zakazky.spent_usd (budget_usage gateway)"}


@tool("governance_report", "Týdenní governance report (metriky.md §5): úplnost T11–T15 per zakázka a role, rozpočty, pozastavení")
def t_report(c, u, a):
    z = rows(c, "SELECT zakazka_id, tenant_id, status, budget_usd, spent_usd, created_at FROM org.zakazky ORDER BY created_at DESC LIMIT 500")
    has_profile = c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='org' AND table_name='zakazky' AND column_name='profile'").fetchone() is not None
    prof = {r["zakazka_id"]: r["profile"] for r in rows(c, "SELECT zakazka_id, profile FROM org.zakazky")} if has_profile else {}
    agents = rows(c, "SELECT zakazka_id, count(*) AS n FROM org.agents GROUP BY zakazka_id") if table_exists(c, "agents") else []
    n_agents = {r["zakazka_id"]: r["n"] for r in agents}
    apr = rows(c, "SELECT workflow_instance, action, decision FROM org.approvals")
    risks = rows(c, "SELECT tenant_id, count(*) AS n FROM org.risk_register GROUP BY tenant_id") if table_exists(c, "risk_register") else []
    n_risks = {r["tenant_id"]: r["n"] for r in risks}
    gates = rows(c, "SELECT role_id, role_version, bool_and(passed) AS ok, count(*) AS n FROM org.eval_gates GROUP BY role_id, role_version") if table_exists(c, "eval_gates") else []
    roles_ok = {(g["role_id"], g["role_version"]): g["ok"] for g in gates}
    rd = rows(c, "SELECT role_id, version, status FROM org.role_definitions") if table_exists(c, "role_definitions") else []
    items = []
    for r in z:
        missing = []
        if not prof.get(r["zakazka_id"]): missing.append("T15:klasifikace")
        if not n_agents.get(r["zakazka_id"]): missing.append("T12:registr_agentu")
        if r["status"] == "Dokonceno":
            acts = {x["action"] for x in apr if x["workflow_instance"] == r["zakazka_id"] and x["decision"] == "approve"}
            for need in ("pr.merge", "deploy.apply"):
                if need not in acts and not ({"merge", "deploy"} & acts): missing.append(f"T13:{need}")
        if not n_risks.get(r["tenant_id"]): missing.append("T11:risk_register")
        items.append({"zakazka_id": r["zakazka_id"], "tenant_id": r["tenant_id"], "status": r["status"], "missing": missing, "spent_usd": r["spent_usd"], "budget_usd": r["budget_usd"]})
    role_items = [{"role_id": x["role_id"], "version": x["version"], "status": x["status"], "eval_gate": roles_ok.get((x["role_id"], x["version"]))} for x in rd]
    n_missing = sum(1 for i in items if i["missing"])
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tenant_view": u["tenant"], "zakazky": items, "roles": role_items, "summary": {"zakazky": len(items), "with_gaps": n_missing, "complete": len(items) - n_missing, "t_items": T_ITEMS}}


CH_URL = os.environ.get("GOV_CLICKHOUSE_URL", "")   # P3-6 E4: spany agentgateway (per request: tenant, zakázka, role, llm.cost.total) v ClickHouse


def clickhouse(sql: str, params: dict) -> list[dict]:
    import httpx
    r = httpx.post(CH_URL.rstrip("/") + "/", params={f"param_{k}": v for k, v in params.items()}, content=sql, timeout=30)
    if r.status_code != 200: raise HTTPException(502, f"ClickHouse: {r.text[:200]}")
    return [json.loads(l) for l in r.text.splitlines() if l.strip()]


@tool("ledger", "Per-request ledger z gateway (P3-6 E4): spany agentgateway v ClickHouse – requesty, tokeny a cena per tenant/zakázka/role za N dní, nezávisle na budget_usage; rozdíl proti org.zakazky.spent_usd")
def t_ledger(c, u, a):
    if not CH_URL: return {"rows": [], "by_zakazka": [], "error": "GOV_CLICKHOUSE_URL není nastaven"}
    days = int(a.get("days", 30)); params = {"days": days}
    q = ("SELECT SpanAttributes['tenant'] AS tenant_id, SpanAttributes['zakazka'] AS zakazka_id, SpanAttributes['role'] AS role, count() AS requests, "
         "round(sum(toFloat64OrZero(SpanAttributes['llm.cost.total'])), 6) AS cost_usd, sum(toUInt64OrZero(SpanAttributes['gen_ai.usage.input_tokens'])) AS input_tokens, "
         "sum(toUInt64OrZero(SpanAttributes['gen_ai.usage.output_tokens'])) AS output_tokens, toString(min(Timestamp)) AS first, toString(max(Timestamp)) AS last "
         "FROM otel.otel_traces WHERE SpanAttributes['zakazka'] != '' AND Timestamp > now() - INTERVAL {days:UInt32} DAY")
    if u["tenant"] != "platform": q += " AND SpanAttributes['tenant'] = {tenant:String}"; params["tenant"] = u["tenant"]   # stejná hranice jako RLS org.*: jen vlastní tenant
    q += " GROUP BY tenant_id, zakazka_id, role ORDER BY last DESC LIMIT 1000 FORMAT JSONEachRow"
    rws = clickhouse(q, params)
    spent = {r["zakazka_id"]: (float(r["spent_usd"] or 0), r["status"]) for r in rows(c, "SELECT zakazka_id, spent_usd, status FROM org.zakazky")}   # RLS org_reader
    by_z = {}
    for r in rws:
        z = by_z.setdefault(r["zakazka_id"], {"zakazka_id": r["zakazka_id"], "tenant_id": r["tenant_id"], "requests": 0, "ledger_usd": 0.0, "roles": {}})
        z["requests"] += int(r["requests"]); z["ledger_usd"] = round(z["ledger_usd"] + float(r["cost_usd"]), 6); z["roles"][r["role"]] = float(r["cost_usd"])
    for z in by_z.values():
        sp = spent.get(z["zakazka_id"]); z["spent_usd"] = sp[0] if sp else None; z["status"] = sp[1] if sp else None
        z["delta_usd"] = round(z["ledger_usd"] - sp[0], 6) if sp else None
    by_t = {}
    for z in by_z.values(): by_t[z["tenant_id"]] = round(by_t.get(z["tenant_id"], 0.0) + z["ledger_usd"], 6)
    return {"rows": rws, "by_zakazka": sorted(by_z.values(), key=lambda x: x["zakazka_id"], reverse=True), "by_tenant": by_t, "window_days": days, "source": "agentgateway spany (tracing fields tenant/zakazka/role/llm.cost.total) → OTEL Collector → ClickHouse otel.otel_traces"}


@tool("export", "Export JSONL všech viditelných řádků org.* pro deployera (čl. 13(3)(f)) – RLS vrací jen tenant volajícího")
def t_export(c, u, a):
    out = []
    for t in ("tenants", "zakazky", "approvals", "agents", "agent_events", "risk_register", "role_autonomy", "sla_events"):
        if not table_exists(c, t): continue
        for r in rows(c, f"SELECT * FROM org.{t}"): out.append({"table": t, **r})
    return out


@app.get("/resources")
async def resources(req: Request):
    user(req); return {"tools": [{"name": n, "description": d} for n, (d, _) in TOOLS.items()], "read_only": True, "db_role": "org_reader"}


@app.post("/tools/{name}")
async def call(name: str, req: Request):
    u = user(req)
    if name not in TOOLS: raise HTTPException(404, "neznámý nástroj")
    try: args = await req.json()
    except Exception: args = {}
    c = conn(u["tenant"])
    try: return {"tenant": u["tenant"], "result": TOOLS[name][1](c, u, args or {})}
    finally: c.close()


@app.get("/export.jsonl", response_class=PlainTextResponse)
async def export_jsonl(req: Request):
    u = user(req); c = conn(u["tenant"])
    try: return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in t_export(c, u, {})) + "\n"
    finally: c.close()


@app.get("/health")
async def health(): return {"ok": True, "dsn": bool(DSN)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("GOV_HOST", "0.0.0.0"), port=int(os.environ.get("GOV_PORT", "9910")), log_level="warning")
