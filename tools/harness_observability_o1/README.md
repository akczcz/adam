# Harness O1: souvislý trace orchestrátor → Claude Code → agentgateway → model, do ClickHouse

Ověřuje tvrzení z `knowledge/observability/standardy.md`: trace je souvislý, když se zapnou vypínače
v Claude Code (`CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_TRACES_EXPORTER`,
**`CLAUDE_CODE_PROPAGATE_TRACEPARENT`**), a že navržený stack z `overview.md` – **OTEL Collector contrib**
(`gen_ai_normalizer`, `redaction`) → **ClickHouse** – data skutečně unese bez vendor backendu.

Celý řetěz běží lokálně bez Dockeru: ClickHouse 26.8 LTS (statická binárka), otelcol-contrib 0.163.2,
agentgateway 1.6.0, mock model z `harness_gateway_g1/`, orchestrátor = tento harness s OTEL SDK.

## Tvrzení

| # | Tvrzení | Kritérium |
|---|---|---|
| A1 | Claude Agent SDK přes agentgateway dokončí turn s MCP nástrojem | `is_error=false`, nástroj proveden |
| O1g | Mock model dostal `traceparent` se stejným trace id (CLI → gateway → model) | všechny `/v1/messages` requesty |
| O1a | Spany orchestrátoru i agentgateway v ClickHouse pod jedním `TraceId` | dotaz `otel.otel_traces` |
| O1b | Claude Code CLI emituje vlastní spany do stejného trace (beta) | service `claude-code` |
| O1c | Gateway span nese `gen_ai.usage.*` vč. cache tokenů, `session.id`, cost | atributy spanu |
| O1d | Gateway spany mají rodiče uvnitř trace (CLI `llm_request`), nejsou osiřelé | `ParentSpanId` ∈ trace |
| O1e | Redaction v Collectoru zamaskuje `sk-…` v atributu | hodnota `****`, žádný únik |
| O1f | `gen_ai_normalizer` přepíše OpenInference `llm.token_count.*` na `gen_ai.usage.*` | probe span |
| O1h | CLI metriky a eventy (`cost.usage`, `token.usage`, `api_request`, `tool_decision`) přes OTLP s `enduser.id` | file exporter |
| O1i | Dapr Workflow v řetězu | **SKIP** – bez Dapr lokálně |

## Výsledek 2026-10-23: 9 PASS, 0 FAIL, 1 SKIP

| Služba | Spany v trace | Příklad |
|---|---|---|
| harness-orchestrator | 5 | `invoke_agent harness-ticket-agent`, MCP `initialize`, `notifications/initialize` |
| **claude-code** (CLI 2.1.308, beta traces) | 10 | `claude_code.interaction` → `claude_code.llm_request`, `claude_code.tool` → `.blocked_on_user`, `.execution` |
| agentgateway 1.6.0 | 6 | `POST /v1/messages` s `gen_ai.provider.name`, `gen_ai.usage.cache_creation.input_tokens` 2048, `cache_read.input_tokens` 4096, `gen_ai.conversation.id`; rodič = `claude_code.llm_request` |

Redaction: `harness.redaction_probe` dorazil jako `****`. Normalizer: `llm.token_count.prompt=123` → `gen_ai.usage.input_tokens=123`
(originály ponechány, `remove_originals: false`). Metriky `claude_code.cost.usage`, `token.usage`, `session.count`; eventy
`api_request`, `tool_decision`, `tool_result`, `user_prompt` s `enduser.id=alice` z `OTEL_RESOURCE_ATTRIBUTES`.

## Pasti

- `gen_ai_normalizer` vyžaduje `sources: [{name: openinference}, {name: openllmetry}]` – prázdný config neprojde.
- ClickHouse z GitHub release (`clickhouse-common-static-<ver>-amd64.tgz`): binárka je `usr/bin/clickhouse`;
  `builds.clickhouse.com` nebyl z prostředí dostupný. Dodávaný config má `send_crash_reports` zapnuté – zde vypnuto.
- Agent SDK s extra `[otel]` injektuje `TRACEPARENT` do CLI sám, pokud je aktivní span; CLI pak s
  `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` posílá `traceparent` na gateway a vytváří **vlastní child spany** (s OTLP exportérem;
  s `console` exportérem v G1 vlastní span nevznikl).
- `OTEL_EXPORTER_OTLP_PROTOCOL` nemá v Claude Code default – bez něj nic neodejde.
- V hostovaném prostředí (claude.ai cloud) CLI ignoruje `ANTHROPIC_API_KEY` → `CLAUDE_CODE_OAUTH_TOKEN` (viz G1 README).

## Spuštění

```bash
cd tools/harness_observability_o1
uv venv && uv pip install -p .venv/bin/python httpx fastapi uvicorn pyyaml "claude-agent-sdk[otel]" opentelemetry-sdk opentelemetry-exporter-otlp-proto-http clickhouse-connect
export CLICKHOUSE_BIN=/path/clickhouse OTELCOL_BIN=/path/otelcol-contrib AGENTGATEWAY_BIN=/path/agentgateway
.venv/bin/python harness.py
```

Porty: 8123/9000 (ClickHouse), 4317/4318 (Collector), 9777 (mock), 4100 (gateway), 19001–19002. Data ClickHouse
v `data/` (mazána při každém běhu), spany navíc v `logs/spans.jsonl`.
