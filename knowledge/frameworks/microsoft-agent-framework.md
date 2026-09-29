---
tema: Microsoft Agent Framework – sloučení AutoGenu a Semantic Kernelu
naposledy_overeno: 2026-09-29
zralost: jádro GA (Python 1.19, .NET 1.22); protokolová a hostingová hranice prerelease; durable extension beta
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
---

# Microsoft Agent Framework (MAF)

## Účel
Agentní SDK pro Python a .NET – sloučení AutoGenu a Semantic Kernelu do jedné knihovny.
Agentní smyčka, workflow graf se supersteps, orchestrační vzory a protokolová rozhraní.

## Aktuální stav
- **GA 2026-04-02**; k 2026-09-29 Python 1.19, .NET 1.22.
- **MIT napříč celým stackem**, včetně durable extension. Žádný `enterprise/` adresář.
- Semantic Kernel **zůstává aktivní** a má interop vrstvu. AutoGen je **de facto zamrzlý**
  (poslední push 2026-04-15, dva týdny po GA MAF).

## Klíčové koncepty
- **Workflow graph + supersteps** – checkpoint po každém superstepu, včetně pending requests.
- **Orchestrační vzory** – Sequential, Concurrent, GroupChat, Handoff, Magentic.
- **`CheckpointStorage`** – otevřený protokol, tři shipped implementace.
- **`BaseChatClient` / `IChatClient`** – model provider není pevný výčet.

## Zralost a rizika

| Osa | Stav |
|---|---|
| Licence | ✅ **MIT napříč vším** – nejčistší licence v celém sítu |
| Governance | ❌ **Microsoft CLA**, a **není uvedená v `CONTRIBUTING.md`** – projeví se až v PR příkazem `@microsoft-github-policy-service agree` |
| Nadace | ❌ žádná; bez `GOVERNANCE.md` i `MAINTAINERS.md` |
| Bus factor | ❌ **jedna firma** – ~2 % commitů v top 30 mimo Microsoft |
| Versioning policy | ❌ **žádná** |
| Support policy | ❌ žádná OSS; komerční podpora **jen s Unified smlouvou a jen když problém vzniká z použití Azure AI services** |
| Breaking changes po GA | ❌ **~16 za 5,5 měsíce**, z toho **2 v patch releasech**, 11 dalších ve frontě |
| Kadence | ⚠️ 19 minor releasů za 5,5 měsíce |
| **A2A** | ✅ oficiální `a2a-sdk` – klient i server; balíčky **prerelease** |
| **MCP** | ✅ klient nativně; server `hosting-mcp` **prerelease, jen Python** |
| **AG-UI** | ✅ **`agent-framework-ag-ui` 1.4.0, GA** – jediný kandidát v sítu, který AG-UI má |
| Observabilita | ✅ **nejlepší v sítu** – OTEL GenAI semconv, Jaeger/Langfuse/MLflow, propagace trace do MCP přes `_meta` |
| Model gateway | ✅ **šev plně otevřený** – `base_url` na vLLM či LiteLLM; .NET: *„any `IChatClient`"* |
| Trvalost – jádro | ⚠️ `InMemory` / `File` / **`Cosmos` jako jediný produkční store**; protokol otevřený, ale Postgres store neexistuje |
| Trvalost – durable ext. | ❌ **jediný produkční backend je Azure Durable Task Scheduler** (placená služba) |
| Durable session store | ❌ *„MAF doesn't include a general-purpose durable session store"* |
| HITL dny–týdny | ✅ doloženo; pending requests jsou součástí checkpointu – **lepší než kagent v1.0-alpha** |
| Cena odchodu stavu | ❌ **nejhorší v poli** – pickle (jazykově nepřenositelné) + vazba na topologii grafu |
| Air-gap | ✅ jádro s poznámkou; ❌ durable cesta (`*.durabletask.io`) |
| Phone-home | ⚠️ **feature-usage token v User-Agent** na Azure OpenAI/Foundry endpointech, výchozí zapnutý; vypne `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED=true`. Žádný licenční klíč. |
| Licence v balíčcích | ⚠️ Python: `license_expression: null` u všech, **ale OSI classifier přítomný**; ✅ .NET: SPDX `MIT` v nuspecu |
| Zralost hranice | ❌ **A2A, MCP server, hosting i durable jsou prerelease** při GA jádře |

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
- [ ] Není žádné TypeScript/Node SDK. Pro frontend to znamená MAF vždy za HTTP hranicí –
      architektonicky spíš dobře (AG-UI / A2A), ale je to fakt k zapsání.

## Changelog
- 2026-09-29: první verze; hloubková prověrka.
- 2026-09-29: ověřeno, že MAF backend nevynucuje – `Microsoft.DurableTask.SqlServer` je
  cesta mimo Azure, ale jen pro .NET. Netherite vyřazen (konec podpory 2028-03-31).
