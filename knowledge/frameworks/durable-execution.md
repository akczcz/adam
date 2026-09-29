---
tema: Durable execution jako samostatná vrstva pod agenty
naposledy_overeno: 2026-09-29
zralost: stable (Temporal, Dapr) / mixed (licence ostatních)
primarni_zdroje:
  - https://github.com/temporalio/temporal/blob/main/LICENSE
  - https://www.cncf.io/projects/dapr/
  - https://github.com/dapr/dapr-agents
  - https://pypi.org/project/langgraph-api/
  - https://github.com/aaif/project-proposals/issues/34
  - https://docs.dapr.io/concepts/dapr-services/scheduler/
  - https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler
---

# Durable execution

## Proč to je samostatná vrstva

Dlouhoběžící agent potřebuje, aby rozpracovaný běh přežil pád procesu, restart clusteru
a čekání na lidské rozhodnutí v řádu dnů. To je **durable execution** – běh se průběžně
zapisuje do trvalého úložiště a po restartu pokračuje z posledního bodu, ne od začátku.

Skoro každý agentní framework si tuhle vrstvu dělá po svém. A právě tady bývá licenční hranice
mezi zdarma a placeným (viz [licencni-vzorce.md](licencni-vzorce.md)).

## Architektonický tah: vytáhnout ji z frameworku ven

```mermaid
flowchart TB
    subgraph bad["Vestavěná trvalost"]
        FW1["Agentní framework<br/><i>+ vlastní persistence</i>"]
        DB1[("úložiště")]
        FW1 --> DB1
    end
    subgraph good["Trvalost jako samostatná vrstva"]
        FW2["Agentní framework<br/><i>bez stavu</i>"]
        DE["Durable execution engine"]
        DB2[("úložiště")]
        FW2 --> DE --> DB2
    end
    bad -.->|"výměna frameworku<br/>= ztráta stavu a přepis"| good
```

| | Vestavěná trvalost | Samostatná vrstva |
|---|---|---|
| Výměna frameworku | Přepis včetně stavové logiky | Změna adaptéru |
| Licenční riziko | Soustředěné do jednoho projektu | Rozdělené, každá vrstva ověřená zvlášť |
| Provoz | Jeden systém | Dva systémy k provozování |
| Vhodné pro | Prototyp, jednoduchý use-case | Produkt dodávaný zákazníkovi |

Cenou je jeden systém navíc v provozu. Pro platformu, která má přežít výměnu frameworku
a licenční změnu, se to vyplatí.

## Kandidáti (ověřeno 2026-09-27)

| Engine | Licence | OSI? | Governance | Kde je stav |
|---|---|---|---|---|
| **Temporal** | **MIT** (server) | Ano | Temporal Technologies, jeden vendor | Vlastní cluster; provozně těžší |
| **Dapr Workflows** | **Apache-2.0** | Ano | **CNCF Graduated** (od 10/2024) | **V tvém state storu – 28 providerů, dokumentovaný append-only formát** |
| **Restate** | **BUSL** (runtime), MIT (SDK) | **Ne** (runtime) | Restate, jeden vendor | Vlastní binárník, nejmenší provozní stopa |
| **Inngest** | **SSPL** | **Ne** | Inngest, jeden vendor | Restriktivní u poskytování služby |
| **DBOS** | ověřit | ověřit | ověřit | Postgres-native přístup |
| **Azure Durable Task Scheduler** | SDK **MIT**, backend **proprietární Azure služba** | **Ne** (backend) | Microsoft, jeden vendor, CLA | **Uvnitř Azure služby**; emulátor jen pro vývoj |

**Pozn. Adam:** kombinace „OSI licence + nadace + graduated" má dnes jen **Dapr**.
Temporal je licenčně čistý (MIT), ale je to jeden vendor s CLA – platí u něj riziko
relicencování popsané v [licencni-vzorce.md](licencni-vzorce.md). Rozdíl je v tom,
že MIT verzi už nikdo nevezme zpátky; relicencování by se týkalo budoucích verzí.

## Když monetizovaná není licence, ale backend

MAF Durable Extension je **celý MIT** – repozitář, PyPI i .NET balíček. Přesto je jeho
durable execution nepřenositelná, protože jediný produkční backend, na který se SDK umí
připojit, je **placená Azure služba** (Durable Task Scheduler, `*.durabletask.io`).
Emulátor podle dokumentace *„isn't suitable for production use"*.

**License gate to nenajde – všechno je MIT.** Odhalí se to jen tím, že si přečteš,
na co se runtime připojuje. Detail viz čtvrtý vzorec v [licencni-vzorce.md](licencni-vzorce.md).

Praktický důsledek: obranný vzor „vytlačit durable vrstvu ven" tady nepomůže, protože
vytlačovat není kam. Buď Azure, nebo vlastní implementace `CheckpointStorage`.

## Vztah k agentním frameworkům

**Dapr Agents** (Apache-2.0, GA březen 2026) staví přímo na durable execution Dapru –
trvalost tedy není doplněk, ale vlastnost runtimu, a je ve stejné licenci jako zbytek.
To je dnes nejčistší kombinace, jakou lze složit.

Návrh na přesun Dapr Agents pod **Agentic AI Foundation** (pod jménem *Durable Agents*)
byl podán **2026-06-02**, hlasování TC uzavřeno 2026-09-03 a **zamítnut 2026-09-11**.
Projekt zůstává pod Dapr / CNCF / Linux Foundation.

Struktura governance se tím nezhoršuje. Zhoršuje se ale obrázek o **neutralitě vrstvy** –
odůvodnění komise je architektonicky důležitější než výsledek a je to trojí nezávislé
potvrzení rizika „jak drahé je vzít stav jinam":

1. Záruky trvalosti jsou demonstrované **jen nad Dapr Workflow** – *„every guarantee it
   offers is currently expressed through Dapr Workflow"*.
2. **Rozhodující bod:** žádná jiná durable-execution komunita o to nestojí; deklarovaný
   Temporal provider nestačil.
3. Projekt *„reads more as an agent framework than as a substrate"*.

Governance ani security posture zpochybněné nebyly. Resubmise je možná bez čekací lhůty –
**sledovat, jestli přibude druhý durable backend**, je to přímý indikátor ceny odchodu.

> ⚠️ **Pozor na zdroj zralosti.** CNCF Graduated se vztahuje na **Dapr runtime**, ne na
> Dapr Agents: repozitář sub-projektu vznikl 2025-01-02, tedy dva měsíce **po** graduaci
> (2024-10-30). Sub-projekt navíc nemá vlastní support ani versioning policy.

### Provozní past Dapru

Scheduler má ve výchozím nastavení **embedded etcd** a *„scaling the Scheduler service
replicas up or down is not possible without incurring data loss"*. Drží přitom reminders,
které probouzejí pozastavená workflow – tedy i čekající schvalovací body.
Pro produkt dodávaný zákazníkovi zvážit **externí etcd** (`--etcd-embed=false`)
a zálohování podle stanoveného RPO.

## Otevřené otázky
- [ ] DBOS – licence, governance, provozní model.
- [ ] Temporal: vyžaduje CLA? Jaká je struktura přispěvatelů mimo vendora?
- [ ] Jak se durable execution snáší s protokolovou hranicí A2A – kde končí běh jednoho agenta.
- [ ] Praktický dopad BUSL u Restate na dodávku produktu on-prem (otázka na právníka).
- [ ] Lze MAF workflow spustit nad Dapr Workflow nebo Temporalem bez `agent-framework-durabletask`?
- [ ] Jsou MSSQL či Netherite backendy Durable Functions použitelné pro MAF mimo Azure?
- [ ] Změřit harnessem: pozastavení na lidské rozhodnutí → restart clusteru → obnovení
      po 14 dnech. Ani jeden kandidát nemá dokumentovaný maximální horizont čekání.

## Changelog
- 2026-09-27: první verze.
- 2026-09-29: doplněn Azure Durable Task Scheduler a vzorec „monetizovaný backend".
- 2026-09-28: opraveno datum a odůvodnění zamítnutí v AAIF; doplněno, že CNCF Graduated
  se nevztahuje na Dapr Agents; přidána provozní past Scheduleru.
