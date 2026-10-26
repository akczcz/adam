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
