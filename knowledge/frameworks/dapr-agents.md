---
tema: Dapr Agents – durable agenti nad Dapr Workflow
naposledy_overeno: 2026-09-28
zralost: GA 1.0.x, ale bez support policy a s breaking change v patch releasu
primarni_zdroje:
  - https://github.com/dapr/dapr-agents
  - https://pypi.org/pypi/dapr-agents/json
  - https://raw.githubusercontent.com/dapr/dapr-agents/main/CONTRIBUTING.md
  - https://github.com/aaif/project-proposals/issues/34
  - https://raw.githubusercontent.com/diagridio/python-ai/main/LICENSE.md
  - https://docs.dapr.io/developing-ai/agent-integrations/
  - https://github.com/dapr/dapr/issues/8703
  - https://docs.dapr.io/concepts/dapr-services/scheduler/
  - https://docs.dapr.io/operations/support/support-release-policy/
---

# Dapr Agents

## Účel
Python framework pro agenty, jejichž běh je trvalý – staví na durable execution Dapru
(workflow jako event-sourced aktoři). Stav žije v konfigurovaném Dapr state storu,
ne uvnitř frameworku.

## Aktuální stav
- Repozitář `dapr/dapr-agents` vznikl **2025-01-02**, GA **v1.0.0 2026-03-19**, k 2026-09-28 **v1.0.6**.
- Apache-2.0, **DCO, ne CLA**, pod Dapr / CNCF / Linux Foundation.
- PyPI metadata licenci **deklarují správně** včetně OSI classifieru.

## Klíčové koncepty
- **DurableAgent** – smyčka nad Dapr Workflow, event sourcing, replay po restartu.
- **Hooks a HITL** – `before_tool_call` vrací `RequireApproval(...)`; workflow se zastaví
  na `wait_for_external_event`, pending approvals se ukládají do state storu.
- **State store jako tvoje volba** – 28 providerů (Postgres, Redis, MySQL, Cassandra…),
  formát je dokumentovaný append-only JSON log.
- **Sidecar model** – `daprd` vedle každého podu, control plane zvlášť.

## Místo v architektuře
Řeší **agentní smyčku a durable execution**, částečně orchestraci. **Neřeší protokolovou
hranici ven ani UI.**

## Zralost a rizika

| Osa | Stav |
|---|---|
| Licence | ✅ Apache-2.0 |
| Governance | ✅ **DCO**, copyright rozptýlený, LF/CNCF |
| Stupeň zralosti | ❌ **CNCF Graduated se na sub-projekt nevztahuje** – Dapr graduoval 2024-10-30, repo vzniklo 2025-01-02 |
| Support policy | ❌ **žádná** – Daprova politika (3 verze, 9měsíční okno) platí pro runtime, ne pro sub-projekt |
| Stabilita API | ❌ **breaking change v patchi** – v1.0.1 odstranila veřejnou třídu `Agent`, měsíc po GA |
| Bus factor | ⚠️ **2** – 2 ze 3 maintainerů z Diagridu, top 3 lidé ≈ 90 % ne-botových commitů |
| **A2A** | ❌ **nepodporuje** – [dapr/dapr#8703](https://github.com/dapr/dapr/issues/8703) uzavřeno jako *not planned* (2025-11-18) |
| **AG-UI** | ❌ nepodporuje |
| MCP klient | ✅ nativně (stdio / SSE / streamable HTTP); Dapr 1.18 přidal MCP jako building block |
| MCP server | ❔ nedoloženo |
| Trvalost stavu | ✅ **nejsilnější v poli** – stav ve tvém state storu, dokumentovaný formát |
| Air-gap | ✅ doloženo (`dapr init --from-dir`, `--image-registry`) |
| Phone-home | ✅ nenalezeno (bez plného auditu závislostí) |
| Model gateway | ✅ šev otevřený – `base_url` vede na vLLM i LiteLLM proxy; LiteLLM je přímá závislost |
| Licence v balíčcích | ⚠️ deklarovaná, ale chybí `license_expression` (SPDX) a classifier je `Development Status :: 2 - Pre-Alpha` na verzi 1.0.6 |

### Provozní cena sidecaru
- Latence: **+1,4 ms P90, +2,1 ms P99** při 1000 req/s – proti latenci volání modelu šum.
- Skutečná cena: **~15 podů control plane** (3 repliky × 5 komponent) + 250 Mi na agentní pod.
- **Scheduler je stavový a nelze ho přeškálovat**: *„scaling the Scheduler service replicas
  up or down is not possible without incurring data loss"* (embedded etcd). Drží reminders,
  které probouzejí pozastavená workflow, tedy i čekající HITL.
  → Pro produkt u zákazníka zvážit **externí etcd** a zálohování dle RPO.

### Zamítnutí v AAIF – co z toho plyne
Návrh na přesun pod Agentic AI Foundation (jako *Durable Agents*) podán **2026-06-02**,
hlasování TC uzavřeno 2026-09-03, **zamítnuto 2026-09-11**.

Odůvodnění TC je architektonicky důležitější než výsledek – jsou to tři nezávislá
potvrzení rizika „jak drahé je vzít stav jinam":

1. Záruky trvalosti jsou demonstrované **jen nad Dapr Workflow** – *„every guarantee it
   offers is currently expressed through Dapr Workflow"*.
2. **Rozhodující bod:** žádná jiná durable-execution komunita o to nestojí; deklarovaný
   Temporal provider nestačil.
3. Projekt *„reads more as an agent framework than as a substrate"*.

Governance ani security posture zpochybněné nebyly, adopce byla uznána. Resubmise je možná
bez čekací lhůty. **Sledovat, jestli přibude druhý durable backend** – je to přímý indikátor
ceny odchodu.

## Architektonické důsledky (Pozn. Adam)
- **Cena odchodu se láme na dvě úrovně.** Pryč od knihovny `dapr-agents` při zachování
  Dapr Workflow je levné – stav zůstává ve tvém storu. Pryč od Dapru celého je drahé,
  protože ztratíš durable execution, aktory, pub/sub i service invocation najednou.
- **Chybějící A2A a AG-UI je největší rozdíl proti kagentu.** Hranici si musíš postavit
  sám nad `a2a-sdk` vedle agenta. Paradoxně to snižuje lock-in – framework do hranice
  nemluví – ale zaplatíš prací.
- **Dapr Conversation API nepoužívat jako model gateway** – jediná `Stable` komponenta
  je `echo`. Gateway šev vést přes `base_url` na LiteLLM proxy.
- ⚠️ **Sousední BUSL past:** viz třetí vzorec v [licencni-vzorce.md](licencni-vzorce.md).
  `dapr-agents` na `diagrid` nezávisí, ale dokumentace Dapru na něj ukazuje.
- **Nejzajímavější varianta, kterou to otevřelo:** Dapr Workflow jako *substrát pod cizí
  tenkou smyčkou* (Pydantic AI, OpenAI Agents SDK). Hotová integrace je pod BUSL, ale
  vlastní obal nad `dapr-ext-workflow` je Apache-2.0. Nejlepší poměr trvalost / nulová vazba.

## Otevřené otázky
- [ ] Právní posudek Diagrid BSL – vylučuje prahy 60 FTE / 15 M USD a zákaz komerční
      redistribuce balíčky `diagrid` i z vývoje, nebo jen z produkce?
- [ ] Odhadnout práci na vlastním obalu nad `dapr-ext-workflow` bez `diagrid`.
- [ ] Cena vlastního A2A serveru nad `a2a-sdk` vedle `AgentRunner.serve()`.
- [ ] Změřit harnessem: pozastavení HITL → restart clusteru → obnovení po 14 dnech.
      Dokumentace uvádí „seconds, hours, or days", **maximální horizont nikde není**.
- [ ] Kolik breaking changes bylo po GA celkem – doložen jeden, API diff neproveden.
- [ ] Složení týmů `@dapr/maintainers-dapr-agents` – není veřejné; seznam maintainerů
      pochází z návrhu psaného CTO Diagridu, tedy zainteresovanou stranou.
- [ ] Umí `dapr-agents` vystavit agenta *jako* MCP server?
- [ ] Síťový test air-gapped: potvrdit nulový egress (40+ tranzitivních závislostí).

## Changelog
- 2026-09-28: první verze; hloubková prověrka.
