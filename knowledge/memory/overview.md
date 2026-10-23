---
tema: Mapa vrstvy paměti a znalostí agentů
naposledy_overeno: 2026-10-23
zralost: n/a (přehled)
primarni_zdroje:
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
  - https://code.claude.com/docs/en/memory
  - https://docs.dapr.io/developing-applications/building-blocks/conversation/
  - https://modelcontextprotocol.io/specification/2026-07-28/server/resources
---

# Mapa paměti a znalostí

Kontext: **paměť je firemní, ne agentní.** Vrstva navazuje na rozhodnuté komponenty: stav běhu drží Dapr,
epizodická data vznikají v ClickHouse, oprávnění řeší OPA, identita Keycloak/SPIRE, nástroje jdou přes MCP
a agentgateway. Kritéria v [kriteria.md](kriteria.md).

## Čtyři druhy paměti v platformě

```mermaid
flowchart LR
    AG["Agent<br/><i>Claude Agent SDK</i>"]
    AG -->|"stav běhu"| WORK[("Pracovní<br/><i>Dapr Workflows,<br/>DaprSessionStore</i>")]
    AG -->|"MCP resources / tools"| MEM["Paměťový MCP server<br/><i>PEP: tenant, role, původ</i>"]
    MEM --> SEM[("Sémantická<br/><i>fakta s původem a datem</i>")]
    MEM --> PROC[("Procedurální<br/><i>runbooky, ADR, skilly, kód</i>")]
    MEM --> EPI[("Epizodická<br/><i>destilace běhů</i>")]
    TR[("ClickHouse<br/><i>traces, HITL verdikty</i>")] -->|"destilace"| EPI
    OPA["OPA"] -.->|"kdo smí číst / psát"| MEM
    HITL["Člověk"] -.->|"schválení zápisu do sdílené paměti"| MEM
    GW["agentgateway"] -.->|"embeddingy"| MEM
```

## Široké síto – kolo 1

*(doplní se z rešerše 2026-10-23)*

## Nativní schopnosti a standardy

*(doplní se z rešerše 2026-10-23)*

## Model původu a životní cyklus

*(doplní se z rešerše 2026-10-23)*

## Co ověřit dál

- [ ] Síto kolo 1 – memory frameworky, vektorové a grafové DB, licence.
- [ ] Co dává Claude (memory tool, CLAUDE.md, kompakce), Dapr (state, Conversation API), MCP (resources) a OTEL (memory spany).
- [ ] Model původu, izolace tenantů, memory poisoning, výmaz (GDPR čl. 17) – metodika.

## Changelog
- 2026-10-23: první verze – kostra, čtyři druhy paměti, otevřeno síto.
