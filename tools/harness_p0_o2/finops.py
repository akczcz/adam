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
