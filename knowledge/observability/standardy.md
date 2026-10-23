---
tema: Standard na drátě – OTEL GenAI semconv, OpenInference a co emitují Claude Code / Agent SDK, Dapr, agentgateway, MCP a A2A SDK; kde se trace přeruší
naposledy_overeno: 2026-10-23
zralost: mixed (OTEL semconv vše Development; Claude Code traces beta; MCP Python SDK stable; A2A nic)
primarni_zdroje:
  - https://github.com/open-telemetry/semantic-conventions-genai
  - https://github.com/open-telemetry/semantic-conventions/blob/v1.44.0/CHANGELOG.md
  - https://github.com/Arize-ai/openinference/tree/main/spec
  - https://code.claude.com/docs/en/monitoring-usage
  - https://code.claude.com/docs/en/agent-sdk/observability
  - https://platform.claude.com/docs/en/manage-claude/opentelemetry
  - https://github.com/dapr/docs (v1.18 tracing-overview, workflow-architecture)
  - https://github.com/dapr/dapr-agents/tree/main/dapr_agents/observability
  - https://github.com/agentgateway/agentgateway/tree/v1.6.0/crates/agentgateway/src/telemetry
  - https://github.com/modelcontextprotocol/python-sdk (server/_otel.py)
  - https://github.com/a2aproject/a2a-python (utils/telemetry.py)
---

# Standard na drátě a souvislost trace

**Metodická poznámka (2026-10-23):** weby mimo code.claude.com a platform.claude.com byly nedostupné; vše ověřeno
ze zdrojových repozitářů (commit uveden v hlavičce zdrojů). GitHub Issues nebyly dostupné (stav SIG, návrhy A2A semconv).

## Závěr: trace je souvislý, ale jen s pěti vypínači

| Úsek | Stav | Podmínka |
|---|---|---|
| AG-UI klient → orchestrátor (FastAPI + Dapr sidecar) | souvislý | HTTP `traceparent`; AG-UI sám trace pole nemá (*neověřeno ve spec*) |
| Dapr Workflow → aktivita | **přeruší se v Dapru**, Dapr Agents obchází | docs 1.18 i 1.19: „activity code does not have access to the trace context“; `dapr-agents` serializuje `traceparent` do vstupu workflow a obnoví ho v aktivitě |
| Dapr Agents executor → Claude Agent SDK → CLI | souvislý (SDK ≥ 0.1.60, CLI ≥ 2.1.110) | SDK injektuje `TRACEPARENT`/`TRACESTATE` do env CLI při aktivním spanu; CLI potřebuje `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, `OTEL_TRACES_EXPORTER=otlp` (traces **beta**, default off) |
| CLI → agentgateway (model i HTTP MCP) | **přeruší se ve výchozím stavu** | CLI posílá `traceparent` jen na api.anthropic.com; s vlastním `ANTHROPIC_BASE_URL` nutné **`CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`** |
| agentgateway → model / MCP server | souvislý | SERVER span s remote parentem, k upstreamu nový child `traceparent` (kód `httpproxy.rs`, `trc.rs`; harness G1 K2d); u MCP i do `params._meta` (SEP-414) |
| model: Claude Platform (api.anthropic.com) | souvislý, **beta** | API emituje serverové spany `anthropic.messages.create` do *telemetry destination* (Console / Admin API); parent = `traceparent` requestu |
| model: Azure AI Foundry `/anthropic` | **končí na gateway** | serverové spany jen Claude Platform a Claude Platform on AWS; tokeny a cenu zapisuje gateway |
| MCP server Python SDK v2 | souvislý, default on | SERVER span `tools/call <tool>`, `gen_ai.operation.name=execute_tool`, kontext z `_meta` |
| MCP server TypeScript SDK | **přeruší se** | jen konstanty `TRACEPARENT_META_KEY`, žádná instrumentace |
| A2A agent ↔ agent | **přeruší se** | spec jen „should“; `a2a-python` má dekorátory spanů, ale neextrahuje ani neinjektuje `traceparent` |

**Co platforma musí doinstrumentovat:**
1. Env pro CLI v `ClaudeAgentOptions.env`: `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`,
   `OTEL_TRACES_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL`
   (bez defaultu!), **`CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`**, per `query()` `OTEL_RESOURCE_ATTRIBUTES=enduser.id=…,tenant.id=…`.
2. Orchestrátor: OTEL SDK + `DaprAgentsInstrumentor` (extra `observability`), aby při startu `ClaudeSDKClient` byl aktivní span.
3. agentgateway `config.tracing`: `clientSampling: true`, `randomSampling: false` (gateway nezačíná vlastní trace),
   `fields.add`: `user.sub: jwt.sub`, `agent.id: request.headers["x-claude-code-agent-id"]`, `session.id: …session-id`,
   cost z `llm.cost.total`; `mcp.tool.arguments` jen opt-in.
4. MCP servery v TypeScriptu: vlastní middleware (extrakce z `_meta` + hlavičky). A2A: ASGI/httpx instrumentace na obou stranách.
5. OTEL Collector: masking obsahu (všude opt-in, default off), normalizace `gen_ai.system` → `gen_ai.provider.name`;
   **žádný hotový procesor OpenInference ↔ GenAI** – převod dělá Arize knihovna (dual-write), ne collector.

## A. OTEL GenAI semantic conventions

- **Přesun do vlastního repa:** od semconv v1.42.0 (2026-06-12) jsou `gen_ai.*`, `model/mcp` a `docs/gen-ai/` v
  `open-telemetry/semantic-conventions-genai` (main @9ffc7e0, 2026-10-21) – **bez tagu a release**, CHANGELOG „Unreleased“.
- **Stav: vše `Development`** (224× development, 0× stable): spany `gen_ai.client.inference`, agent spany
  (`create_agent`, `invoke_agent` client/internal, `invoke_workflow`, `plan`), `execute_tool`, metriky
  (`gen_ai.client.inference.duration|time_to_first_chunk|usage.input_tokens|usage.cache_read.input_tokens|…`),
  event `gen_ai.evaluation.result`, `mcp.md`, `anthropic.md`.
- **MCP semconv existuje** (od v1.39): spany `{mcp.method.name} {target}`, `mcp.session.id`, `gen_ai.tool.name`;
  propagace SHOULD do `params._meta` (SEP-414). **A2A semconv neexistuje** (jen entita `gen_ai.main_agent` ↔ Agent Card).
- **Obsah promptů:** per-message eventy deprecated (v1.37); obsah jako Opt-In atributy `gen_ai.input.messages`,
  `gen_ai.output.messages`, `gen_ai.system_instructions`, nebo event `gen_ai.client.inference.operation.details`;
  zapnutí přes `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`.
- Změny za 6 měsíců: `gen_ai.system` → `gen_ai.provider.name`; `input_tokens` **zahrnuje** cache (Anthropic guidance);
  `cache_read` / `cache_creation` tokeny; `reasoning.output_tokens`; `invoke_workflow`; streaming atributy.
  **Cena v semconv není.**

## B. OpenInference (Arize)

Jiný slovník atributů nad stejným OTLP (`openinference.span.kind` LLM/TOOL/AGENT/…, `llm.token_count.*`, `session.id`,
`user.id`, `evaluation.*`). Spec bez čísla verze (main @f248e09). Převod: Python `OPENINFERENCE_ENABLE_GENAI_SEMCONV`
(default False) = dual-write; JS `@arizeai/openinference-genai` SpanProcessor GenAI → OI. **V OTEL Collectoru žádný
hotový procesor.** Používá Phoenix/AX, `dapr-agents` (dual), `openinference-instrumentation-claude-agent-sdk`
(AGENT span per `query()`, TOOL child spany přes hooky). **agentgateway OI jako default nepoužívá** – `gen_ai.*`;
OI jen přes `tracing.fields.add` (příklad `examples/llm-telemetry/tracing/phoenix.yaml`).

## C. Claude Code CLI 2.1.309 a Agent SDK 0.2.173

- **Metriky:** `claude_code.cost.usage` (USD), `token.usage` (input|output|cacheRead|cacheCreation; `input` **bez** cache –
  opak semconv a gateway), `session.count`, `code_edit_tool.decision`, atributy `model`, `agent.name`, `mcp_tool.name`
  (redigované bez `OTEL_LOG_TOOL_DETAILS`).
- **Eventy (OTLP logs):** `api_request` (`cost_usd`, tokeny vč. cache, `request_id`), `tool_decision` (`tool_use_id`,
  `decision`), `tool_result`, `api_error`, `safety_event`, `hook_*`, `subagent_completed`; korelace `prompt.id`, `message.uuid`.
- **Traces (beta):** `claude_code.interaction` → `llm_request` (`gen_ai.request.model`, `agent_id`, tokeny, `gen_ai.response.id`),
  `tool` (`gen_ai.tool.call.id`), `hook`; subagenti vnořeni. Obsah redigovaný bez bran `OTEL_LOG_*`.
- **Propagace:** inbound `TRACEPARENT` z env (jen SDK / `-p`); outbound `traceparent` na API a HTTP MCP **jen pro Anthropic
  URL** nebo s `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`; `traceresponse` z API jako span link; Bash subprocesy dědí.
  **Agent SDK sám žádnou telemetrii neemituje**; hooky nesou `session_id`, `agent_id`, `tool_use_id`; `ResultMessage` nese
  `total_cost_usd`, `usage`, `model_usage`.
- Atribuční hlavičky k gateway: `x-claude-code-session-id|agent-id|parent-agent-id|request-class|agent-type|prompt-id`,
  `x-client-request-id` (G1: agentgateway propouští, LiteLLM zahazuje).
- Identita koncového uživatele: per `query()` `OTEL_RESOURCE_ATTRIBUTES` (`enduser.id`); vestavěné `user.*` = credential služby.
- `.claude/settings.json` OTEL proměnné **ignoruje** (jen managed/user/shell).

## D. Dapr 1.18 a Dapr Agents 1.0.9

- `Configuration.spec.tracing`: **`samplingRate` default 0.0001** (1 z 10 000!); OTLP http/grpc nebo Zipkin; W3C
  `traceparent` HTTP, `grpc-trace-bin` gRPC, CloudEvents nesou `traceparent` (ne při `rawPayload`). Mezi hopy aplikace
  přenáší hlavičky sama. Zpráva bez kontextu nemá span (opraveno až 1.19).
- Workflow: parent span per instance, child spany aktivit; **aktivita nemá přístup k trace kontextu** → `dapr-agents`
  `extract_otel_context()` / `restore_otel_context()` přes vstup workflow.
- `DaprAgentsInstrumentor`: obaluje tool executor, workflow runner, chat klienty, `DurableExecutorMixin` (cesta
  `ClaudeAgentExecutor`), + httpx a gRPC instrumentace; **dual semconv** OI + `gen_ai.*` (`invoke_agent`, `execute_tool`,
  `gen_ai.usage.*`, `session.id`, `workflow.instance_id`). Span `invoke_agent` aktivní při běhu `ClaudeSDKClient` →
  SDK injektuje `TRACEPARENT`. **Neměřeno.**
- Metriky: Prometheus sidecar `:9090`; workflow histogramy (docs 1.19; pro 1.18 neověřeno).

## E. agentgateway 1.6.0

- `config.tracing`: `otlpEndpoint`, `otlpProtocol`, `fields.add` (CEL, stejný kontext jako logging: `jwt.sub`, `extauthz.*`,
  `request.headers`), **`randomSampling` default false**, **`clientSampling` default true**; per-policy `frontendPolicies.tracing`
  (`service.name`, `filter`, `parentNotSampled`).
- Semconv `gen_ai.*`: `gen_ai.provider.name`, `request/response.model`, `usage.input_tokens` (**vč. cache**),
  `usage.cache_creation.input_tokens`, `cache_read.input_tokens`, `output_tokens`, `reasoning_tokens` (nestandardní název).
  HTTP atributy stabilní semconv. Obsah `llm.prompt|completion|toolCalls` opt-in CEL.
- Metriky: `agentgateway_gen_ai_client_token_usage` (label **`gen_ai_system`** – starý název), **`agentgateway_gen_ai_client_cost`**
  (USD z katalogu), `agentgateway_cost_catalog_lookups_total`; CEL `llm.cost.*`, `llm.providerInputTokens`.
- Propagace k upstreamu potvrzena v kódu (`TraceParent::from_request` → `new_span()` → `insert_header`); gateway vrací
  klientovi původní `traceparent` v odpovědi. MCP: child span `mcp.method.name` + `gen_ai.tool.name`, `traceparent` do
  hlaviček **i `_meta`** (i pro stdio upstreamy).

## F. MCP a A2A SDK

- MCP spec 2026-07-28 (SEP-414): `traceparent`, `tracestate`, `baggage` jsou rezervované neprefixované klíče v `_meta`.
- **MCP Python SDK v2.3** (2026-10-02): OTEL default on (jen `opentelemetry-api`, no-op bez SDK); server span
  `{method} {target}`, `execute_tool` + `gen_ai.tool.name`; klient injektuje kontext do `_meta`. Bez argumentů, bez `mcp.session.id`.
- **MCP TypeScript SDK v2.3.1**: jen konstanty, žádná OTEL závislost.
- **A2A v1.0.1**: tracing jen v `enterprise-ready.md` jako „should“; `a2a-python` 1.2.3 dekorátory, extra `telemetry`,
  **žádná extrakce/injekce** hlaviček; žádné `gen_ai.*`.

## G. Anthropic API

- `metadata.user_id` je pro detekci zneužití; **ve span referenci se neobjevuje**.
- **OpenTelemetry for the Claude API (beta):** serverové spany (`service.name: claude-platform`) `anthropic.messages.create`
  → `anthropic.model_request`, `anthropic.tool_use|mcp_tool_use`, `anthropic.compaction`; parent = `traceparent` requestu;
  doručení do telemetry destination (Admin API `POST /v1/organizations/telemetry_destinations`, beta hlavička
  `telemetry-destinations-2026-08-11`, OTLP/HTTP, `metadata_only` | `content`, best-effort). Jen Claude Platform
  a Claude Platform on AWS; **Azure Foundry ne**.

## Tok spanů

```mermaid
sequenceDiagram
    autonumber
    participant UI as AG-UI klient
    participant ORC as Orchestrátor (Dapr sidecar + Dapr Agents)
    participant SDK as Claude Agent SDK
    participant CLI as Claude Code CLI
    participant GW as agentgateway 1.6
    participant API as Model
    participant MCP as MCP server
    UI->>ORC: HTTP traceparent
    Note over ORC: Dapr span; Workflow aktivita bez kontextu → dapr-agents restore
    ORC->>SDK: invoke_agent span aktivní
    SDK->>CLI: env TRACEPARENT (SDK ≥ 0.1.60)
    Note over CLI: claude_code.interaction → llm_request / tool (beta, 3 env)
    CLI-->>GW: traceparent jen s CLAUDE_CODE_PROPAGATE_TRACEPARENT=1
    CLI->>GW: x-claude-code-session-id / agent-id vždy
    Note over GW: SERVER span, gen_ai tokeny + cost; clientSampling
    GW->>API: child traceparent
    Note over API: Claude Platform: anthropic.messages.create do telemetry destination (beta); Foundry: nic
    GW->>MCP: child span + traceparent v HTTP i _meta
    Note over MCP: Python SDK v2: execute_tool default on; TS SDK: nic
```

## Tabulka komponent

| Komponenta | Emituje | Semconv | traceparent in / out | Identita / cena |
|---|---|---|---|---|
| Claude Code CLI 2.1.309 | metrics, logs/events, **traces beta** | `claude_code.*` + část `gen_ai.*` | in: env (SDK/`-p`); out: jen Anthropic URL nebo `PROPAGATE_TRACEPARENT=1` | `session.id`, `user.*`, `agent_id`, `cost_usd`, tokeny (input bez cache) |
| Claude Agent SDK 0.2.173 | nic | – | out: `TRACEPARENT` do CLI env | hooky `session_id`, `agent_id`, `tool_use_id`; `ResultMessage` cost |
| Dapr 1.18 | traces, metrics, logs | OTEL bez gen_ai | HTTP/gRPC/CloudEvents; workflow aktivity ne; sampling 0.0001 | app-id |
| Dapr Agents 1.0.9 | traces | OI + `gen_ai.*` dual | serializace přes workflow hranici; httpx/gRPC | `gen_ai.agent.name`, `session.id`, tokeny |
| agentgateway 1.6.0 | traces, metrics, JSON logs | `gen_ai.*` | in parse; out nový child; MCP i `_meta` | `jwt.sub`, `extauthz.*`, `llm.cost.*`, cache tokeny |
| Claude Platform API (beta) | traces push | `gen_ai.*` + `anthropic.*` | in parent; out `_meta` k MCP | org/workspace/request id; tokeny; bez `user_id` |
| MCP Python SDK 2.3 | traces server+client | MCP semconv | `_meta` | – |
| MCP TS SDK 2.3.1 | nic | – | passthrough | – |
| a2a-python 1.2.3 | spany bez propagace | generické | žádná | – |

## Co ověřit dál
- [ ] **Harness O1:** `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` přes agentgateway (mock zachytí `traceparent` z CLI) – doplnit do G1 A1.
- [ ] Dapr Agents + `ClaudeAgentExecutor` end-to-end (SDK injekce → CLI child span) – neměřeno.
- [ ] agentgateway `tracing.fields.add` s `jwt.sub` na spanu (I2 měřil jen logy).
- [ ] AG-UI spec – trace pole.
- [ ] Stav SIG GenAI a první release `semantic-conventions-genai`; návrh A2A semconv (Issues nedostupné).

## Changelog
- 2026-10-23: první verze z rešerše (kolo 1).
