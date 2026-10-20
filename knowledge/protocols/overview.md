---
tema: Mapa AI protokolů pro multiagentní platformy
naposledy_overeno: 2026-10-20
zralost: n/a (přehled)
primarni_zdroje:
  - https://a2a-protocol.org/latest/
  - https://modelcontextprotocol.io/specification/2026-07-28
  - https://docs.ag-ui.com/introduction
  - https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/
---

# Mapa protokolů

## Vrstvy

| Vrstva | Protokol | Směr komunikace | Zralost (10/2026) |
|---|---|---|---|
| Agent ↔ nástroje / data | **MCP** | agent → zdroje, nástroje, API | stable (spec 2026-07-28) |
| Agent ↔ agent | **A2A** | agent ↔ vzdálený agent | v1.0.1 stable, v1.1 ve vývoji; Foundry A2A v1.0 GA |
| Agent ↔ frontend (runtime) | **AG-UI** | backend ↔ uživatelská aplikace, event stream | spec 1.0 (2026-09-17), ekosystém v migraci, MAF stále na 0.x |
| Deklarativní popis UI | **A2UI** | agent popisuje UI, klient vykresluje | v0.9.1 produkční, v1.0 RC (renderery v1.0 jen plánované) |
| UI přímo z MCP serveru | **MCP Apps** (rozšíření MCP) | MCP server → hostitel (Claude, ChatGPT, VS Code, M365 Copilot…) | spec 2026-01-26; TS `ext-apps` 2.0.3; Python SDK v2 má extension API |

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
- **A2UI vs MCP Apps.** A2UI: agent posílá deklaraci, klient vykresluje vlastními komponentami z katalogu. MCP Apps: server dodává interaktivní UI (iframe), hostitel ho vloží do konverzace. Nejsou konkurenti – Google a autoři MCP Apps publikovali tři kombinační vzory (A2UI over MCP, MCP Apps in A2UI, A2UI in MCP Apps), viz `a2ui.md`.

## Pozn. Adam: architektonické doporučení (výchozí hypotéza)

- MCP je dnes jediná vrstva, na kterou lze stavět bez výhrad.
- A2A, AG-UI a A2UI zapouzdřit za vlastní abstrakci (adaptér), aby šly vyměnit.
- Pro UI rozhodnout podle toho, kdo vlastní frontend: vlastní aplikace → AG-UI + A2UI (MCP Apps jen jako sandboxovaná výjimka uvnitř A2UI surface); UI uvnitř cizího hostitele (Claude, ChatGPT, M365 Copilot) → MCP Apps.
- A2UI zatím jen v0.9.1 – v1.0 RC bez rendererů do produkce nepatří.

## Vztah k frameworkům

Protokoly jsou **švy, na kterých stojí vyměnitelnost frameworku**. Když hranice mezi
orchestrační vrstvou a agenty stojí na A2A, MCP a AG-UI, je výměna orchestrátoru prací
na platformní vrstvě, ne přepisem agentů. Viz [`../frameworks/overview.md`](../frameworks/overview.md).

## Další protokoly k prozkoumání

- AP2 (Agent Payments Protocol) – v0.2.0 (2026-04-28, „Human Not Present“ platby), téhož dne darováno
  FIDO Alliance (Agentic Authentication TWG); rozšíření A2A, vzorky používají x402. Pro enterprise mimo
  commerce okrajové; zajímavé jako vzor „mandátů“ (podepsaný uživatelský záměr) pro governance agentů.
  Zdroj: github.com/google-agentic-commerce/AP2/releases, ověřeno 2026-10-20.
- ~~Open-JSON-UI~~ – prověřeno 2026-10-20: žádný první-party zdroj OpenAI, jen CopilotKit docs; vyřazeno.
- Agentic AI Foundation (AAIF) – kam spadají MCP a A2A z hlediska governance

## Changelog
- 2026-09-23: první verze.
- 2026-10-20: AG-UI 1.0, A2A v1.0.1 + Foundry GA, A2UI v1.0 stále RC + přesun repa, MCP Apps hostitelé
  a Python SDK, AP2 a Open-JSON-UI vyhodnoceny.
