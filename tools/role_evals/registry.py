"""
registry.py – registr rolí a agentů (P2-5, knowledge/organization/metriky.md: org.role_definitions, org.eval_gates, org.agents) v databázi `org`.
Plní ho harness/CI z Gitu (definice rolí, výsledky evalů) a z ledgeru aplikace (instance rolí v zakázce). Schéma = podmnožina
sloupců z metriky.md (idempotentní CREATE IF NOT EXISTS); plná verze s FK a dalšími tabulkami přijde s Dapr workflow zápisem (P3).
"""
from __future__ import annotations

import hashlib
import json

DDL = """
CREATE SCHEMA IF NOT EXISTS org;
CREATE TABLE IF NOT EXISTS org.role_definitions (
  role_id text NOT NULL, version text NOT NULL, yaml jsonb NOT NULL, yaml_sha256 text NOT NULL, git_commit text NOT NULL,
  approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL CHECK (status IN ('proposed','evaluated','active','suspended','retired')),
  PRIMARY KEY (role_id, version));
CREATE TABLE IF NOT EXISTS org.eval_gates (
  gate_id bigserial PRIMARY KEY, role_id text NOT NULL, role_version text NOT NULL,
  layer text NOT NULL CHECK (layer IN ('L0','L1','L2','L3','L4','L5')), set_name text NOT NULL, metric text NOT NULL, k int,
  value numeric NOT NULL, threshold numeric NOT NULL, passed boolean NOT NULL, inspect_log text NOT NULL, model text NOT NULL,
  git_commit text, evaluated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (role_id, role_version) REFERENCES org.role_definitions(role_id, version));
CREATE TABLE IF NOT EXISTS org.agents (
  agent_id text PRIMARY KEY, tenant_id text NOT NULL, role_id text NOT NULL, role_version text NOT NULL, zakazka_id text,
  process_id text NOT NULL, workflow_instance text NOT NULL, model text NOT NULL, model_version text, prompt_version text NOT NULL,
  policy_bundle_rev text NOT NULL, gateway_key_id text NOT NULL, sandbox_profile text NOT NULL, image_digest text,
  node text, runtime_class text, started_at timestamptz, finished_at timestamptz, exit_code int, cost_usd numeric, created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (role_id, role_version) REFERENCES org.role_definitions(role_id, version));
"""


def ensure_schema(conn):
    conn.execute(DDL)


def seed_roles(conn, roles_yaml: dict, eval_status: dict, git_commit: str, approved_by="adam"):
    """roles_yaml: {role: dict z knowledge/organization/roles/<role>.yaml}; eval_status: results/eval-status.json. status: passed → active, failed → suspended, jinak proposed."""
    n = 0
    for role, y in roles_yaml.items():
        st = (eval_status.get(role) or {}).get("status")
        status = {"passed": "active", "failed": "suspended"}.get(st, "proposed")
        sha = hashlib.sha256(json.dumps(y, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        conn.execute("""INSERT INTO org.role_definitions (role_id, version, yaml, yaml_sha256, git_commit, approved_by, status)
                        VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
                        ON CONFLICT (role_id, version) DO UPDATE SET yaml = EXCLUDED.yaml, yaml_sha256 = EXCLUDED.yaml_sha256, git_commit = EXCLUDED.git_commit, status = EXCLUDED.status""",
                     (role, str(y["version"]), json.dumps(y, ensure_ascii=False, default=str), sha, git_commit, approved_by, status)); n += 1
    return n


def seed_eval_gates(conn, results: dict, git_commit: str):
    """results: {role: obsah results/<role>.json}. Řádky PASS/FAIL (SKIP vrstvy se neevidují – nebyly měřeny)."""
    n = 0
    for role, r in results.items():
        for x in r.get("rows", []):
            if x.get("status") not in ("PASS", "FAIL"): continue
            conn.execute("""INSERT INTO org.eval_gates (role_id, role_version, layer, set_name, metric, k, value, threshold, passed, inspect_log, model, git_commit)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                         (role, str(r["version"]), x["layer"], x["set_name"], x["metric"], x.get("k"), x["value"], x["threshold"], x["passed"], x.get("inspect_log") or "logs/", x.get("model", "mock"), git_commit)); n += 1
    return n


def seed_agents(conn, ledger: list, zid: str, roles_yaml: dict, opa_rev: str, model: str, tenant="acme"):
    """Instance rolí jedné zakázky z ledgeru aplikace (ROLE_POD + AGENT_RUN): agent_id = SPIFFE ID role per běh (identita role; SVID až P2-3)."""
    runs = {e["role"]: e for e in ledger if e.get("kind") == "AGENT_RUN" and e.get("zakazka") == zid}
    n = 0
    for e in ledger:
        if e.get("kind") != "ROLE_POD" or e.get("zakazka") != zid: continue
        role = e["role"]; y = roles_yaml.get(role, {}); run = runs.get(role, {})
        agent_id = f"spiffe://platform/role/{role}/{tenant}/{zid}/{e['pod'].rsplit('-', 1)[-1]}"
        conn.execute("""INSERT INTO org.agents (agent_id, tenant_id, role_id, role_version, zakazka_id, process_id, workflow_instance, model, prompt_version, policy_bundle_rev,
                                                gateway_key_id, sandbox_profile, image_digest, node, runtime_class, exit_code, cost_usd)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (agent_id) DO NOTHING""",
                     (agent_id, tenant, role, str(y.get("version", "0")), zid, (y.get("processes") or ["?"])[0], zid, model, str(y.get("version", "0")), opa_rev,
                      f"k-{tenant}-{zid}-{role}", (y.get("sandbox") or {}).get("profile", "?"), e.get("image"), e.get("node"), e.get("runtime_class"), e.get("exit_code"), run.get("cost_usd"))); n += 1
    return n


def summary(conn):
    out = {}
    for t, q in (("role_definitions", "SELECT role_id, version, status FROM org.role_definitions ORDER BY 1"),
                 ("eval_gates", "SELECT role_id, layer, metric, value, threshold, passed FROM org.eval_gates ORDER BY role_id, layer"),
                 ("agents", "SELECT agent_id, role_id, role_version, model, gateway_key_id, sandbox_profile, image_digest FROM org.agents ORDER BY created_at DESC LIMIT 20")):
        out[t] = [list(map(lambda v: float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, (int, bool)) else v, r)) for r in conn.execute(q).fetchall()]
    return out
