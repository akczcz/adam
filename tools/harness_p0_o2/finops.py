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
        used = [u for bid, u, unit in rows if h in bid and bid.endswith(f"-{window}-block") and unit == "USD"]
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
RLS_TABLES = ("tenants", "zakazky", "approvals")   # org.agents/role_definitions/eval_gates zakládá tools/role_evals/registry.py (agents má tenant_id – přidá se tam)
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
        c.execute(DDL_TENANTS); c.execute(DDL_ZAKAZKY); c.execute(DDL_APPROVALS)
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
                     ON CONFLICT (zakazka_id) DO UPDATE SET spent_usd = EXCLUDED.spent_usd, spent_by_role = EXCLUDED.spent_by_role, spend_source = EXCLUDED.spend_source,
                       status = EXCLUDED.status, keys_source = COALESCE(EXCLUDED.keys_source, org.zakazky.keys_source), key_hashes = COALESCE(EXCLUDED.key_hashes, org.zakazky.key_hashes), updated_at = now()""",
                  (zid, tenant, budget_usd, (spent or {}).get("total_usd", 0.0), json.dumps((spent or {}).get("by_role") or {}), "budget_usage" if spent else "sdk_usage", status, keys_source, json.dumps(key_hashes or {})))
        return True
    except Exception:
        return False
    finally: c.close()
