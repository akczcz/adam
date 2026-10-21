---
tema: Dapr Agents – durable agenti nad Dapr Workflow
naposledy_overeno: 2026-10-21
zralost: GA 1.0.9, ale bez support policy, s breaking change v patch releasu a PyPI classifierem Pre-Alpha
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
  - https://github.com/dapr/dapr-agents/releases
  - https://github.com/dapr/dapr-agents/pull/809
  - https://raw.githubusercontent.com/dapr/dapr-agents/main/pyproject.toml
  - https://docs.dapr.io/reference/components-reference/supported-conversation/
---

# Dapr Agents

## Účel
Python framework pro agenty, jejichž běh je trvalý – staví na durable execution Dapru
(workflow jako event-sourced aktoři). Stav žije v konfigurovaném Dapr state storu,
ne uvnitř frameworku.

## Aktuální stav
- Repozitář `dapr/dapr-agents` vznikl **2025-01-02**, GA **v1.0.0 2026-03-19**, k 2026-10-20 **v1.0.9**
  (1.0.7 2026-10-02, 1.0.8 2026-10-08, 1.0.9 2026-10-09; v release notes žádný deklarovaný breaking change).
- Pin runtimu `dapr>=1.18.0rc0,<1.19.0`; **Dapr 1.19 je v RC** (rc.4 2026-10-16), GA si vyžádá nový release
  dapr-agents. MCP klient stojí na `mcp>=1.26.0,<2.0.0`, tedy na **1.x linii MCP SDK** – 2026-07-28 éra
  (stateless, MRTR) se ho netýká, dokud nepřejde na `mcp` 2.x (viz [`../protocols/mcp.md`](../protocols/mcp.md)).
- Apache-2.0, **DCO, ne CLA**, pod Dapr / CNCF / Linux Foundation.
- PyPI metadata licenci **deklarují správně** včetně OSI classifieru.

## Klíčové koncepty
- **DurableAgent** – smyčka nad Dapr Workflow, event sourcing, replay po restartu.
- **Hooks a HITL** – `before_tool_call` vrací `RequireApproval(...)`; workflow se zastaví
  na `wait_for_external_event`, pending approvals se ukládají do state storu.
- **State store jako tvoje volba** – 28 providerů (Postgres, Redis, MySQL, Cassandra…),
  formát je dokumentovaný append-only JSON log.
- **Sidecar model** – `daprd` vedle každého podu, control plane zvlášť.
- **Vyměnitelný executor** – smyčku agenta lze nahradit přes `AgentExecutorBase`; od 1.0.7 existuje
  first-party **`ClaudeAgentExecutor`** (viz níže).

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
| Bus factor | ❌ **zhoršuje se** – za 2026-09-28 až 10-20 je z 49 commitů 24 dependabot, **23 jeden člověk** (CasperGN), 2 ostatní; dřív top 3 ≈ 90 % ne-botových commitů, teď fakticky jeden |
| **A2A** | ❌ **nepodporuje** – [dapr/dapr#8703](https://github.com/dapr/dapr/issues/8703) uzavřeno jako *not planned* (2025-11-18) |
| **AG-UI** | ❌ nepodporuje |
| MCP klient | ✅ nativně (stdio / SSE / streamable HTTP); Dapr 1.18 přidal MCP jako building block |
| MCP server | ❌ **ne** – v knihovně žádný import `mcp.server` (grep tarballu `main`, 2026-10-20); agenta jako MCP server musíš obalit sám |
| Trvalost stavu | ✅ **nejsilnější v poli** – stav ve tvém state storu, dokumentovaný formát |
| Air-gap | ✅ doloženo (`dapr init --from-dir`, `--image-registry`) |
| Phone-home | ⚠️ **kód žádný, ale `posthog<8.0.0` je runtime závislost** – v `pyproject.toml` od 2025-07-07 (#139), v `dapr_agents/` ani nikde v repu **neimportovaný**, jen dependabot ho bumpuje. Mrtvá závislost, která do každého image instaluje analytický SDK – pro SBOM a air-gap review červená vlajka, i když nic neodesílá (ověřeno 2026-10-20) |
| Model gateway | ✅ šev otevřený – `base_url` vede na vLLM i LiteLLM proxy; LiteLLM je přímá závislost |
| Licence v balíčcích | ⚠️ deklarovaná, ale chybí `license_expression` (SPDX) a classifier je `Development Status :: 2 - Pre-Alpha` i na verzi 1.0.9 (2026-10-20) |

### Claude Agent SDK jako smyčka nad Dapr Workflow (od 1.0.7)
*Zdroj: PR [#809](https://github.com/dapr/dapr-agents/pull/809), merged 2026-10-01; ověřeno 2026-10-20.*

Extra `dapr-agents[claude]` instaluje `claude-agent-sdk>=0.2.159,<0.3.0`. `ClaudeAgentExecutor` nechá
reasoning loop na Claude Agent SDK a Dapr dodá trvalost: `DaprSessionStore` ukládá Claude transcript
po chunkách do Dapr state storu (ETag, dedup podle `uuid`, sliding TTL), takže **retried activity nebo jiný
pod obnoví tutéž Claude session**. SDK zprávy se mapují na `AgentEvent` (`text_delta`, `tool_call`,
`tool_result`, `session`, `complete` s cost a usage, `error`); hooks a `RequireApproval` fungují stejně
jako u nativní smyčky. 1.0.9 opravuje resume lokální CLI session.

**Pozn. Adam:** to je přesně varianta „Dapr Workflow jako substrát pod cizí tenkou smyčkou“, kterou jsem
si dřív musel představovat jako vlastní obal – teď je first-party, Apache-2.0 a **pro Anthropic stack**.
Dvě výhrady: `claude-agent-sdk` je 0.2.x s pinem `<0.3`, a maintainer je tentýž jeden člověk jako u zbytku
repa. Ale ukazuje, že executor šev je reálný, ne jen deklarovaný.

### Harness: restart uprostřed schvalování (2026-10-21, změřeno)
*Zdroj: `tools/harness_dapr_claude/`, výsledky v `results/all-20261021T073302Z.json`; dapr-agents 1.0.9,
claude-agent-sdk 0.2.170, Dapr CLI 1.18.0 / runtime 1.18.7, model claude-haiku-4-5, lokální `dapr run`
s Redis, SIGKILL aplikace i daprd naráz.*

| # | Tvrzení | Výsledek |
|---|---|---|
| T1 | Druhý běh se stejnou `session_id` navazuje na transcript | ✅ |
| T2 | Čekající schválení přežije SIGKILL aplikace i sidecaru | ✅ stejné `approval_request_id` po restartu |
| T3 | Po restartu lze schválit přes HTTP, běh doběhne, nástroj proběhne **přesně jednou** | ✅ ledger start=1 end=1, restart 3,2 s |
| T4 | Transcript po restartu drží celou historii (Paříž i převod) | ✅ |
| T5 | SIGKILL **uprostřed běhu schváleného nástroje** | ⚠️ **at-least-once**: nástroj spuštěn 2×, dokončen 1×, **nové schválení nevzniklo** |
| T6 | Zamítnutí: nástroj neproběhne, Claude neopakuje | ✅ |
| T7 | Dlouhá pauza s restartem uprostřed | ✅ pro 180 s (restart v polovině pauzy, 14 dní neměřeno) |

Co z toho plyne:
- **Restart při čekání na člověka je bezpečný.** Schválení i transcript leží mimo proces
  (klíče `claude-session:<agent>/<session_id>` v Redisu, ~100 KB po čtyřech tazích), HTTP endpoint
  `/hitl/approvals/{id}/respond` funguje i v nové generaci procesu – `_restore_pending_approvals`
  dělá, co slibuje. Fallback na sidecar `raiseEvent` nebyl potřeba.
- **Restart při běhu nástroje = opakování aktivity `run_executor` s již schváleným rozhodnutím.**
  U Claude executoru neběží nástroj v aktivitě `run_tool`, ale uvnitř Claude session jako in-process
  MCP tool. Po restartu Dapr Workflow spustí `run_executor` znovu, session se obnoví z Redisu
  a `ToolGate` pustí volání se stejným `tool_use_id` rovnou, protože rozhodnutí už má. Člověk se
  podruhé neptá. Je to **dokumentované** chování (docstring `durable_executor.py`: *„tools that ran
  inside the failed attempt may run again“*), ne chyba.
- **Idempotency key v 1.0.9 do nástroje nedostaneš čistě.** Stabilní klíč je `tool_use_id`
  (`toolu_…`); hook `before_tool_call` ho v `ToolHookContext.tool_call_id` má, ale na obnovené
  cestě gate hooky vůbec nevolá (rozhodnutí má přednost) a argumenty hlídá digestem proti
  schválené podobě – injektovat klíč do argumentů tedy nejde. Zbývá: klíč odvozovat v nástroji
  z argumentů + session, nebo upstream žádost o předání `tool_use_id` nástrojům.
- Harness měl vlastní chybu: `dapr run` spouští daprd i aplikaci každý ve vlastní procesní
  skupině, takže `killpg` na skupinu CLI nic nezabije a „restart“ vypadá jako průchod za 0 s.
  Opraveno na SIGKILL celého stromu procesů s kontrolou, že porty opravdu uvolnil starý proces.
- Limity měření: jeden stroj, `dapr run` místo Kubernetes podu, Redis lokální, 14denní horizont
  neměřen.

### Co přinesla 1.0.6 (GH release 2026-09-28, mohlo uniknout)
HITL governance: `Deny` s `code`/`details`, **approver authz pole a approver token v eventech**,
caller headers na trigger akci; LiteLLM provider; streaming agent; Drasi extension (reakce na změny dat).
Approver token v eventu je dobrý základ pro auditovatelné schvalování.

### Provozní cena sidecaru
- Latence: **+1,4 ms P90, +2,1 ms P99** při 1000 req/s – proti latenci volání modelu šum.
- Skutečná cena: **~15 podů control plane** (3 repliky × 5 komponent) + 250 Mi na agentní pod.
- **Scheduler je stavový a nelze ho přeškálovat**: *„scaling the Scheduler service replicas
  up or down is not possible without incurring data loss"* (embedded etcd). Drží reminders,
  které probouzejí pozastavená workflow, tedy i čekající HITL. Věta v docs beze změny k 2026-10-20;
  externí etcd je dokumentovaná volba.
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
ceny odchodu. *Stav 2026-10-20:* žádná resubmise, v kódu `main` **nula výskytů** `temporal`;
A2A (`dapr/dapr#8703` dál *not planned*) ani AG-UI se neobjevily.

## Architektonické důsledky (Pozn. Adam)
- **Cena odchodu se láme na dvě úrovně.** Pryč od knihovny `dapr-agents` při zachování
  Dapr Workflow je levné – stav zůstává ve tvém storu. Pryč od Dapru celého je drahé,
  protože ztratíš durable execution, aktory, pub/sub i service invocation najednou.
- **Chybějící A2A a AG-UI je největší rozdíl proti kagentu.** Hranici si musíš postavit
  sám nad `a2a-sdk` vedle agenta. Paradoxně to snižuje lock-in – framework do hranice
  nemluví – ale zaplatíš prací.
- **Dapr Conversation API nepoužívat jako model gateway** – jediná `Stable` komponenta
  je `echo` (re-ověřeno 2026-10-20: Anthropic, OpenAI, Bedrock, GoogleAI, Mistral, Ollama,
  OpenRouter vše Alpha). Gateway šev vést přes `base_url` na LiteLLM proxy.
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
      → 2026-10-21: harness umí `--scenario long-pause --pause-seconds 1209600`, zbývá nechat běžet.
- [ ] Kolik breaking changes bylo po GA celkem – doložen jeden, API diff neproveden.
- [ ] Složení týmů `@dapr/maintainers-dapr-agents` – není veřejné; seznam maintainerů
      pochází z návrhu psaného CTO Diagridu, tedy zainteresovanou stranou.
- [x] ~~Umí `dapr-agents` vystavit agenta *jako* MCP server?~~ – **ne** (2026-10-20, grep zdrojáků).
- [ ] Otevřít upstream issue na odstranění nepoužívané závislosti `posthog` (nebo ověřit, zda ji
      nepotřebuje tranzitivně něco z `[dev]`) – veřejné vystoupení, chce souhlas.
- [ ] Kdy dapr-agents zvedne pin na Dapr 1.19 a na `mcp` 2.x.
- [x] ~~**Priorita (rozhodnutí Adam 2026-10-21):** ověřit `ClaudeAgentExecutor` + `DaprSessionStore`
      v harnessu~~ → **změřeno 2026-10-21**, viz sekce *Harness*: čekání na člověka restart přežije beze
      ztráty a bez dvojího provedení; restart *během* nástroje je at-least-once bez nového schválení.
- [ ] Idempotency key za schvalovacím bodem: v 1.0.9 se `tool_use_id` k nástroji nedostane
      (gate na obnovené cestě hooky přeskakuje, argumenty jsou digestované). Upstream issue, nebo
      klíč odvozovat v nástroji z argumentů – veřejné vystoupení chce souhlas.
- [ ] Zopakovat harness na `kind` + `dapr init -k` s `kubectl delete pod` místo SIGKILL.
- [ ] Síťový test air-gapped: potvrdit nulový egress (40+ tranzitivních závislostí).

## Changelog
- 2026-09-28: první verze; hloubková prověrka.
- 2026-10-21: harness T1–T7 změřen – restart při čekání na schválení beze ztráty a exactly-once,
  restart během nástroje at-least-once bez nového schválení; idempotency key jako otevřená otázka.
- 2026-10-21: rozhodnutí Adam – `ClaudeAgentExecutor` je preferovaná cesta pro Claude Agent SDK jako
  smyčku platformy (hotové first-party řešení před vlastním vývojem v MAF); harness test má prioritu.
- 2026-10-20: 1.0.7–1.0.9; first-party `ClaudeAgentExecutor` nad Claude Agent SDK; bus factor fakticky 1;
  `posthog` jako mrtvá runtime závislost; MCP server ne; MCP SDK 1.x; A2A/AG-UI/Temporal stále nic;
  AAIF bez resubmise; Conversation API dál jen `echo` Stable; Dapr 1.19 v RC.
