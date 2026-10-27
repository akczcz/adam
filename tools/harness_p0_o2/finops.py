"""
finops.py – cena a strop zakázky (P2-6): útrata zakázky = součet útraty jejích klíčů gateway (role × zakázka) z tabulky `budget_usage`,
kterou vede agentgateway (config.database, Flexible Server; čítače flushuje periodicky → eventually consistent). Gateway zná jen rozpočty
per klíč; strop *zakázky* (sdílený napříč rolemi) vynucuje aplikace: před každou rolí `spend(zid) >= budget_usd` → BudgetExceeded
(stejná eskalace jako 429 z gateway: HITL `rozpocet`, timeout → pauza). Cena zakázky jde do registru `org.zakazky` (metriky.md T12).

Env: P0_FINOPS_DSN (DB agentgateway), P0_REGISTRY_DSN (DB org). Bez nich = kind/P0: spend() vrací None a aplikace padá zpět na usage SDK.
"""
from __future__ import annotations

import os
import time

NANO = 1e9   # agentgateway ukládá USD v nanodolarech, okna v ms (harness O-2 B3)
CAP_BUDGET = "zakazka-30d-block"   # P3-6 (E3): druhý rozpočet každého klíče = strop zakázky; tentýž request se počítá do obou → útrata jen z rozpočtu role


def is_role_usage(budget_id: str, window: str = "30d") -> bool:
    """Řádek budget_usage rozpočtu ROLE (`<role>-<window>-block`), ne stropu zakázky (`zakazka-30d-block`, P3-6 E3) – nález E4: ledger z gateway
    ukázal, že součet všech `-30d-block` řádků klíče počítal každý request dvakrát."""
    return budget_id.endswith(f"-{window}-block") and not budget_id.endswith(CAP_BUDGET)


def _conn(dsn_env):
    dsn = os.environ.get(dsn_env)
    if not dsn: return None
    import psycopg
    return psycopg.connect(dsn, autocommit=True, connect_timeout=5)


def spend(zid: str, key_hashes: dict[str, str], window: str = "30d") -> dict | None:
    """{total_usd, by_role, window, rows} ze součtu `used_amount` budgetu `<role>-<window>-block` všech klíčů zakázky; None bez DSN."""
    c = _conn("P0_FINOPS_DSN")
    if c is None or not key_hashes: return None
    try:
        rows = c.execute("SELECT budget_id, used_amount, unit FROM budget_usage").fetchall()
    finally: c.close()
    by_role = {}
    for role, h in key_hashes.items():
        used = [u for bid, u, unit in rows if h in bid and is_role_usage(bid, window) and unit == "USD"]
        by_role[role] = round(sum(used) / NANO, 6)
    return {"total_usd": round(sum(by_role.values()), 6), "by_role": by_role, "window": window, "rows": len(rows), "ts": time.time()}


DDL_ZAKAZKY = """
CREATE SCHEMA IF NOT EXISTS org;
CREATE TABLE IF NOT EXISTS org.zakazky (
  zakazka_id text PRIMARY KEY, tenant_id text NOT NULL, budget_usd numeric NOT NULL, spent_usd numeric NOT NULL DEFAULT 0,
  spent_by_role jsonb, spend_source text, status text NOT NULL, keys_source text, key_hashes jsonb,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
"""


DDL_TENANTS = """
CREATE SCHEMA IF NOT EXISTS org;
CREATE TABLE IF NOT EXISTS org.tenants (
  tenant_id text PRIMARY KEY, name text NOT NULL, profile text NOT NULL DEFAULT 'standard', budget_usd numeric NOT NULL DEFAULT 0,
  spent_usd numeric NOT NULL DEFAULT 0, role_pods boolean NOT NULL DEFAULT false, namespace text, status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
"""
DDL_GOVERNANCE = """
CREATE SCHEMA IF NOT EXISTS org;
CREATE TABLE IF NOT EXISTS org.role_definitions (
  role_id text NOT NULL, version text NOT NULL, yaml jsonb NOT NULL, yaml_sha256 text NOT NULL, git_commit text NOT NULL,
  approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL CHECK (status IN ('proposed','evaluated','active','suspended','retired')), PRIMARY KEY (role_id, version));
CREATE TABLE IF NOT EXISTS org.agents (
  agent_id text PRIMARY KEY, tenant_id text NOT NULL, role_id text NOT NULL, role_version text NOT NULL, zakazka_id text,
  process_id text NOT NULL, workflow_instance text NOT NULL, model text NOT NULL, model_version text, prompt_version text NOT NULL,
  policy_bundle_rev text NOT NULL, gateway_key_id text NOT NULL, sandbox_profile text NOT NULL, image_digest text,
  node text, runtime_class text, started_at timestamptz, finished_at timestamptz, exit_code int, cost_usd numeric, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS org.agent_events (
  event_id bigserial PRIMARY KEY, agent_id text, role_id text, role_version text, tenant_id text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('created','suspended','resumed','autonomy_changed','retired','violation_A','violation_B')),
  reason text NOT NULL, evidence_ref jsonb, actor text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), signature text NOT NULL DEFAULT '-');
CREATE TABLE IF NOT EXISTS org.role_autonomy (
  role_id text NOT NULL, tenant_id text NOT NULL, level text NOT NULL CHECK (level IN ('A0','A1','A2','A3')),
  changed_by text NOT NULL, reason text NOT NULL, changed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (role_id, tenant_id));
CREATE TABLE IF NOT EXISTS org.risk_register (
  risk_id text PRIMARY KEY, tenant_id text NOT NULL, use_case_id text NOT NULL,
  ai_act_class text NOT NULL CHECK (ai_act_class IN ('minimal','limited','annex_iii_2','annex_iii_4','other_high')),
  category text NOT NULL, description text NOT NULL, likelihood smallint NOT NULL CHECK (likelihood BETWEEN 1 AND 5), impact smallint NOT NULL CHECK (impact BETWEEN 1 AND 5),
  controls jsonb NOT NULL, evidence_ref jsonb, owner text NOT NULL, status text NOT NULL CHECK (status IN ('open','mitigated','accepted','closed')),
  review_at date NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
"""
RLS_TABLES = ("tenants", "zakazky", "approvals", "agents", "agent_events", "role_autonomy", "risk_register", "sla_events")   # tabulky s tenant_id (role_definitions/eval_gates jsou globální)
AUTONOMY_ORDER = ["A0", "A1", "A2", "A3"]
# metriky.md §6 – podmínka vstupu (per role × tenant); v0 strop A2, A3 jen po v0 (rozhodnutí v0: člověk zůstává u nevratných kroků)
AUTONOMY_RULES = {"A1": {"min_tasks": 10, "max_reject_rate": 0.2}, "A2": {"min_tasks": 30, "max_reject_rate": 0.10, "eval_layers": ("L2",), "no_violation_A": True}, "A3": {"min_tasks": 100, "max_reject_rate": 0.10, "eval_layers": ("L2",), "no_violation_A": True, "blocked": "A3 až po v0 (autonomie.md: strop v0 = A2)"}}


def autonomy_check(c, role: str, tenant: str, target: str) -> dict:
    """Metriky z org.* pro posun autonomie role × tenant (metriky.md §6): počet úkolů (org.agents), podíl HITL odmítnutí (org.approvals), eval gate L2
    (org.eval_gates poslední verze), žádné porušení třídy A (org.agent_events). Vrací {ok, current, target, metrics, reasons}; posun dolů je vždy ok."""
    cur = (c.execute("SELECT level FROM org.role_autonomy WHERE role_id = %s AND tenant_id = %s", (role, tenant)).fetchone() or ["A0"])[0]
    if target not in AUTONOMY_ORDER: return {"ok": False, "current": cur, "target": target, "reasons": ["neznámá úroveň"], "metrics": {}}
    tasks = c.execute("SELECT count(*) FROM org.agents WHERE role_id = %s AND tenant_id = %s", (role, tenant)).fetchone()[0]
    ap = c.execute("SELECT decision, count(*) FROM org.approvals WHERE tenant_id = %s GROUP BY decision", (tenant,)).fetchall(); apd = {d: n for d, n in ap}
    rej = apd.get("reject", 0) / max(1, apd.get("approve", 0) + apd.get("reject", 0))
    viol = c.execute("SELECT count(*) FROM org.agent_events WHERE role_id = %s AND tenant_id = %s AND kind = 'violation_A'", (role, tenant)).fetchone()[0]
    gates = {r[0]: r[1] for r in c.execute("SELECT DISTINCT ON (layer) layer, passed FROM org.eval_gates WHERE role_id = %s ORDER BY layer, evaluated_at DESC", (role,)).fetchall()} if c.execute("SELECT to_regclass('org.eval_gates') IS NOT NULL").fetchone()[0] else {}
    amax = (c.execute("SELECT yaml->>'autonomy_max' FROM org.role_definitions WHERE role_id = %s ORDER BY version DESC LIMIT 1", (role,)).fetchone() or [None])[0] if c.execute("SELECT to_regclass('org.role_definitions') IS NOT NULL").fetchone()[0] else None
    metrics = {"tasks": tasks, "reject_rate": round(rej, 3), "approvals": apd, "violations_A": viol, "eval_gates": gates, "autonomy_max": amax}
    reasons = []
    if AUTONOMY_ORDER.index(target) <= AUTONOMY_ORDER.index(cur): return {"ok": True, "current": cur, "target": target, "metrics": metrics, "reasons": [], "direction": "down" if target != cur else "same"}
    if AUTONOMY_ORDER.index(target) - AUTONOMY_ORDER.index(cur) > 1: reasons.append(f"posun jen o jednu úroveň ({cur} → {AUTONOMY_ORDER[AUTONOMY_ORDER.index(cur) + 1]})")
    if amax and AUTONOMY_ORDER.index(target) > AUTONOMY_ORDER.index(amax): reasons.append(f"nad autonomy_max role ({amax})")
    rule = AUTONOMY_RULES.get(target, {})
    if rule.get("blocked"): reasons.append(rule["blocked"])
    if tasks < rule.get("min_tasks", 0): reasons.append(f"úkolů {tasks} < {rule['min_tasks']}")
    if rej > rule.get("max_reject_rate", 1): reasons.append(f"HITL odmítnutí {rej:.0%} > {rule['max_reject_rate']:.0%}")
    for l in rule.get("eval_layers", ()):
        if not gates.get(l): reasons.append(f"eval gate {l} neprošel nebo chybí")
    if rule.get("no_violation_A") and viol: reasons.append(f"porušení třídy A: {viol}")
    try:   # P3-4 (T9): high-risk profil zamyká posun autonomie (autonomie.md: pravidlo pass^k vypnuto) – zakázky tenanta s profilem přílohy III
        hr = c.execute("SELECT count(*) FROM org.zakazky WHERE tenant_id = %s AND profile = ANY(%s) AND status NOT IN ('Dokonceno','Zamitnuto','Odmitnuto')", (tenant, list(HIGH_RISK))).fetchone()[0]
        metrics["high_risk_zakazky"] = hr
        if hr: reasons.append(f"high-risk profil (příloha III) u {hr} zakázek tenanta – posun autonomie zamčen (T9)")
    except Exception: pass
    return {"ok": not reasons, "current": cur, "target": target, "metrics": metrics, "reasons": reasons, "direction": "up"}


def autonomy_set(role: str, tenant: str, target: str, *, by: str, reason: str) -> dict:
    """Posun autonomie role × tenant: nahoru jen při splněných podmínkách (autonomy_check), dolů vždy; řádek org.role_autonomy + org.agent_events autonomy_changed."""
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return {"ok": False, "reasons": ["bez DSN"]}
    try:
        c.execute(DDL_GOVERNANCE)
        chk = autonomy_check(c, role, tenant, target)
        if not chk["ok"]: return chk
        c.execute("""INSERT INTO org.role_autonomy (role_id, tenant_id, level, changed_by, reason) VALUES (%s, %s, %s, %s, %s)
                     ON CONFLICT (role_id, tenant_id) DO UPDATE SET level = EXCLUDED.level, changed_by = EXCLUDED.changed_by, reason = EXCLUDED.reason, changed_at = now()""", (role, tenant, target, by, reason))
        import json
        c.execute("INSERT INTO org.agent_events (role_id, tenant_id, kind, reason, evidence_ref, actor) VALUES (%s, %s, 'autonomy_changed', %s, %s::jsonb, %s)", (role, tenant, f"{chk['current']} → {target}: {reason}", json.dumps(chk["metrics"], default=str), by))
        return chk | {"written": True}
    except Exception as e:
        return {"ok": False, "reasons": [f"{type(e).__name__}: {str(e)[:200]}"]}
    finally: c.close()


def agent_insert(zid: str, *, tenant: str, role: str, version: str, process: str, model: str, pod: dict, run: dict, opa_rev: str, key_id: str, sandbox_profile: str) -> bool:
    """P3-3 (uzavírá otevřenou položku P2): řádek org.agents píše workflow po každém běhu role (dřív harness). agent_id = SPIFFE ID role per běh."""
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return False
    try:
        c.execute(DDL_GOVERNANCE)
        agent_id = f"spiffe://platform/role/{role}/{tenant}/{zid}/{(pod.get('pod') or 'local').rsplit('-', 1)[-1]}"
        c.execute("""INSERT INTO org.agents (agent_id, tenant_id, role_id, role_version, zakazka_id, process_id, workflow_instance, model, prompt_version, policy_bundle_rev,
                                             gateway_key_id, sandbox_profile, image_digest, node, runtime_class, exit_code, cost_usd)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (agent_id) DO NOTHING""",
                  (agent_id, tenant, role, version, zid, process, zid, model, version, opa_rev, key_id, sandbox_profile, pod.get("image"), pod.get("node"), pod.get("runtime_class"), pod.get("exit_code"), run.get("cost_usd")))
        c.execute("INSERT INTO org.agent_events (agent_id, role_id, role_version, tenant_id, kind, reason, actor) VALUES (%s, %s, %s, %s, 'created', %s, 'workflow')", (agent_id, role, version, tenant, f"běh role v zakázce {zid}"))
        return True
    except Exception:
        return False
    finally: c.close()


DDL_P34 = """
ALTER TABLE org.zakazky ADD COLUMN IF NOT EXISTS profile text;
ALTER TABLE org.zakazky ADD COLUMN IF NOT EXISTS klasifikace jsonb;
CREATE TABLE IF NOT EXISTS org.sla_events (
  event_id bigserial PRIMARY KEY, tenant_id text NOT NULL, zakazka_id text NOT NULL, process_id text NOT NULL, bod text NOT NULL,
  sla_s numeric NOT NULL, elapsed_s numeric NOT NULL, escalated_to text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
"""
HIGH_RISK = ("high-risk-III/4", "high-risk-III/2", "nejasne")   # autonomie.md: nejasne se do stanoviska bere jako high-risk


def zakazka_classify(zid: str, *, tenant: str, profile: str, answers: dict, by: str, reason: str, budget_usd: float) -> bool:
    """P3-4 (T9, T15): profil rizika zakázky do org.zakazky (+ odpovědi K1–K6) a auditní řádek org.approvals (action zadani.classify)."""
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return False
    try:
        import json
        c.execute(DDL_ZAKAZKY); c.execute(DDL_APPROVALS); c.execute(DDL_P34)
        c.execute("""INSERT INTO org.zakazky (zakazka_id, tenant_id, budget_usd, status, profile, klasifikace) VALUES (%s, %s, %s, 'Running', %s, %s::jsonb)
                     ON CONFLICT (zakazka_id) DO UPDATE SET profile = EXCLUDED.profile, klasifikace = EXCLUDED.klasifikace, updated_at = now()""", (zid, tenant, budget_usd, profile, json.dumps(answers)))
        c.execute("""INSERT INTO org.approvals (approval_id, tenant_id, workflow_instance, process_id, action, artifact_ref, artifact_sha, approver, decision, reason, limits_shown, expires_at, signature, channel)
                     VALUES (%s, %s, %s, 'P1a', 'zadani.classify', %s, %s, %s, %s, %s, %s::jsonb, now(), '-', 'agui')""",
                  (__import__("uuid").uuid4().hex, tenant, zid, f"klasifikace://{zid}", profile, by, "reject" if profile == "odmitnout" else "approve", reason, json.dumps(answers)))
        return True
    except Exception:
        return False
    finally: c.close()


def sla_event(zid: str, *, tenant: str, process: str, bod: str, sla_s: float, elapsed_s: float, escalated_to: str) -> bool:
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return False
    try:
        c.execute(DDL_P34)
        c.execute("INSERT INTO org.sla_events (tenant_id, zakazka_id, process_id, bod, sla_s, elapsed_s, escalated_to) VALUES (%s, %s, %s, %s, %s, %s, %s)", (tenant, zid, process, bod, sla_s, elapsed_s, escalated_to))
        return True
    except Exception:
        return False
    finally: c.close()


def tenant_status(tenant: str, status: str, *, by: str, reason: str) -> bool:
    """Stop/resume tenanta (autonomie.md T5): org.tenants.status + org.agent_events suspended/resumed per tenant."""
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return False
    try:
        c.execute(DDL_TENANTS); c.execute(DDL_GOVERNANCE)
        c.execute("UPDATE org.tenants SET status = %s, updated_at = now() WHERE tenant_id = %s", (status, tenant))
        c.execute("INSERT INTO org.agent_events (tenant_id, kind, reason, actor) VALUES (%s, %s, %s, %s)", (tenant, "suspended" if status == "stopped" else "resumed", reason, by))
        return True
    except Exception:
        return False
    finally: c.close()


def tenant_is_stopped(tenant: str) -> bool | None:
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return None
    try:
        r = c.execute("SELECT status FROM org.tenants WHERE tenant_id = %s", (tenant,)).fetchone(); return bool(r and r[0] == "stopped")
    except Exception: return None
    finally: c.close()
RLS_SQL = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'org_reader') THEN CREATE ROLE org_reader LOGIN PASSWORD 'org_reader'; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'org_writer') THEN CREATE ROLE org_writer LOGIN PASSWORD 'org_writer'; END IF;
END $$;
GRANT USAGE ON SCHEMA org TO org_reader, org_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA org TO org_reader;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA org TO org_writer;
"""
RLS_POLICY = """
ALTER TABLE org.{t} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON org.{t};
CREATE POLICY tenant_isolation ON org.{t}
  USING (tenant_id = current_setting('app.tenant_id', true) OR current_setting('app.tenant_id', true) = 'platform')
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true) OR current_setting('app.tenant_id', true) = 'platform');
"""


def tenants_sync(tenants: list[dict]) -> dict:
    """P3-2: org.tenants z Gitu (rolegen tenants.json v ConfigMapě) + RLS per tenant_id na org.* (role org_reader/org_writer; tenant `platform` = průřez).
    Vlastník schématu (DSN aplikace) RLS nepodléhá – aplikace píše za všechny tenanty, čte je Governance MCP jako org_reader (P3-3)."""
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return {"written": False}
    try:
        c.execute(DDL_TENANTS); c.execute(DDL_ZAKAZKY); c.execute(DDL_APPROVALS); c.execute(DDL_GOVERNANCE); c.execute(DDL_P34)   # P3-4: profile/klasifikace, org.sla_events
        for t in tenants:
            c.execute("""INSERT INTO org.tenants (tenant_id, name, profile, budget_usd, role_pods, namespace) VALUES (%s, %s, %s, %s, %s, %s)
                         ON CONFLICT (tenant_id) DO UPDATE SET name = EXCLUDED.name, profile = EXCLUDED.profile, budget_usd = EXCLUDED.budget_usd, role_pods = EXCLUDED.role_pods, namespace = EXCLUDED.namespace, updated_at = now()""",
                      (t["id"], t.get("name") or t["id"], t.get("profile", "standard"), t.get("budget_usd", 0), bool(t.get("role_pods")), t.get("namespace")))
        c.execute(RLS_SQL)
        for t in RLS_TABLES: c.execute(RLS_POLICY.format(t=t))
        return {"written": True, "tenants": [t["id"] for t in tenants], "rls": list(RLS_TABLES)}
    except Exception as e:
        return {"written": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    finally: c.close()


def tenant_spend(tenant: str) -> dict | None:
    """Útrata tenanta = součet spent_usd jeho zakázek v org.zakazky (30d okno klíčů) + strop z org.tenants; None bez DSN."""
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return None
    try:
        c.execute(DDL_TENANTS); c.execute(DDL_ZAKAZKY)
        row = c.execute("SELECT COALESCE(SUM(spent_usd), 0) FROM org.zakazky WHERE tenant_id = %s", (tenant,)).fetchone()
        lim = c.execute("SELECT budget_usd FROM org.tenants WHERE tenant_id = %s", (tenant,)).fetchone()
        c.execute("UPDATE org.tenants SET spent_usd = %s, updated_at = now() WHERE tenant_id = %s", (float(row[0]), tenant))
        return {"tenant": tenant, "spent_usd": float(row[0]), "budget_usd": float(lim[0]) if lim else None}
    except Exception:
        return None
    finally: c.close()


DDL_APPROVALS = """
CREATE SCHEMA IF NOT EXISTS org;
CREATE TABLE IF NOT EXISTS org.approvals (
  approval_id        text PRIMARY KEY,
  tenant_id          text NOT NULL,
  workflow_instance  text NOT NULL,
  process_id         text NOT NULL,
  action             text NOT NULL,
  artifact_ref       text NOT NULL,
  artifact_sha       text NOT NULL,
  requested_by_agent text,
  approver           text NOT NULL,
  decision           text NOT NULL CHECK (decision IN ('approve','reject','override')),
  reason             text NOT NULL CHECK (length(reason) >= 10),
  limits_shown       jsonb,
  decided_at         timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL,
  signature          text NOT NULL,
  channel            text);
"""
BOD_PROCESS = {"H1": "P1", "H1a": "P1", "H2": "P2", "H4": "P4", "H5": "P5", "rozpocet": "X2"}
BOD_ACTION = {"H1": "zadani.accept", "H1a": "pravnik.stanovisko", "H2": "navrh.accept", "H4": "pr.merge", "H5": "deploy.apply", "rozpocet": "budget.raise"}   # metriky.md org.approvals.action


def approval_insert(zid: str, *, tenant: str, bod: str, action: str, artifact_sha: str, approver: str, decision: str, reason: str, expires_at: float, signature: str, channel: str, limits_shown: dict | None = None, artifact_ref: str | None = None) -> bool:
    """Append-only záznam rozhodnutí člověka (metriky.md org.approvals, T6: důvod ≥ 10 znaků vynucuje i DB). False bez DSN nebo při chybě."""
    import json, uuid, datetime as dt
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return False
    try:
        c.execute(DDL_APPROVALS)
        c.execute("""INSERT INTO org.approvals (approval_id, tenant_id, workflow_instance, process_id, action, artifact_ref, artifact_sha, approver, decision, reason, limits_shown, expires_at, signature, channel)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)""",
                  (uuid.uuid4().hex, tenant, zid, BOD_PROCESS.get(bod, bod), BOD_ACTION.get(bod, action), artifact_ref or f"{bod}://{zid}", artifact_sha or "-", approver, decision, reason, json.dumps(limits_shown or {}), dt.datetime.fromtimestamp(expires_at, dt.timezone.utc), signature, channel))
        return True
    except Exception:
        return False
    finally: c.close()


def registry_upsert(zid: str, *, tenant: str, budget_usd: float, spent: dict | None, status: str, keys_source: str | None, key_hashes: dict | None) -> bool:
    """Řádek zakázky v registru org.zakazky (cena zakázky čitelná z jedné tabulky). False bez DSN nebo při chybě (ledger rozhodne, co s tím)."""
    import json
    c = _conn("P0_REGISTRY_DSN")
    if c is None: return False
    try:
        c.execute(DDL_ZAKAZKY)
        c.execute("""INSERT INTO org.zakazky (zakazka_id, tenant_id, budget_usd, spent_usd, spent_by_role, spend_source, status, keys_source, key_hashes)
                     VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)
                     ON CONFLICT (zakazka_id) DO UPDATE SET spent_usd = EXCLUDED.spent_usd, spent_by_role = EXCLUDED.spent_by_role, spend_source = EXCLUDED.spend_source, budget_usd = EXCLUDED.budget_usd,
                       status = EXCLUDED.status, keys_source = COALESCE(EXCLUDED.keys_source, org.zakazky.keys_source), key_hashes = COALESCE(EXCLUDED.key_hashes, org.zakazky.key_hashes), updated_at = now()""",
                  (zid, tenant, budget_usd, (spent or {}).get("total_usd", 0.0), json.dumps((spent or {}).get("by_role") or {}), "budget_usage" if spent else "sdk_usage", status, keys_source, json.dumps(key_hashes or {})))
        return True
    except Exception:
        return False
    finally: c.close()
