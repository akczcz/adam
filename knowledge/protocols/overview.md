---
tema: Mapa AI protokolů pro multiagentní platformy
naposledy_overeno: 2026-09-23
zralost: n/a (přehled)
primarni_zdroje:
  - https://a2a-protocol.org/latest/
  - https://modelcontextprotocol.io/specification/2026-07-28
  - https://docs.ag-ui.com/introduction
  - https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/
---

# Mapa protokolů

## Vrstvy

| Vrstva | Protokol | Směr komunikace | Zralost (9/2026) |
|---|---|---|---|
| Agent ↔ nástroje / data | **MCP** | agent → zdroje, nástroje, API | stable (spec 2026-07-28) |
| Agent ↔ agent | **A2A** | agent ↔ vzdálený agent | v1.0 stable, adopce v počátcích |
| Agent ↔ frontend (runtime) | **AG-UI** | backend ↔ uživatelská aplikace, event stream | early / community-driven |
| Deklarativní popis UI | **A2UI** | agent popisuje UI, klient vykresluje | v0.9.x produkční, v1.0 RC |
| UI přímo z MCP serveru | **MCP Apps** (rozšíření MCP) | MCP server → hostitel (Claude, ChatGPT…) | oficiální rozšíření MCP |

Jednou větou: MCP = nástroje, A2A = ostatní agenti, AG-UI = kanál k uživateli,
A2UI = formát, kterým agent popíše rozhraní.

## Jak do sebe zapadají

```
Uživatel
   │  AG-UI (event stream: zprávy, stav, tool calls, human-in-the-loop)
   ▼
Frontend agent ──A2A──► Vzdálený agent (jiný tým / framework / firma)
   │                        │
   │ MCP                    │ MCP
   ▼                        ▼
Nástroje, data           Nástroje, data

A2UI = payload (deklarativní UI), který může cestovat přes A2A i AG-UI
MCP Apps = alternativní cesta UI, kde UI dodává přímo MCP server
```

## Časté záměny

- **A2UI ≠ AG-UI.** A2UI je *formát* (co vykreslit), AG-UI je *transport/runtime* (jak to dostat k uživateli a zpět).
- **A2A vs MCP.** MCP volá nástroj s definovaným vstupem/výstupem; A2A deleguje *úkol* autonomnímu agentovi, který nesdílí svou paměť ani nástroje.
- **A2UI vs MCP Apps.** A2UI: agent posílá deklaraci, klient vykresluje vlastními komponentami z katalogu. MCP Apps: server dodává interaktivní UI, hostitel ho vloží do konverzace.

## Pozn. Adam: architektonické doporučení (výchozí hypotéza)

- MCP je dnes jediná vrstva, na kterou lze stavět bez výhrad.
- A2A, AG-UI a A2UI zapouzdřit za vlastní abstrakci (adaptér), aby šly vyměnit.
- Pro UI rozhodnout podle toho, kdo vlastní frontend: vlastní aplikace → AG-UI + A2UI; UI uvnitř cizího hostitele (Claude, ChatGPT) → MCP Apps.

## Další protokoly k prozkoumání

- AP2 (Agent Payments Protocol), X42 – platby a governance agentů
- Open-JSON-UI – alternativní deklarativní UI formát
- Agentic AI Foundation (AAIF) – kam spadají MCP a A2A z hlediska governance

## Changelog
- 2026-09-23: první verze.
