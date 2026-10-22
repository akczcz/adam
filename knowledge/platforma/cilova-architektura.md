---
tema: Cílová architektura autonomní multiagentní platformy – živý soubor rozhodnutí
naposledy_overeno: 2026-10-22
zralost: experimental
primarni_zdroje:
  - https://github.com/akczcz/adam/tree/main/knowledge
---

# Cílová architektura

Živý soubor. Každá prověřená vrstva sem vloží **jedno rozhodnutí** se zdůvodněním a riziky,
která Adam vědomě přijímá. Prázdné řádky jsou záměrně prázdné – označují, co ještě není rozhodnuto.
Detail a zdroje jsou vždy ve složce dané vrstvy, tady je jen výsledek.

## Rozhodnutí po vrstvách

| Vrstva | Rozhodnutí | Datum | Přijatá rizika | Detail |
|---|---|---|---|---|
| Agent ↔ nástroje | **MCP** jako jediná hranice k nástrojům a datům | 2026-09-23 | – | [`../protocols/mcp.md`](../protocols/mcp.md) |
| Agent ↔ agent | **A2A**, ale za vlastním adaptérem (vyměnitelné) | 2026-09-23 | A2A v1.1 ve vývoji, SDK verze se liší per framework | [`../protocols/a2a.md`](../protocols/a2a.md) |
| Agent ↔ uživatel | **AG-UI** (vlastní frontend) + **A2UI** jako payload; MCP Apps jen uvnitř cizího hostitele | 2026-09-23 | AG-UI 1.0 čerstvé, ekosystém v migraci; A2UI bez v1.0 rendererů | [`../protocols/overview.md`](../protocols/overview.md) |
| Agentní smyčka | **Claude Agent SDK** | 2026-10-21 | `claude-agent-sdk` pinnutý na 0.2.x v Dapr Agents | [`../frameworks/overview.md`](../frameworks/overview.md) |
| Orchestrace a durable execution | **Dapr Agents** (`ClaudeAgentExecutor` + `DaprSessionStore`) nad Dapr Workflows | 2026-10-21 | Bus factor 1, žádná support policy, A2A/AG-UI nepodporuje – nutný vlastní A2A server; obnovení během nástroje at-least-once → idempotency key | [`../frameworks/dapr-agents.md`](../frameworks/dapr-agents.md) |
| Model gateway a FinOps | **agentgateway** (LF, Apache-2.0, nativní `/v1/messages`, USD rozpočty v OSS) – navrženo k rozhodnutí po harnessu G1 (21/21), LiteLLM záloha | 2026-10-22 (návrh, čeká na potvrzení a live L1) | bus factor 1 (51 % commitů), bez CLA/DCO, rozpočty jen per API klíč (klíč per agent/tým), persistence rozpočtů mezi replikami neověřena | [`../gateway/overview.md`](../gateway/overview.md) |
| Identita, autorizace, governance | – | – | – | – |
| Observabilita a evaluace | – | – | – | – |
| Paměť a znalosti | – | – | – | – |
| Sandboxy a pracovní prostředí | – | – | – | – |
| Organizační vrstva | *(hypotéza níže)* | – | – | – |

## Pracovní hypotéza organizační vrstvy

**Pozn. Adam:** tohle není rozhodnutí, je to hypotéza, aby technické vrstvy měly proti čemu
formulovat požadavky. Přepíše se, až se vrstva otevře.

Virtuální IT firma = sada **rolí** (agentů) a **procesů** (workflow), kde každý proces má
definované vstupy, výstupy, schvalovací body a vlastníka.

| Role | Co dělá | Co potřebuje od technických vrstev |
|---|---|---|
| Account / zadání | Přijme požadavek, upřesní ho s člověkem, založí zakázku | AG-UI (dialog), paměť zákazníka, identita zadavatele |
| Architekt | Navrhne řešení, rozhodne o stacku, odhadne cenu | Paměť (co už firma umí), gateway (cena modelů), sandbox (prototyp) |
| Vývojář | Implementuje, testuje, otevírá PR | Sandbox (kód, git, CI), MCP (repo, issue tracker), durable execution (dlouhé běhy) |
| Reviewer / QA | Kontroluje kvalitu, spouští evaly | Observabilita a evaluace, oprávnění jen pro čtení + komentáře |
| Provoz / SRE | Nasazuje, hlídá, eskaluje incidenty | MCP (cloud API), identita (produkční oprávnění jen po schválení), observabilita |
| Governance / compliance | Audituje, hlídá rozpočty a AI Act | Identita a audit log, FinOps data, evaluace |
| Člověk | Schvaluje na definovaných bodech, řeší eskalace | AG-UI, durable HITL (dny až týdny) |

Z hypotézy plynou tři požadavky, které se zatím opakují napříč vrstvami:

1. **Každá akce agenta má identitu, rozpočet a stopu.** Identita (kdo), gateway (za kolik),
   observabilita (co a proč). Žádná z těch tří vrstev to nesmí řešit jen pro sebe.
2. **Hranice autonomie jsou v procesu, ne v promptu.** Schvalovací body drží durable vrstva
   (Dapr Workflows), ne instrukce modelu.
3. **Paměť je firemní, ne agentní.** Co se agent naučí o zákazníkovi nebo o kódu, patří firmě
   a řídí se oprávněním, ne instancí agenta.

## Changelog
- 2026-10-22: gateway – harness G1 změřen, agentgateway navržen k rozhodnutí, LiteLLM záloha.
- 2026-10-22: první verze – přeneseno pět rozhodnutí z `protocols/` a `frameworks/`, prázdné řádky
  pro zbylé vrstvy, pracovní hypotéza organizační vrstvy.
