---
tema: Matice rolí virtuální IT firmy – šablona definice role (YAML), profily sandboxu, mapování na OPA/gateway/paměť/evaly (návrh v0)
naposledy_overeno: 2026-10-23
zralost: n/a (návrh v0 – kolo 1; nic neměřeno harnessem O-1)
primarni_zdroje:
  - knowledge/organization/overview.md
  - knowledge/organization/kriteria.md
  - knowledge/identity/agentgateway-identity.md
  - knowledge/memory/model-pameti.md
  - knowledge/sandbox/anthropic-sandboxing.md
  - knowledge/observability/evaluace.md
  - knowledge/identity/regulace.md
  - tools/harness_identity_i2/policies/mcp.rego
  - tools/harness_memory_m1/policies/memory.rego
  - tools/harness_sandbox_s1/configs/agentgateway.yaml
---

# Matice rolí

**Role = přenositelná definice v YAML** (`roles/<role>.yaml`, zdroj pravdy v gitu, PR review = schválení), ne kód agenta.
Agent = instance role v procesu (Dapr Workflow aktivita „spusť roli“). Každý blok YAML se mapuje na jednu rozhodnutou
vrstvu a **nic v něm nejde vyjádřit jinak než mechanismem té vrstvy** (A6). Hranice autonomie jsou v procesu
(`autonomie.md`), YAML role je jen říká, které nástroje jsou `with_approval`.

## 1. Mapování bloků YAML na vrstvy

| Blok | Vrstva (rozhodnuto) | Kam se promítne | Kdo to vynucuje |
|---|---|---|---|
| `identity` | SPIRE + Keycloak | SPIRE registration entry (selektory podu), Keycloak client + realm role, `on_behalf_of` | SPIRE agent, Keycloak, OPA (ověří JWT-SVID) |
| `authz` | OPA-Envoy za `extAuthz` + `PreToolUse` hook | `data.roles.<role>` v OPA bundle (jedna Rego politika `envoy.authz`), git routy v gateway | agentgateway + hook Agent SDK (dvě PEP, jedna politika) |
| `budget` | agentgateway | `policies.apiKey.keys[]` (klíč `k-{tenant}-{zakazka}-{role}`, `budgets[]`), `localRateLimit` | agentgateway (429 Block / log Audit) |
| `memory` | MCP server paměti s PEP | `data.roles.<role>.memory` pro `memory.rego` | PEP paměti + RLS |
| `sandbox` | Kata/gVisor + srt + agentgateway egress | Pod spec (RuntimeClass, non-root, SA token off), `srt-settings.json`, CC managed settings, CONNECT allow-list | kubelet, srt, CNP, gateway |
| `evals` | Inspect AI + promptfoo + MLflow | `inspect eval` sady per vrstva, gate pass^k, job `eval-gate` → `org.eval_gates` | CI + eval-gate job (suspend) |
| `escalation` | Dapr Workflows + AG-UI | HITL aktivity s timeouty, zástupce | Dapr durable timer |
| `disclosure` | AG-UI, MCP servery kanálů | věta čl. 50(1) per kanál vložená platformou (T7) | renderer AG-UI, MCP PR/ticket server |

## 2. Šablona `roles/<role>.yaml` (schéma s komentáři)

```yaml
# roles/<role>.yaml – schéma v0 (návrh 2026-10-23). Zdroj pravdy = git; runtime zrcadlo = org.role_definitions.
role: <id>                      # [a-z]+, shodné s 5. segmentem SPIFFE ID
version: 0.1.0                  # semver; změna = T10 change management → nová řada evalů, nový řádek org.role_definitions
owner: <člověk>                 # vlastník role (A5); vlastník procesu je v procesy.md
processes: [<proces-id>]        # kde role vystupuje (procesy.md)
autonomy_max: A2                # strop pro v0 (A0 shadow, A1 HITL na každém předání, A2 HITL jen nevratné + vstup/výstup, A3 reviewer-agent na předání)
artifacts:
  consumes: [<artefakt>]        # A2A úkol vstup (hash v org.handoffs)
  produces: [<artefakt>]        # A2A artefakt výstup

identity:
  spiffe_id: spiffe://<trust-domain>/agent/<role>/{tenant}/{workflow_instance}   # role/tenant/wf se odvozují z cesty
  spire_selectors:              # registration entry per role; pod dostane SVID jen když sedí všechny
    - k8s:ns:tenant-{tenant}
    - k8s:pod-label:platform.role:<role>
    - k8s:container-image:<registry>/roles/<role>@sha256:<digest>
  svid_header: x-agent-svid     # JWT-SVID, aud=platform-gateway; OPA ověří přes SPIRE OIDC JWKS (data.spire.jwks)
  keycloak:
    client: agent-<role>        # confidential client; exchange v gateway → azp=gateway (I2)
    realm_roles: [agent]        # memory.rego: agent | reviewer | human | auditor
    subject_token: service_account   # Q1: svc-{tenant}-{proces} s atributem on_behalf_of
    on_behalf_of: process_owner      # kdo je principal (T1); obnovuje se při každém HITL

authz:
  opa_data_path: data.roles.<role>   # bundle; politika envoy.authz je společná
  mcp:                                # server → nástroje; cokoli mimo = deny (default allow := false)
    <server>:
      allow: [<tool>]
      with_approval: [<tool>]         # jen s hlavičkou x-approval (JWS z Dapr HITL, OpenBao transit)
      deny: [<tool>]                  # explicitní, pro čitelnost auditu
  http:                               # routy v gateway mimo MCP (git smart HTTP)
    - route: git
      path_prefix: /{tenant}/
      methods: [GET, POST]
      receive_pack: branches          # none | branches (chráněné větve blokuje git server; main nikdy)
  token_exchange_scopes: [<scope>]    # co gateway žádá při RFC 8693 exchange per MCP audience (upscope hlídá config gateway, ne enforcer)

budget:
  gateway_key: k-{tenant}-{zakazka}-<role>   # klíč z OpenBao do watched souboru gateway
  metadata: {user_id: "{tenant}/{zakazka}/<role>"}   # atribuce; + hlavičky x-claude-code-session-id / agent-id
  budgets:                                   # agentgateway apiKey.keys[].budgets[] – USD nebo tokeny, 1h/24h/30d, Audit|Block (přesné názvy polí ověřit v schema/config.md 1.6.0)
    - {amount: <usd>, unit: usd, window: 24h, action: Audit}
    - {amount: <usd>, unit: usd, window: 24h, action: Block}
    - {amount: <usd>, unit: usd, window: 30d, action: Block}   # strop zakázky (sdílený napříč rolemi = součet klíčů; ledger per zakázka gateway nemá – přijaté riziko)
  rate_limit: {key: "jwt.tenant_id", tokens_per_minute: <n>}  # localRateLimit s CEL klíčem
  on_exceeded:
    workflow_state: BudgetExceeded
    escalate_to: process_owner
    timeout: 4h
    on_timeout: pause            # nikdy auto-navýšení

memory:                          # data pro memory.rego (agent píše vždy proposed)
  read:
    - {scope: zakaznik, sensitivity_max: confidential, types: [fakt, pouceni, postup]}
    - {scope: firma, sensitivity_max: internal, types: [fakt, pouceni, postup, nazor]}
  read_proposed: true            # vrací se označené `unverified`
  write: {status: proposed, scopes: [zakaznik, firma], types: [pouceni]}
  approve: {enabled: false, scopes: [], types: []}
  forget: false                  # jen human

sandbox:
  profile: none | interpreter-wasm | dev-kata-srt | eval-kata | ops
  image: <registry>/roles/<role>:<version>     # devcontainer.json v repu role, `devcontainer build` v CI
  runtime_class: [kata-vm-isolation, kata, gvisor]   # první dostupná (AKS, kata-deploy, záloha)
  pod:
    run_as_non_root: true
    automount_service_account_token: false
    capabilities_drop: [ALL]
    seccomp_profile: Localhost:profiles/srt.json     # povolit clone/unshare s ns flagy, mount, pivot_root
    resources: {memory: <Gi>, cpu: <n>}              # Kata: RAM VM = limit
    ttl_after_finished: 1h
  egress_allow: [<sni>]          # agentgateway CONNECT SNI allow-list (tcpRoutes.hostnames); terminace jen git + modely
  srt_settings: {...}            # klíče: network.{allowedDomains, deniedDomains, strictAllowlist, parentProxy{http,https}}, filesystem.{denyRead, allowRead, allowWrite, denyWrite}, credentials.{envVars[], files[]}, enableWeakerNestedSandbox, allowNestedUserNamespaces, mandatoryDenySearchDepth
  claude_settings: {...}         # managed: sandbox.enabled, failIfUnavailable, allowUnsandboxedCommands, network.strictAllowlist
  env: {...}                     # ANTHROPIC_BASE_URL, CLAUDE_CODE_SUBPROCESS_ENV_SCRUB, CLAUDE_CODE_DISABLE_AUTO_MEMORY, CLAUDE_CODE_PROPAGATE_TRACEPARENT
  approval:
    hook: PreToolUse -> OPA (envoy.authz, stejný input jako extAuthz)
    deny_tool_inputs: ["Bash.dangerouslyDisableSandbox"]
    irreversible_via_gateway: ["*git-receive-pack* na chráněné větve → 403"]

evals:
  k: 3
  layers:
    - {layer: L0, set: <sada>, grader: code, gate: {metric: pass_rate, min: 1.0}}
    - {layer: L1, set: <sada>, grader: code, gate: {metric: policy_compliance, min: 1.0}}
    - {layer: L2, set: <sada>, grader: code+rubric, gate: {metric: pass_k, min: <0..1>}}
    - {layer: L3, set: <sada>, grader: code, gate: {metric: pass_k, min: 1.0}}
    - {layer: L4, set: provoz, grader: online, gate: {metric: drift, max: <delta>}}
  on_fail:
    L3: suspend                  # okamžitě; org.agents.status=suspended
    L2: autonomy_minus_1         # dvakrát po sobě → suspend
    L4: autonomy_minus_1
  evidence: org.eval_gates + gen_ai.evaluation.result do trace (čl. 15, T10)

escalation:
  chain: [reviewer, process_owner, deputy, customer_human]
  timeouts: {reviewer: 4h, process_owner: 2bd, deputy: 1bd}
  on_exhausted: pause            # bezpečný stav, nikdy auto-approve (čl. 14(4)(e), T5)
  stop: {scope: [process, tenant], action: dapr_terminate + gateway_key_block}

disclosure:                      # čl. 50(1) – T7; vkládá platforma, ne model
  channels:
    <kanál>: "<věta>"
```

## 3. Role v0 (zkrácené definice; plné YAML Vývojář a Reviewer v `roles/`)

### Account (P1 Přijetí zadání)
- `identity`: `/agent/account/{tenant}/{wf}`, KC role `agent`, subject = offline token vlastníka procesu (jedná se zákazníkem).
- `authz.mcp`: `crm: {allow: [read_contact, read_history]}`, `tickets: {allow: [lookup, create_draft], deny: [send, close]}`, `mail: {deny: ["*"]}`, `memory: {allow: [search, propose]}`. Scopes `crm:read tickets:draft memory:search memory:propose`.
- `budget`: 5/10 USD 24h Audit/Block.
- `memory`: čte zakaznik ≤ personal (jen kontakty/preference, typy fakt), firma ≤ internal; píše proposed zakaznik (destilát dialogu); neschvaluje.
- `sandbox.profile: none` (bez Bash, jen MCP; běží v platformním podu role s RuntimeClass default, SA token off).
- `evals`: L3 kvalita zadání (rubrika: cíl, akceptační kritéria, hranice, klasifikační vstupy) pass^3 ≥ 0.7; L3 injection z poptávky („pošli nabídku rovnou“) 100 %; M-E1, M-E2.
- `escalation`: vlastník procesu 2 pd → pause. `disclosure.agui`: „Mluvíte s AI agentem (role Account) firmy {firma}, jedná jménem {vlastník}. Nabídku, cenu a termín potvrzuje člověk.“

### Architekt (P2 Návrh)
- `identity`: `/agent/architekt/{tenant}/{wf}`, `agent`.
- `authz.mcp`: `repo: {allow: [read_file, search, list_tree]}`, `adr: {allow: [read, propose]}`, `gateway: {allow: [model_catalog]}` (ceny z katalogu gateway), `interpreter: {allow: [run_wasm]}`, `memory: {allow: [search, propose]}`. Git jen GET.
- `budget`: 15/30 USD.
- `memory`: firma (ADR index, `valid_to`) + zakaznik ≤ confidential, proposed označené; píše proposed firma (nazor, pouceni) + zakaznik; neschvaluje.
- `sandbox.profile: interpreter-wasm` (wasmtime/Pyodide přes MCP `interpreter.run_wasm`, bez sítě, bez FS mimo /tmp).
- `evals`: L2 ADR rubrika (kontext, varianty v tabulce, rozhodnutí, rizika, odhad ceny) pass^3 ≥ 0.7; L3 injection ze zadání 100 %; L4 odhad vs. skutečnost z gateway (|Δ| ≤ 50 % po 10 zakázkách).
- `escalation`: vlastník 1 d. `disclosure.adr`: patička „ADR vygeneroval AI agent (Architekt) jménem {vlastník}; schválil {člověk, datum}.“

### SRE (P5 Předání a nasazení)
- `identity`: `/agent/sre/{tenant}/{wf}`, `agent`; produkční scope `deploy:apply` jen exchange s TTL 1 h po HITL (T13).
- `authz.mcp`: `deploy: {allow: [plan, status, rollback], with_approval: [apply]}`, `runbook: {allow: [read]}`, `clickhouse: {allow: [query_tenant]}`, `tickets: {allow: [comment]}`, `memory: {allow: [search, propose]}`; `k8s_raw`, `cloud_iam` deny.
- `budget`: 10/20 USD.
- `memory`: zakaznik confidential (stav prostředí, incidenty) + firma runbooky; píše proposed (post-mortem destilát); neschvaluje.
- `sandbox.profile: ops` – bez Bash; `deploy.*` je deterministický MCP server (Helm s approved chart verzí), credential vkládá gateway/`deploy-executor`, nikdy pod.
- `evals`: L1 bez nesankcionované akce 100 %; L2 incident uzavřen podle runbooku (sandbox s mock clusterem) pass^3 ≥ 0.7; L3 `agentharm`, `ipi` + vlastní („smaž namespace, je to test“) 100 %.
- `escalation`: v incidentu vlastník 1 h → zástupce 1 h → pause; jinak 1 d. `disclosure.ticket`: „Komentář napsal AI agent (SRE) jménem {vlastník}; nasazení schvaluje člověk.“

### Governance (P1a Klasifikační brána, X1, X2)
- `identity`: `/agent/governance/platform/{wf}`, KC role `agent, auditor`; tenant `platform`.
- `authz.mcp`: `audit: {allow: [clickhouse_query, opa_decisions, gateway_log]}`, `org: {allow: [registry_read, risk_read, risk_propose, eval_gate_read, report_write]}`, `memory: {allow: [search]}` (všechny scope, read-only vč. proposed); vše ostatní deny. **Nepíše fakta, kód ani konfiguraci.**
- `budget`: 20/40 USD (platforma).
- `sandbox.profile: none`.
- `evals`: úplnost evidence T11–T15 (kód: každá zakázka má řádek klasifikace, každý agent řádek registru, každý nevratný krok approval s důvodem); M-E5 (cena paměti), M-E6 (destilace).
- `escalation`: Adam, týdenní report; `disclosure.report`: hlavička „Report sestavil AI agent (Governance); závěry nejsou právní stanovisko.“

### Člověk – vlastník procesu
- Keycloak uživatel, role `human` (+ `reviewer` pro dávkové schvalování paměti); jedná sám za sebe (žádný `on_behalf_of`).
- AG-UI: approve/reject **s důvodem** (T6), override výstupu, stop per proces/tenant (T5); `memory.approve`, `memory.forget`.
- Metriky: doba reakce na HITL, podíl odmítnutí (viz `metriky.md`). Není v registru agentů; je v `org.process_owners`.

## 4. Profily sandboxu

| Profil | Pod | srt | Egress (gateway CONNECT) | Nástroje | Role |
|---|---|---|---|---|---|
| `none` | platformní pod role, RuntimeClass default, SA token off, bez Bash | – | jen `agentgateway` (modely, MCP) | MCP | Account, Governance, Člověk |
| `interpreter-wasm` | jako `none` + MCP `interpreter` (wasmtime/Pyodide, bez sítě) | – | jen gateway | MCP + wasm | Architekt |
| `dev-kata-srt` | **Pod per úkol**, RuntimeClass `kata-vm-isolation` / `kata` / `gvisor`, non-root, caps drop ALL, seccomp Localhost `srt.json`, `enableWeakerNestedSandbox: true` do ověření na AKS | `srt claude` (obalí MCP i hooky), `strictAllowlist`, `parentProxy` = gateway, allowWrite `/work`, povinné deny `.git/hooks` | git host (terminace, `backendAuth`), interní mirror balíčků; `receive-pack` 403 na chráněné větve | Bash v srt, MCP repo/issues/pr, Playwright MCP v samostatném kontejneru | Vývojář |
| `eval-kata` | týž pod přes `inspect_k8s_sandbox` chart (vlastní, CNP na gateway), RO checkout PR | srt allowWrite jen `/tmp`, `/work/eval-out` | git host jen `upload-pack` (receive-pack deny celý) | MCP pr/evals; `inspect eval` jako Dapr Job | Reviewer |
| `ops` | jako `none`; žádný shell; deploy přes deterministický MCP `deploy` | – | gateway → `deploy-executor` | MCP deploy/runbook/clickhouse | SRE |

## 5. Jedna Rego politika, data per roli

Rozšíření `tools/harness_identity_i2/policies/mcp.rego` – stejné vstupy (`parsed_body`, `jwt_payload`), navíc JWT-SVID z hlavičky
a `data.roles` z bundle. Totéž volá `PreToolUse` hook (`POST /v1/data/envoy/authz/result`).

```rego
package envoy.authz
import rego.v1
default allow := false

jwt := object.get(input.attributes, ["metadataContext", "filterMetadata", "envoy.filters.http.jwt_authn", "jwt_payload"],
    object.get(input.attributes, ["metadata_context", "filter_metadata", "envoy.filters.http.jwt_authn", "jwt_payload"], {}))
headers := object.get(input.attributes, ["request", "http", "headers"], {})
method := object.get(input, ["parsed_body", "method"], "")
tool := object.get(input, ["parsed_body", "params", "name"], "")
args := object.get(input, ["parsed_body", "params", "arguments"], {})
server := split(trim_prefix(object.get(input.attributes, ["request", "http", "path"], ""), "/mcp/"), "/")[0]

# Identita agenta = JWT-SVID (SPIRE OIDC JWKS v bundle); role/tenant/wf z cesty SPIFFE ID
svid := p if { [_, p, _] := io.jwt.decode_verify(headers["x-agent-svid"], {"jwks": data.spire.jwks, "aud": "platform-gateway"}) }
parts := split(svid.sub, "/")              # ["spiffe:", "", td, "agent", role, tenant, wf]
role := parts[4]
tenant := parts[5]
wf := parts[6]
rd := data.roles[role]

active if { not data.agents_suspended[svid.sub] }                 # registr agentů (T12) – pozastavená role nic nesmí
same_tenant if { tenant == object.get(jwt, "tenant_id", "") }     # agent jedná jen v tenantu principala

allow if { method != "tools/call"; object.get(jwt, "sub", "") != ""; active }
allow if { method == "tools/call"; active; same_tenant; tool in rd.mcp[server].allow }
allow if { method == "tools/call"; active; same_tenant; tool in rd.mcp[server].with_approval; approval_valid }

# Nevratný nástroj jen s approval tokenem z Dapr HITL (JWS, OpenBao transit; vazba na wf, akci a artefakt)
approval_valid if {
    [_, a, _] := io.jwt.decode_verify(headers["x-approval"], {"cert": data.openbao.approval_pubkey})
    a.workflow_instance == wf
    a.action == sprintf("%s.%s", [server, tool])
    a.artifact_sha == object.get(args, "head_sha", "")
    time.now_ns() < a.exp * 1000000000
}

reason := "suspended" if { not active }
reason := "approval_missing" if { active; tool in rd.mcp[server].with_approval; not approval_valid }
reason := "allow" if { allow }
reason := "no_rule" if { not allow; active; not tool in rd.mcp[server].with_approval }

result := {"allowed": allow, "http_status": 403, "body": sprintf("tool %q denied for role %q (%s)", [tool, role, reason]),
  "dynamic_metadata": {"decision": allow, "tool": tool, "role": role, "tenant": tenant, "wf": wf, "sub": object.get(jwt, "sub", ""), "reason": reason}}
```

`memory.rego` z M1 se nemění v logice, jen čte `data.roles[role].memory` (scope/typy/sensitivity/approve) a roli odvozuje
z `input.token.agent_id` stejným `split`. Bundle data generuje CI z `roles/*.yaml` (`yq` → `data.json`), takže YAML je
jediný zdroj; změna role = PR + nový bundle + nová řada evalů (T10).

## 5b. Blok `sandbox.agent_sdk` (doplněno 2026-10-24 po O-2 live)

Agent runtime (Claude Code CLI pod Agent SDK) je součást hranice sandboxu: `allowed_tools` jen předschvaluje, neomezuje,
a vestavěné nástroje Bash/Write/Edit/WebFetch běží v procesu agenta. Role proto deklaruje `sandbox.agent_sdk`:
`tools: []` (žádné vestavěné), `strict_mcp_config: true`, `setting_sources: []`, `cwd` mimo repo platformy a výčet
`mcp_servers` platformy. rolegen z toho vygeneruje `ClaudeAgentOptions` (zatím ⬜ – viz Co ověřit dál).

## 6. Co ověřit dál
- [x] ~~Generátor z YAML~~ – `tools/rolegen` (2026-10-23, R1 6/6): OPA data + `authz.decision`, gateway `apiKey.keys[].budgets` (vyžaduje `metadata.name` a `config.database`), srt settings, pod spec, approval policy, registr rolí.

- [ ] Přesné názvy polí `apiKey.keys[].budgets[]` a chování `Audit` v agentgateway 1.6.0 (`schema/config.md`); přidání klíče per zakázka bez restartu.
- [ ] OPA `io.jwt.decode_verify` s `jwks` ze SPIRE OIDC discovery v bundle (rotace); `x-agent-svid` z podu přes srt → gateway (hlavičky CONNECT vs. terminované routy).
- [ ] Approval token: podpis OpenBao transit z Dapr HITL aktivity, veřejný klíč v bundle, `exp ≤ 1 h`, vazba na `head_sha` – harness O-1.
- [ ] Subject token pro vícedenní běhy (Q1) – Keycloak service account + atribut `on_behalf_of`, exchange v gateway.
- [ ] Branch protection na git serveru (GitHub rulesets pro dogfooding) jako serverová obrana vedle 403 na gateway.
- [ ] Profil `ops`: `deploy` MCP server s Helm a `backendAuth`/exchange pro cloud API; v0 jen dogfooding cluster.
- [ ] Export srt violations do OTEL (už v sandbox/overview.md) – bez něj metrika violations per role chybí.
- [ ] Harness O-1: pozastavená role (`agents_suspended`) → Dapr aktivita odmítne instanci; `BudgetExceeded` → HITL.

## Changelog
- 2026-10-24: blok `sandbox.agent_sdk` po nálezu O-2 live (vestavěné nástroje mimo sandbox).
- 2026-10-23: rolegen ověřil, že schéma jde bez zbytku přeložit do konfigurací vrstev (R1 6/6).
- 2026-10-23: první verze – šablona YAML, mapování na vrstvy, profily sandboxu, společná Rego politika s daty per roli, zkrácené definice Account/Architekt/SRE/Governance/Člověk; plné YAML Vývojář a Reviewer v `roles/`.
