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

*(doplní se z rešerše 2026-10-23)*

## Evaluace

*(doplní se z rešerše 2026-10-23)*

## Co ověřit dál

- [ ] Síto kolo 1 – backendy a LLM observability platformy.
- [ ] Stav OTEL GenAI semconv, co emitují Claude Agent SDK / Dapr / agentgateway / MCP SDK, kde se trace přeruší.
- [ ] Evaluační frameworky pro trajektorie agentů, metodika pro role virtuální firmy.

## Changelog
- 2026-10-23: první verze – kostra, tok dat, otevřeno síto.
