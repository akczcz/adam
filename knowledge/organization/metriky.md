---
tema: Metriky a odpovědnost organizační vrstvy – per proces a role, zdroje dat, registr agentů (T12) a risk register (T11) jako data, rozšiřování autonomie (návrh v0)
naposledy_overeno: 2026-10-23
zralost: n/a (návrh v0 – kolo 1; schéma neověřeno harnessem)
primarni_zdroje:
  - knowledge/organization/kriteria.md
  - knowledge/observability/overview.md
  - knowledge/observability/evaluace.md
  - knowledge/memory/model-pameti.md
  - knowledge/identity/regulace.md
  - knowledge/gateway/overview.md
---

# Metriky a odpovědnost

Zásada O4: firma dělá práci dobře, když to jde **změřit z dat, která už vznikají** (A2: každá akce má identitu, rozpočet
a stopu), a když za každý proces **odpovídá jeden člověk** (A5). Autonomie se **rozšiřuje měřením**, ne nastavením.

## 1. Zdroje dat (vše rozhodnuté vrstvy)

| Zdroj | Co nese | Klíč pro spojení |
|---|---|---|
| ClickHouse spany (OTEL Collector, `genainormalizer`) | `gen_ai.usage.{input,output,cache_read,cache_creation}_tokens`, `gen_ai.request.model`, `gen_ai.tool.name`, `claude_code.*` (`interaction`, `llm_request`, `tool`), `session.id`, `enduser.id`, `tenant.id`, `memory.status` (spany `search_memory`/`create_memory` – M1h), `gen_ai.evaluation.result` eventy | `trace_id`, `session.id`, `x-claude-code-agent-id` |
| agentgateway JSON log + Prometheus | request per klíč (`metadata.user_id` = `{tenant}/{zakazka}/{role}`), `…cost_usd_total`, `user.sub`, `authz.decision`, `tls.sni` u CONNECT, 403/429 | klíč, `traceparent` |
| OPA decision log | `dynamic_metadata.{decision, tool, role, tenant, wf, reason}` (gateway i hook) | `wf`, `trace_id` v input (doplnit) |
| Ledger paměti (memory server) | `action`, `effective_status`, `reason` (`agent_write_quarantined`, `approve_by_reviewer`, `rejected`…), `created_by.agent_id` | `agent_id`, `record.id` |
| Inspect logy (`evals_df()`), promptfoo JSON | pass^k per vrstva, policy-compliance, judge agreement; export JSONL | `role`, `version`, `layer` |
| Dapr Workflow události (Postgres state store, Dapr events) | přechody stavů, HITL verdikty (approve/reject + důvod), timeouty, eskalace, stop | `workflow_instance` |
| srt violations (export do OTEL – otevřeno v `sandbox/overview.md`) | `deny <syscall> <path>`, odmítnuté hosty | `wf`, `commandId` |
| `org.*` tabulky (níže) | registr agentů, approvals, eval gates, risk register, post-mortemy | `agent_id`, `workflow_instance` |

## 2. Metriky per proces

| Metrika | Definice | Zdroj | Cíl v0 (Pozn. Adam, odhad) |
|---|---|---|---|
| Doba cyklu | `end − start` workflow instance; rozpad per stav | Dapr události | P4 úkol ≤ 4 h běhu; zakázka ≤ 10 pd |
| Doba čekání na člověka | součet trvání HITL aktivit | Dapr | ≤ 50 % doby cyklu (jinak je úzké hrdlo člověk, ne agent) |
| Podíl HITL odmítnutí | `reject / (approve + reject)` per schvalovací bod | `org.approvals` | ≤ 10 % (merge), ≤ 20 % (návrh) |
| Cena per zakázka | Σ `cost_usd` přes klíče `k-{tenant}-{zakazka}-*` | gateway Prometheus/log | ≤ odhad Architekta × 1.5 |
| Počet eskalací | události `escalation` per instance a úroveň řetězu | Dapr | ≤ 1 na zakázku nad úroveň vlastníka |
| Smyčky Review → Implementace | počet návratů per PR | Dapr | ≤ 2 |
| Incidenty a post-mortemy | incident otevřen/uzavřen, MTTR, post-mortem do 5 pd | `org.postmortems`, tickety | 100 % incidentů má post-mortem |
| Podíl artefaktů s předáním | předání s hashem artefaktu / všechna předání | `org.handoffs` | 100 % (B1 – bez artefaktu není audit) |
| Stop tlačítko | čas od stisknutí do `Pozastaveno`; rozpracovaná práce zachována | Dapr + git | ≤ 60 s; 100 % |

## 3. Metriky per role

| Metrika | Definice | Zdroj | Gate / cíl |
|---|---|---|---|
| pass^k per vrstva | Inspect, `k = 3`, per verze role | `org.eval_gates` | L0 1.0; L1 policy-compliance 1.0; L2 viz YAML; L3 1.0 |
| Cena per úkol | Σ `cost_usd` per `session.id` / `x-claude-code-agent-id` | gateway + ClickHouse | Vývojář ≤ 25 USD (Audit práh) |
| Tokeny per úkol, podíl cache | `gen_ai.usage.*`, `cache_read / input` | ClickHouse | cache ≥ 50 % u Vývojáře |
| Policy-compliance (provoz) | běhy bez OPA deny `reason ∉ {allow}` / všechny běhy | OPA decision log | ≥ 0.99; deny `approval_missing` = třída A → suspend |
| Podíl sandbox violations | běhy s ≥ 1 srt violation nebo gateway CONNECT 403 / běhy | srt export, gateway log | ≤ 5 % (diagnostika, ne gate); exfil pokus = třída A |
| Podíl zamítnutých zápisů do paměti | `rejected / proposed` per role | ledger paměti | ≤ 20 %; > 50 % → role nepíše (write off) |
| Shoda s člověkem | HITL verdikt vs. verdikt reviewer-agenta (Reviewer), judge vs. člověk (L5) | `org.approvals` + Inspect | ≥ 0.85 |
| Podíl HITL odmítnutí výstupu role | odmítnuté artefakty role / všechny | `org.approvals` | ≤ 10 % |
| Doba běhu úkolu | Dapr aktivita | Dapr | per role v YAML |

Třídy porušení: **A** (pokus o nevratnou akci bez approval, exfil, cross-tenant čtení, zápis `approved` agentem) → okamžité
pozastavení verze role; **B** (host mimo allow-list, odmítnutý zápis, překročený soft rozpočet) → metrika, L4 drift.

## 4. Registr agentů (T12) a risk register (T11) – datové schéma

Postgres platformy, schéma `org` (Q5: stejný cluster jako paměť, vlastní DB role `org_writer` pro Dapr aktivity a eval-gate
job, `org_reader` pro Governance MCP; RLS per `tenant_id`, tenant `platform` pro průřez). Append-only tabulky podepsané
klíčem z OpenBao (T2). Export JSONL per tenant pro deployera (čl. 13(3)(f)).

```sql
CREATE SCHEMA org;

-- Definice rolí: git je zdroj pravdy, tady runtime zrcadlo (T10 change management)
CREATE TABLE org.role_definitions (
  role_id        text NOT NULL,
  version        text NOT NULL,
  yaml           jsonb NOT NULL,
  yaml_sha256    text NOT NULL,
  git_commit     text NOT NULL,
  approved_by    text NOT NULL,            -- Keycloak sub vlastníka role
  approved_at    timestamptz NOT NULL,
  status         text NOT NULL CHECK (status IN ('proposed','evaluated','active','suspended','retired')),
  PRIMARY KEY (role_id, version)
);

-- Registr agentů (T12): jedna řádka = instance role (SVID) v procesu
CREATE TABLE org.agents (
  agent_id            text PRIMARY KEY,     -- SPIFFE ID
  tenant_id           text NOT NULL,
  role_id             text NOT NULL,
  role_version        text NOT NULL,
  zakazka_id          text,
  process_id          text NOT NULL,
  workflow_instance   text NOT NULL,
  model               text NOT NULL,        -- gen_ai.request.model
  model_version       text,
  prompt_version      text NOT NULL,
  policy_bundle_rev   text NOT NULL,        -- OPA bundle revision
  gateway_key_id      text NOT NULL,        -- k-{tenant}-{zakazka}-{role}
  sandbox_profile     text NOT NULL,
  image_digest        text,
  autonomy_level      text NOT NULL CHECK (autonomy_level IN ('A0','A1','A2','A3')),
  on_behalf_of        text NOT NULL,        -- principal (T1)
  owner_human         text NOT NULL,        -- vlastník procesu (A5)
  status              text NOT NULL CHECK (status IN ('active','suspended','retired')),
  created_at          timestamptz NOT NULL DEFAULT now(),
  retired_at          timestamptz,
  FOREIGN KEY (role_id, role_version) REFERENCES org.role_definitions(role_id, version)
);

-- Události registru (append-only, podepsané): pozastavení, změna autonomie, eval gate
CREATE TABLE org.agent_events (
  event_id        bigserial PRIMARY KEY,
  agent_id        text REFERENCES org.agents(agent_id),
  role_id         text, role_version text,
  tenant_id       text NOT NULL,
  kind            text NOT NULL CHECK (kind IN ('created','suspended','resumed','autonomy_changed','retired','violation_A','violation_B')),
  reason          text NOT NULL,
  evidence_ref    jsonb,                    -- {trace_id, span_id, eval_log, decision_log_id}
  actor           text NOT NULL,            -- člověk nebo job
  created_at      timestamptz NOT NULL DEFAULT now(),
  signature       text NOT NULL
);

-- Schvalovací rozhodnutí (T3, T6): důvod povinný
CREATE TABLE org.approvals (
  approval_id        text PRIMARY KEY,      -- ULID; jde do JWS x-approval
  tenant_id          text NOT NULL,
  workflow_instance  text NOT NULL,
  process_id         text NOT NULL,
  action             text NOT NULL,         -- např. pr.merge, deploy.apply, zadani.accept
  artifact_ref       text NOT NULL,         -- PR URL / chart
  artifact_sha       text NOT NULL,
  requested_by_agent text REFERENCES org.agents(agent_id),
  approver           text NOT NULL,         -- Keycloak sub (člověk)
  decision           text NOT NULL CHECK (decision IN ('approve','reject','override')),
  reason             text NOT NULL CHECK (length(reason) >= 10),   -- proti automation bias (T6)
  limits_shown       jsonb,                 -- co HITL ukázalo (confidence, evaly, cena) – čl. 14(4)(a)
  decided_at         timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL,  -- ≤ 1 h pro token
  signature          text NOT NULL
);

-- Předání s artefaktem (B1)
CREATE TABLE org.handoffs (
  handoff_id        text PRIMARY KEY,
  tenant_id         text NOT NULL,
  workflow_instance text NOT NULL,
  from_agent        text, to_agent text,
  artifact_kind     text NOT NULL,          -- zadani, adr, pr, eval_log, runbook
  artifact_ref      text NOT NULL,
  artifact_sha      text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Eval gate (čl. 15 evidence per verze)
CREATE TABLE org.eval_gates (
  gate_id        bigserial PRIMARY KEY,
  role_id        text NOT NULL, role_version text NOT NULL,
  layer          text NOT NULL CHECK (layer IN ('L0','L1','L2','L3','L4','L5')),
  set_name       text NOT NULL,
  metric         text NOT NULL,             -- pass_k, policy_compliance, agreement, drift
  k              int,
  value          numeric NOT NULL,
  threshold      numeric NOT NULL,
  passed         boolean NOT NULL,
  inspect_log    text NOT NULL,
  model          text NOT NULL,
  evaluated_at   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (role_id, role_version) REFERENCES org.role_definitions(role_id, version)
);

-- Vlastníci procesů (A5)
CREATE TABLE org.process_owners (
  process_id  text NOT NULL,
  tenant_id   text NOT NULL,
  owner       text NOT NULL,
  deputy      text NOT NULL,
  valid_from  date NOT NULL,
  valid_to    date,
  PRIMARY KEY (process_id, tenant_id, valid_from)
);

-- Risk register (T11): per zákazník / use case; NIST AI 600-1 kategorie, ISO 42005
CREATE TABLE org.risk_register (
  risk_id             text PRIMARY KEY,
  tenant_id           text NOT NULL,
  use_case_id         text NOT NULL,
  ai_act_class        text NOT NULL CHECK (ai_act_class IN ('minimal','limited','annex_iii_2','annex_iii_4','other_high')),  -- T9
  category            text NOT NULL,        -- confabulation, prompt_injection, data_privacy, ... (AI 600-1)
  description         text NOT NULL,
  likelihood          smallint NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
  impact              smallint NOT NULL CHECK (impact BETWEEN 1 AND 5),
  controls            jsonb NOT NULL,       -- [{kind: opa_rule|eval|gateway_budget|sandbox_profile|hitl, ref}]
  evidence_ref        jsonb,                -- poslední důkaz: eval gate id, decision log, trace
  owner               text NOT NULL,
  status              text NOT NULL CHECK (status IN ('open','mitigated','accepted','closed')),
  review_at           date NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE org.risk_events (
  event_id    bigserial PRIMARY KEY,
  risk_id     text REFERENCES org.risk_register(risk_id),
  tenant_id   text NOT NULL,
  kind        text NOT NULL,                -- created, reassessed, control_added, incident_linked, accepted
  detail      jsonb NOT NULL,
  actor       text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  signature   text NOT NULL
);

-- Post-mortemy: poučení žije v gitu (procedurální paměť), tady jen odkaz a metriky
CREATE TABLE org.postmortems (
  incident_id       text PRIMARY KEY,
  tenant_id         text NOT NULL,
  process_id        text NOT NULL,
  workflow_instance text,
  opened_at         timestamptz NOT NULL,
  closed_at         timestamptz,
  mttr_seconds      int,
  git_commit        text,                   -- knowledge/organization/postmortems/<id>.md
  risk_ids          text[],
  actions           jsonb                   -- [{action, owner, due, done}]
);

-- RLS vzor (jako u paměti – M1e): tenant z app.tenant_id, platform vidí vše
ALTER TABLE org.agents ENABLE ROW LEVEL SECURITY;
CREATE POLICY agents_tenant ON org.agents
  USING (tenant_id = current_setting('app.tenant_id', true) OR current_setting('app.tenant_id', true) = 'platform');
```

Kdo zapisuje: `org.agents` + `org.handoffs` Dapr aktivita „spusť roli“ / „předej“ (platformní SVID); `org.approvals` HITL
aktivita; `org.eval_gates` + `org.agent_events` eval-gate job (CI a noční L4); `org.risk_register` Governance (`risk_propose`)
→ člověk potvrdí; `org.postmortems` vlastník procesu. Governance jen čte (kromě `report_write`). OPA bundle dostává
`agents_suspended` jako data (`SELECT agent_id FROM org.agents WHERE status='suspended'`), takže pozastavení platí
na obou PEP do minuty.

## 5. Odpovědnost

- **Jeden člověk per proces a tenant** (`org.process_owners`, zástupce povinný kvůli timeoutům). Vlastník: schvaluje HITL
  s důvodem (T6), drží stop (T5), rozhoduje o úrovni autonomie, podepisuje post-mortem.
- **Vlastník role** (v YAML `owner`) odpovídá za verzi role: evaly, bundle, obraz; schvaluje PR s `roles/<role>.yaml`.
- **Post-mortem**: do 5 pd od uzavření incidentu nebo porušení třídy A; soubor `knowledge/organization/postmortems/<id>.md`
  (co, proč, poučení, změna procesu/role) jako PR (= procedurální paměť v gitu, review = schválení); řádek v
  `org.postmortems`; poučení typu `pouceni` může destilační agent navrhnout do sémantické paměti (`proposed`).
- **Governance report** týdně: úplnost T11–T15 (každá zakázka klasifikace, každý agent řádek registru, každý nevratný
  krok approval s důvodem, každá verze role eval gate), rozpočty vs. odhad, drift.

## 6. Jak metriky rozšiřují (a zužují) autonomii

| Úroveň | Co role dělá sama | Kde je člověk | Podmínka vstupu (per role × tenant) | Automatický pád |
|---|---|---|---|---|
| A0 shadow | navrhuje, nic nevykonává | vše | nová verze role prošla eval gate (L0–L3) | – |
| A1 | reverzibilní kroky | každé předání artefaktu + nevratné | ≥ 10 úkolů v A0, shoda s člověkem ≥ 0.8 | L3 fail / třída A → suspend |
| **A2 (v0 default a strop)** | reverzibilní kroky + předání reviewer-agentovi | nevratné kroky + vstup/výstup zakázky | ≥ 30 úkolů v A1 (nebo 4 týdny), L2 pass^3 ≥ gate, HITL odmítnutí ≤ 10 %, 0 porušení třídy A, policy-compliance ≥ 0.99 | HITL odmítnutí > 20 % za 10 úkolů nebo L4 drift (cena/kroky > baseline + 50 %) → A1 |
| A3 (po v0) | reviewer-agent nahrazuje člověka na předání; člověk vzorkuje 10 % | nevratné + vstup/výstup (zůstává – rozhodnutí v0) | ≥ 100 úkolů v A2, judge–human agreement ≥ 0.9, risk register bez open rizik třídy A | jako A2 → A2 |

Posun nahoru = rozhodnutí vlastníka procesu v AG-UI (řádek `org.agent_events kind=autonomy_changed` s důvodem a odkazem
na metriky); posun dolů a pozastavení = automaticky (eval-gate job, L4 alert → Dapr). High-risk profil (T9) zamyká A1.
Žádná úroveň neodstraňuje člověka z nevratných kroků a vstupu/výstupu zakázky – to je rozhodnutí v0, ne metrika.

## 7. Co ověřit dál

- [ ] Harness O-1: `org.approvals` → JWS → OPA; `agents_suspended` v bundle; metriky doby cyklu a ceny per zakázka z gateway log.
- [ ] OPA decision log: doplnit `trace_id` do inputu (hook i gateway), aby šel spojit se spany.
- [ ] Export srt violations do OTEL (sandbox/overview.md) – bez něj violations per role nejsou měřitelné.
- [ ] Gateway: ledger per zakázka neexistuje – Σ přes klíče; ověřit persistenci rozpočtů mezi replikami (gateway/overview.md).
- [ ] Podpis `org.*` append-only řádků klíčem z OpenBao (transit) – formát a ověření při exportu.
- [ ] Prahy v sekcích 2, 3, 6 přepočítat po 30 úkolech dogfoodingu.

## Changelog
- 2026-10-23: první verze – zdroje dat, metriky per proces a role, schéma `org.*` (T11, T12, approvals, eval gates), odpovědnost, úrovně autonomie A0–A3.
