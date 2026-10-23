---
tema: Mapa vrstvy observability a evaluace agentů
naposledy_overeno: 2026-10-23
zralost: n/a (přehled)
primarni_zdroje:
  - https://opentelemetry.io/docs/specs/semconv/gen-ai/
  - https://code.claude.com/docs/en/monitoring-usage
  - https://docs.dapr.io/operations/observability/
---

# Mapa observability a evaluace

Kontext: **průřezová vrstva** – odpovídá na „co se stalo“ (O1), „dělá to práci dobře“ (O2) a „kdy zasáhnout“ (O3).
Kritéria v [kriteria.md](kriteria.md). Navazuje na to, co už emitují zvolené komponenty: agentgateway (JSON log
s `jwt.sub` a `extauthz.*`, propagace `traceparent` jako child span – harness G1), OPA decision log (harness I2),
Dapr tracing, Claude Agent SDK hooky. Audit podle čl. 12 AI Act je **nosič** této vrstvy
([`../identity/regulace.md`](../identity/regulace.md), T2–T4).

## Tok dat

```mermaid
flowchart LR
    SDK["Claude Agent SDK<br/><i>hooky, usage</i>"] -->|OTLP| COL
    DAPR["Dapr sidecar<br/><i>W3C trace, metriky</i>"] -->|OTLP| COL
    GW["agentgateway<br/><i>spany gen_ai, cost, JSON log</i>"] -->|OTLP| COL
    OPA["OPA-Envoy<br/><i>decision log</i>"] -->|log| COL
    COL["OTEL Collector<br/><i>masking PII, routing per tenant</i>"]
    COL --> TR[("Traces")]
    COL --> ME[("Metriky")]
    COL --> LO[("Logy / audit")]
    TR --> EV["Evaluace<br/><i>trajektorie z trace, judge přes gateway, CI gate</i>"]
    ME --> AL["Alerty<br/><i>cena, smyčky, HITL, drift</i>"]
    AL -.->|stop| DUR["Dapr Workflow"]
```

## Široké síto – kolo 1

*(doplní se z rešerše 2026-10-23)*

## Standard na drátě a co emitují komponenty

Detail v [standardy.md](standardy.md). Pět věcí, které mění návrh (2026-10-23):

- **OTEL GenAI semconv je celé `Development`**, přesunuté do vlastního repa bez release; MCP semconv existuje, A2A ne.
  Stavět na něm lze, ale s vrstvou normalizace v Collectoru (`gen_ai.system` → `provider.name`, cache tokeny).
- **Trace se ve výchozím stavu přeruší mezi Claude Code a naší gateway**: CLI posílá `traceparent` jen na
  api.anthropic.com; nutné `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`. Traces CLI jsou beta za dalšími třemi env.
- **Dapr Workflow aktivity nemají trace kontext**; Dapr Agents to obchází serializací do vstupu workflow; Dapr
  `samplingRate` default 0.0001.
- **agentgateway je nejbohatší zdroj**: `gen_ai.*` spany, cache tokeny, cost USD metrika, `jwt.sub` a `extauthz.*`
  jako CEL pole, propagace k modelu i MCP (i do `_meta`).
- **Model na Azure Foundry žádné spany neposílá**; Claude Platform má beta serverové spany do telemetry destination.
  MCP Python SDK v2 má OTEL default on, TypeScript SDK nic, A2A SDK nepropaguje.

## Evaluace

*(doplní se z rešerše 2026-10-23)*

## Co ověřit dál

- [ ] Síto kolo 1 – backendy a LLM observability platformy.
- [x] ~~Stav OTEL GenAI semconv, co emitují komponenty, kde se trace přeruší~~ → [standardy.md](standardy.md), 2026-10-23.
- [ ] Evaluační frameworky pro trajektorie agentů, metodika pro role virtuální firmy.

## Changelog
- 2026-10-23: standardy – semconv Development, přerušení trace CLI → gateway, Dapr aktivity, Foundry bez spanů.
- 2026-10-23: první verze – kostra, tok dat, otevřeno síto.
