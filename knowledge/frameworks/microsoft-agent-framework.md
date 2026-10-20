---
tema: Microsoft Agent Framework – sloučení AutoGenu a Semantic Kernelu
naposledy_overeno: 2026-10-20
zralost: jádro GA (Python 1.22, .NET 1.25); protokolová a hostingová hranice stále prerelease; durable extension beta; Go SDK public preview
primarni_zdroje:
  - https://github.com/microsoft/agent-framework/blob/main/LICENSE
  - https://github.com/microsoft/agent-framework/blob/main/SUPPORT.md
  - https://github.com/microsoft/agent-framework/pull/8807
  - https://pypi.org/pypi/agent-framework-core/json
  - https://pypi.org/pypi/agent-framework-durabletask/json
  - https://pypi.org/pypi/agent-framework-ag-ui/json
  - https://github.com/microsoft/agent-framework-durable-extension
  - https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints
  - https://learn.microsoft.com/en-us/agent-framework/hosting/self-hosting
  - https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes
  - https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler
  - https://github.com/microsoft/durabletask-mssql
  - https://github.com/microsoft/durabletask-go
  - https://pypi.org/pypi/durabletask/json
  - https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-storage-providers
  - https://github.com/microsoft/agent-framework/releases
  - https://github.com/microsoft/agent-framework/blob/main/.github/CODEOWNERS
  - https://pypi.org/pypi/agent-framework-redis/json
  - https://pypi.org/pypi/agent-framework-claude/json
  - https://github.com/microsoft/agent-framework-go
  - https://github.com/microsoft/autogen/blob/main/README.md
---

# Microsoft Agent Framework (MAF)

## Účel
Agentní SDK pro Python a .NET – sloučení AutoGenu a Semantic Kernelu do jedné knihovny.
Agentní smyčka, workflow graf se supersteps, orchestrační vzory a protokolová rozhraní.

## Aktuální stav
- **GA 2026-04-02**; k 2026-10-20 **Python 1.22.0** (2026-10-15), **.NET 1.25.0** (2026-10-14).
  Kadence drží: týdenní minor (Python 1.20 → 1.21 → 1.22 během 2.–15. 10.).
- **MIT napříč celým stackem**, včetně durable extension. Žádný `enterprise/` adresář.
- **Go SDK** – `microsoft/agent-framework-go` (MIT, v0.2.0 prerelease 2026-10-20), *„public preview,
  evolving outside the core upstream codebase“*. TypeScript/Node SDK stále neexistuje.
- Semantic Kernel **zůstává aktivní** (Python 1.45.0, 2026-10-06) a má interop vrstvu.
  AutoGen je od **2026-10-16 oficiálně archivovaný** – README: *„no longer actively maintained …
  not providing bug fixes, security fixes … we continue to advise against production use“*
  (repo na GitHubu formálně nearchivováno, ale deklarace je jednoznačná). Ověřeno 2026-10-20.

## Klíčové koncepty
- **Workflow graph + supersteps** – checkpoint po každém superstepu, včetně pending requests.
- **Orchestrační vzory** – Sequential, Concurrent, GroupChat, Handoff, Magentic.
- **`CheckpointStorage`** – otevřený protokol, tři shipped implementace.
- **`BaseChatClient` / `IChatClient`** – model provider není pevný výčet.
- **`SessionStore` + history providers** – session objekt a historie zpráv se persistují zvlášť;
  `SessionStore` je subclassovatelný, `RedisHistoryProvider` (beta) persistuje zprávy napříč restarty.
- **`agent-framework-claude`** (beta, `claude-agent-sdk>=0.1.46,<0.3`) – Claude Agent SDK jako smyčka
  uvnitř MAF; obdoba toho, co Dapr Agents dodaly v 1.0.7 (viz [`dapr-agents.md`](dapr-agents.md)).

## Zralost a rizika

| Osa | Stav |
|---|---|
| Licence | ✅ **MIT napříč vším** – nejčistší licence v celém sítu |
| Governance | ❌ **Microsoft CLA**, a **není uvedená v `CONTRIBUTING.md`** (re-ověřeno 2026-10-20, žádná zmínka) – projeví se až v PR příkazem `@microsoft-github-policy-service agree` |
| Nadace | ❌ žádná; bez `GOVERNANCE.md` i `MAINTAINERS.md`; jediný seznam vlastníků je `.github/CODEOWNERS` – 11 handle, Python 9, .NET 7 (2026-10-20) |
| Bus factor | ❌ **jedna firma** – ~2 % commitů v top 30 mimo Microsoft |
| Versioning policy | ❌ **žádná** |
| Support policy | ❌ žádná OSS; komerční podpora **jen s Unified smlouvou a jen když problém vzniká z použití Azure AI services** |
| Breaking changes po GA | ❌ **tempo roste** – stránka významných změn (stav 2026-10-15) eviduje **31 🔴 od GA**, z toho **16 v bloku „Unreleased“**, který podle release notes z větší části vyšel v Python 1.20 a 1.22 (6 položek označených [BREAKING], mj. jedna napříč 17 balíčky: #8886 „consolidate content identity, hosted execution, protocol metadata, replay, stream-merge“). .NET 1.23 pět, 1.25 dvě (+ jeden revert). Dříve ~16 za 5,5 měsíce, teď **~13 za tři týdny** |
| Kadence | ⚠️ 19 minor releasů za 5,5 měsíce |
| **A2A** | ✅ oficiální `a2a-sdk` (`agent-framework-a2a` pinuje `a2a-sdk>=1.0.0,<2`, tj. protokol v1.0) – klient i server; balíček **stále Beta** (1.0.0b261015, 2026-10-15; ověřeno 2026-10-20 na PyPI) |
| **MCP** | ✅ klient nativně, ale na **`mcp<2,>=1.24` – 1.x linie SDK**, éra 2026-07-28 (stateless, MRTR) se ho netýká; server `agent-framework-hosting-mcp` **Alpha** (1.0.0a261015), jen Python. 1.22 oddělila MCP runtime context od approval headers (🔴) |
| **AG-UI** | ✅ **`agent-framework-ag-ui` 1.6.0 (2026-10-15), GA** – jediný kandidát v sítu, který AG-UI má. ⚠️ Pinuje `ag-ui-protocol<0.2,>=0.1.19`, zatímco spec AG-UI je od 2026-09-17 na **1.0** (ověřeno 2026-10-20 na PyPI; viz [`../protocols/ag-ui.md`](../protocols/ag-ui.md)). 1.22 přinesla dvě 🔴 v AG-UI (fail-closed trust boundaries vázané na thread ID; shared state nesmí přepsat tool-approval state). ⚠️ **.NET `Microsoft.Agents.AI.AGUI` je 1.13.0-preview z 2026-07-03** – AG-UI na .NET zaostává o čtvrt roku |
| Observabilita | ✅ **nejlepší v sítu** – OTEL GenAI semconv, Jaeger/Langfuse/MLflow, propagace trace do MCP přes `_meta` |
| Model gateway | ✅ **šev plně otevřený** – `base_url` na vLLM či LiteLLM; .NET: *„any `IChatClient`"* |
| Trvalost – jádro | ⚠️ `InMemory` / `File` / **`Cosmos` jako jediný produkční checkpoint store** (re-ověřeno v docs 2026-10-20); protokol otevřený, Postgres checkpoint store dál neexistuje (`agent-framework-postgres` 1.0.0a261015 je stále jen pgvector) |
| Trvalost – durable ext. | ❌ **jediný produkční backend je Azure Durable Task Scheduler** (placená služba) |
| Durable session store | ❌ *„MAF doesn't include a general-purpose durable session store"* (věta v docs trvá, 2026-10-20). Nuance: **historii zpráv** už persistuje `RedisHistoryProvider` (beta, scoped keys per application/session); **session objekt** (metadata + provider state) zůstává na vlastním `SessionStore` |
| HITL dny–týdny | ✅ doloženo; pending requests jsou součástí checkpointu – **lepší než kagent v1.0-alpha** |
| Cena odchodu stavu | ❌ **nejhorší v poli** – pickle (jazykově nepřenositelné) + vazba na topologii grafu |
| Air-gap | ✅ jádro s poznámkou; ❌ durable cesta (`*.durabletask.io`) |
| Phone-home | ⚠️ **feature-usage token v User-Agent** na Azure OpenAI/Foundry endpointech, výchozí zapnutý; vypne `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED=true`. Žádný licenční klíč. |
| Licence v balíčcích | ⚠️ Python: `license_expression: null` u všech, **ale OSI classifier přítomný**; ✅ .NET: SPDX `MIT` v nuspecu |
| Zralost hranice | ❌ **A2A (Beta), hosting-a2a (Alpha), hosting-mcp (Alpha), durabletask (Beta, 2026-09-25, bez nového vydání) jsou prerelease** při GA jádře; .NET A2A/Hosting.A2A/DurableTask všechny `-preview` (2026-10-20) |

### `agent-framework-postgres` není checkpoint store
Je to **vector store** (`PostgresCollection`, pgvector) ve stavu alpha. Kdo hledá
produkční trvalost mimo Azure, musí si `CheckpointStorage` napsat sám.

### Durable backend: past je v dokumentované cestě, ne ve frameworku
*Ověřeno 2026-09-29.*

`ServiceCollectionExtensions.cs` registruje **generické** buildery z `Microsoft.DurableTask`
(`AddDurableTaskWorker`, `AddDurableTaskClient`). **Storage provider určuje volající delegát,
ne MAF.** `UseDurableTaskScheduler(connectionString)` je v dokumentaci jen příklad, ne vynucení.

Existuje tedy cesta ven – ale jen jedna a jen na .NET:

| Cesta | Mimo Azure? |
|---|---|
| MAF .NET + [`Microsoft.DurableTask.SqlServer`](https://github.com/microsoft/durabletask-mssql) | ✅ **ano** |
| MAF Python + `agent-framework-durabletask` | ❌ ne – `durabletask` na PyPI *„requires Azure Durable Task Scheduler, it is not a generic gRPC sidecar connector"* |
| MAF jako tenká smyčka + cizí durable vrstva | ✅ ano |

**`microsoft/durabletask-mssql`** (MIT, 105 hvězd, poslední push 2026-09-25, release v1.8.1
z 2026-08-06, **není archivovaný**) persistuje stav task hubu do MS SQL,
*„which can be hosted in the cloud or in your own infrastructure"*. Dodává tři NuGet balíčky
včetně `Microsoft.DurableTask.SqlServer` pro DTFx aplikace, tedy nejen pro Azure Functions.

**Tři háčky:**

1. **Python cestu to nezachrání.** Mimo Azure jde MAF durable jen přes .NET – což naráží
   na stack postavený na Pythonu.
2. **Netherite je mrtvý směr** – podpora pro Durable Functions **končí 2028-03-31**
   a Microsoft směruje na DTS. Pro produkt nepoužitelné.
3. **Směr vývoje jde proti tomu.** `microsoft/durabletask-go`: *„DTS is the only supported
   runtime. This SDK does not include a storage backend."* Microsoft zužuje out-of-process
   SDK svět na svoji placenou službu. (`dapr/durabletask-go` je fork, který si embeddable
   engine ponechal – což zpětně vysvětluje, proč Dapr forkoval.)

**Pozn. Adam:** doporučení „durable vrstvu MAF nedávat" tím **nepadá, jen dostává lepší
podklad**. Cesta ven existuje, ale zamkne tě do .NET a jede proti směru, kam Microsoft
ekosystém tlačí. Varianta s cizí durable vrstvou zůstává nejlepší.

### Checkpoint je vázaný na topologii grafu
*„A rehydrated workflow must preserve the topology and executor identities."*
U .NET dokonce platí, že změna `Name` nebo `Id` executoru učiní checkpoint nekompatibilním
a nejde to opravit. **Refaktor grafu během dlouhého čekání na schválení zneplatní běžící běhy.**

### Co přinesl říjen 2026 (ověřeno 2026-10-20)
- **Balíčky:** `agent-framework-core` 1.22.0 (PyPI 2026-10-15), celý meta balíček `agent-framework[all]`
  pinuje `core==1.22.0`. `durabletask` na PyPI 1.12.0 (2026-10-12) se dál popisuje jako SDK pro Azure
  Durable Task Scheduler; `agent-framework-durabletask` bez vydání od 2026-09-25 a závisí na
  `durabletask-azuremanaged`. Python 3.15 podporováno, **3.10 deprecated**.
- **Breaking v HITL cestě:** „Local tool approvals require the issuing session“ a „Persisted approval
  transcripts must use typed approval controls“ – obojí 🔴 v bloku Unreleased. Pro nás relevantní:
  uložené schvalovací transkripty z dřívějších verzí nemusí po upgradu projít.
- **Phone-home beze změny:** `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED` dál v `core/agent_framework/_telemetry.py`
  (spec `docs/specs/004-feature-usage-telemetry.md`), k tomu `AGENT_FRAMEWORK_USER_AGENT`.
- **Bus factor:** 100 commitů od 2026-09-29 (limit API); top ne-botoví autoři jsou všichni v CODEOWNERS,
  tedy Microsoft. Číslo ~2 % mimo Microsoft dál neověřeno.
- **SUPPORT.md beze změny:** Unified smlouva + jen při použití Azure AI služeb; jinak *„purely open-source tool“*.

## Architektonické důsledky (Pozn. Adam)
MAF sedí za protokolovou hranicí **lépe než kterýkoliv jiný kandidát** a zároveň má
**nejdražší stav** z celého pole. Na tuhle kombinaci má obranný vzor z
[licencni-vzorce.md](licencni-vzorce.md) přímou odpověď – **vzít MAF jako smyčku
a hranici, a durable vrstvu mu nedat**:

```
MAF (agent + workflow graph + A2A/MCP/AG-UI, MIT)
  ├── model:    LiteLLM proxy nebo vLLM přes base_url
  ├── trvalost: vlastní CheckpointStorage nad Postgres  (NE Cosmos, NE DTS)
  └── nebo:     MAF agent jako aktivita v Dapr Workflow či Temporalu
```

Tím se `agent-framework-durabletask` vůbec nepoužije a Azure gravitace zmizí.
Cenou je vlastní `CheckpointStorage` a `AgentSessionStore` – ten je ale nutný
i v Azure scénáři, tam ho jen nahradí Cosmos.

**Důsledek pro celé síto:** posouvá to variantu 3 z „nejvíc práce" na „nejrealističtější",
protože MAF pokrývá právě tu vrstvu, kterou varianta 3 neměla – protokolovou hranici
včetně AG-UI.

**Co zůstává i v téhle podobě:** Microsoft CLA, nulová versioning policy a tempo
breaking changes. Verzi je nutné přišpendlit a upgrade rozpočtovat jako opakovanou práci.
Říjen 2026 to podtrhl: **tři minory za dva týdny s ~13 🔴**, z toho dvě přímo v AG-UI a dvě v HITL
schvalování – tedy přesně ve vrstvách, kvůli kterým MAF v sítu je. Pin na konkrétní verzi není
hygiena, je to podmínka provozu.

**Nový argument pro variantu 3:** MAF má od 10/2026 `agent-framework-claude` (Claude Agent SDK jako
smyčka) i `RedisHistoryProvider`. S Dapr Agents 1.0.7 (`ClaudeAgentExecutor`) tak existují **dvě
Apache-2.0/MIT cesty, jak dát Claude Agent SDK durable běh** – MAF přes vlastní `CheckpointStorage`,
Dapr přes `DaprSessionStore`. Dapr má trvalost hotovou, MAF má protokolovou hranici. Srovnat v harnessu.

## Otevřené otázky
- [x] ~~Jsou MSSQL nebo Netherite backendy použitelné pro MAF mimo Azure?~~ –
      **uzavřeno 2026-09-29: MSSQL ano, ale jen na .NET; Netherite končí 2028-03-31.**
      Viz sekce o durable backendu výše.
- [ ] Odhadnout práci na vlastním `CheckpointStorage` nad Postgres a `AgentSessionStore`.
      Vyhnout se pickle by zlepšilo cenu odchodu nad úroveň, kterou dodává Microsoft.
- [ ] Lze MAF workflow spustit nad Dapr Workflow nebo Temporalem bez `agent-framework-durabletask`?
- [ ] Kolik z ~16 post-GA breaking changes by reálně zasáhlo naši vrstvu (API diff).
- [ ] Ověřit zaměstnanecké příslušnosti hlavních přispěvatelů – číslo ~2 % je odvozené z handle.
- [ ] Právní rozsah Microsoft CLA (copyright assignment vs. license grant).
- [ ] Obnovení checkpointu po změně topologie grafu – dokumentace říká, že nefunguje;
      zjistit, jak přesně selže.
- [ ] Není žádné TypeScript/Node SDK (stav 2026-10-20; přibylo jen Go v public preview). Pro frontend
      to znamená MAF vždy za HTTP hranicí – architektonicky spíš dobře (AG-UI / A2A), ale je to fakt k zapsání.
- [ ] Kdy `agent-framework-ag-ui` přejde na `ag-ui-protocol` 1.x a kdy .NET AGUI balíček dožene Python.
- [ ] Kdy jádro přejde na `mcp` 2.x (éra 2026-07-28) – dnes `mcp<2`.
- [ ] Ověřit dopad 🔴 „Persisted approval transcripts must use typed approval controls“ na checkpointy
      uložené před upgradem (migrace, nebo zahození čekajících schválení?).
- [ ] Srovnat `agent-framework-claude` + vlastní `CheckpointStorage` proti Dapr `ClaudeAgentExecutor`.

## Changelog
- 2026-09-29: první verze; hloubková prověrka.
- 2026-09-29: ověřeno, že MAF backend nevynucuje – `Microsoft.DurableTask.SqlServer` je
  cesta mimo Azure, ale jen pro .NET. Netherite vyřazen (konec podpory 2028-03-31).
- 2026-10-20: hloubková re-verifikace. Python 1.22 / .NET 1.25; ~13 🔴 za tři týdny (31 od GA), z toho
  AG-UI a HITL; AutoGen oficiálně archivován; Go SDK public preview; `agent-framework-claude` a
  `RedisHistoryProvider` (beta); MCP SDK 1.x; checkpoint store dál jen Cosmos; .NET AGUI zaostává;
  CLA v CONTRIBUTING dál chybí; phone-home a SUPPORT beze změny.
