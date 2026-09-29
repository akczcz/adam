---
tema: Licenční vzorce a pasti v open-source AI frameworcích
naposledy_overeno: 2026-09-29
zralost: n/a (metodika)
primarni_zdroje:
  - https://pypi.org/project/langgraph-api/
  - https://github.com/temporalio/temporal/blob/main/LICENSE
  - https://www.cncf.io/projects/dapr/
  - https://docs.litellm.ai/docs/enterprise
  - https://pypi.org/pypi/kagent-adk/json
  - https://raw.githubusercontent.com/diagridio/python-ai/main/LICENSE.md
  - https://docs.dapr.io/developing-ai/agent-integrations/
  - https://learn.microsoft.com/en-us/azure/durable-task/scheduler/durable-task-scheduler
  - https://github.com/microsoft/agent-framework/pull/8807
---

# Licenční vzorce a pasti

Metodika, jak u agentního frameworku poznat licenční riziko dřív, než se na něm postaví produkt.
Platí obecně, ne jen pro AI – jen je to tady vyhrocenější, protože trh je mladý a monetizační
modely se teprve usazují.

## Hlavní vzorec: knihovna je návnada, runtime je háček

> Knihovna, která tvoří graf a volá model, bývá MIT nebo Apache-2.0.
> To, co potřebuješ **v produkci** – trvalý stav, fronty úloh, HTTP server, streaming,
> plánované běhy, koordinace replik – bývá v jiné licenci.

Prototyp proto projde bez problému a licenční problém se objeví až ve chvíli, kdy se řeší
škálování a provoz. V té fázi je přepis drahý – to je na tom to nebezpečné.

**Doložený případ (ověřeno 2026-09-27):**

| Balíček | Licence | Co obsahuje |
|---|---|---|
| `langgraph` | MIT | graf, uzly, hrany – vývojová smyčka |
| `langchain-core` | MIT | základní abstrakce |
| **`langgraph-api`** | **Elastic License 2.0** | **HTTP, persistence, fronty úloh, streaming** |

`langgraph-api` se aktivuje příkazy `langgraph dev` i `langgraph build`. ELv2 není OSI open source –
zakazuje mimo jiné poskytovat produkt jako řízenou službu třetím stranám a obcházet licenční klíče.
Pro produkční self-hosted provoz serverové části je potřeba komerční klíč.

Stejný vzorec jinde: **Mastra** má jádro Apache-2.0, ale některé komponenty pod Elastic licencí.
**LiteLLM** má SDK i proxy MIT, ale adresář `enterprise/` je licencovaný zvlášť.

## Druhý vzorec: publikovaný artefakt bez licenčních metadat

Repozitář je Apache-2.0, ale **publikovaný balíček nedeklaruje licenci vůbec**.
Pro SBOM, license gate v CI a compliance review zákazníka to není „Apache-2.0",
ale **„unknown"** – a to bývá v enterprise politikách horší než permisivní licence.

**Doložený případ (ověřeno 2026-09-28):** balíčky kagentu na PyPI – `kagent-adk`,
`kagent-core`, `kagent-langgraph`, `agentsts-core` – mají `license: null`,
`license_expression: null` a žádný license classifier. Repozitář přitom Apache-2.0 je.

Mírnější varianta: licence deklarovaná legacy free-textem (`"Apache License 2.0"`),
ale chybějící `license_expression` podle PEP 639 v SPDX tvaru (`Apache-2.0`).
Přísný gate, který čte jen `license_expression`, uvidí prázdno. Tak to má `dapr-agents`.

Tři gradace téhož symptomu, od nejhorší:

| Projekt | `license` | `license_expression` | OSI classifier |
|---|---|---|---|
| kagent (PyPI) | `null` | `null` | ❌ chybí |
| Microsoft Agent Framework (PyPI) | `null` u většiny | `null` u všech | ✅ přítomný |
| Dapr Agents (PyPI) | free-text, ne SPDX | `null` | ✅ přítomný |

**Hygiena se liší i mezi jazykovými SDK jednoho repozitáře:** MAF má na PyPI `license_expression: null`,
ale jeho .NET balíček deklaruje SPDX `MIT` v nuspecu správně. Kontrolovat každý registry zvlášť.

Není to licenční past, je to **hygiena**. Řeší se jedním PR – ale dokud se nevyřeší,
je to práce pro dodavatele produktu: doložit licenci ručně.

## Třetí vzorec: dokumentace projektu jako vektor pasti

Šev nemusí být v repu. Může být **vedle něj** – a odkazovat na něj oficiální dokumentace
nadačního projektu.

**Doložený případ (ověřeno 2026-09-28):** stránka `docs.dapr.io/developing-ai/agent-integrations/`
na doméně CNCF projektu nabízí durable execution pro 11 agentních frameworků instalací
`pip install diagrid[...]`. Ty balíčky pocházejí z `github.com/diagridio/python-ai` –
repozitáře firmy, ne dapr orgu – a jsou pod **Diagrid Business Source License 1.1**:

| Omezení | |
|---|---|
| Produkční použití zdarma | jen organizace pod **60 FTE a 15 M USD obratu** |
| Zákaz | SaaS, konkurenční infrastruktura (agent runtime, durable execution) |
| Zákaz | **komerční redistribuce a sublicencování za úplatu** |
| Change Date | 2030-03-01 → Apache-2.0 |

Třetí řádek míří přesně na model *dodáváme produkt do prostředí zákazníka*.
**Otázka na právníka.**

Zákeřné je, že PyPI balíček `diagrid` **licenci v metadatech neuvádí vůbec** a GitHub
ji hlásí jako `NOASSERTION`. License gate tedy uvidí *unknown*, ne *BUSL* – a pustí to dál.

**Pozn. Adam – poučení:** „projekt je pod nadací" chrání **repozitář**, ne `pip install`
příkaz v jeho dokumentaci. Kontrolovat vlastníka **každého** balíčku ve finálním lock filu.
Balíčky s BUSL licencí patří na deny-list v license gate, aby se nedostaly do lock filu omylem.

## Čtvrtý vzorec: OSS SDK, uzavřený backend

Nejzákeřnější z celé sady, protože **license gate ho nikdy nenajde** – všechno je MIT.

Knihovna i SDK jsou v pořádkové licenci, ale **jediný produkční backend, na který se
runtime umí připojit, je hostovaná služba jednoho poskytovatele**. Přenositelnost
nezablokuje licence, zablokuje ji architektura.

**Doložený případ (ověřeno 2026-09-29):** `agent-framework-durabletask` (Microsoft Agent
Framework) je MIT, repozitář i balíček. Ale:

- `durabletask-azuremanaged` je **povinná závislost**, bez extra markeru
- všechny navazující balíčky se jmenují `*AzureManaged`
- *„The Durable Task Scheduler **runs in Azure** as a separate resource from your app"*,
  dvě billing SKU, endpoint `{scheduler}.{region}.durabletask.io`
- emulátor: *„The emulator internally stores orchestration and entity state in local memory,
  so **it isn't suitable for production use**."*

**Zpřesnění po přečtení kódu (2026-09-29):** past není ve frameworku, ale v **dokumentované
cestě a v jazykovém SDK**. MAF sám backend nevynucuje – registruje generické buildery
a provider určuje volající. Cesta ven existuje (`Microsoft.DurableTask.SqlServer`, MIT,
persistuje do MS SQL kdekoliv), ale **jen na .NET**; Python SDK je popsané jako
*„requires Azure Durable Task Scheduler, it is not a generic gRPC sidecar connector"*.

To vzorec nevyvrací, jen ukazuje, kde přesně hledat: **ne v `LICENSE`, ale v tom, jaké
backendy SDK daného jazyka umí oslovit, a jestli je dokumentace vůbec zmiňuje.**

**Pozn. Adam – kontrolní otázka:** *„Má tahle OSS komponenta alespoň jeden produkční
backend, který si smíme provozovat sami?"* MIT knihovna, která umí mluvit jen s jednou
hostovanou službou, není přenositelná bez ohledu na licenci.

## Skutečný prediktor rizika: kdo vlastní copyright

Aktuální soubor `LICENSE` říká, co platí dnes. Neříká nic o tom, co bude platit za rok.
Rozhodující je, **kdo smí licenci změnit**.

| Struktura | Může relicencovat? | Riziko | Precedenty |
|---|---|---|---|
| Jeden vendor + CLA / copyright assignment | Ano, jednostranně a bez varování | **Vysoké** | HashiCorp → BUSL, Elastic → SSPL, Redis → RSAL, Sentry → BUSL |
| Jeden vendor + CLA, **která není v `CONTRIBUTING.md`** | Ano | **Vysoké a skryté** | Microsoft Agent Framework – CLA se projeví až v PR příkazem `@microsoft-github-policy-service agree` |
| Projekt pod nadací (CNCF, ASF, LF AI & Data) | Prakticky ne – copyright je rozptýlený mezi přispěvatele | **Nízké** | Kubernetes, Dapr, OpenTelemetry |
| Jeden vendor + **DCO** + trademark u nadace | Jen budoucí vlastní kód; cizí příspěvky ne | **Nízké licenčně, střední směrově** | kagent (Apache-2.0 + DCO + CNCF IP Policy, ale 7/8 maintainerů od jednoho vendora) |

**Pozn. Adam:** tohle je nejdůležitější otázka celé licenční analýzy a zároveň ta, na kterou
automatický license gate v CI neodpoví. Gate kontroluje dnešní stav souboru `LICENSE`.
Neumí říct „tenhle projekt má CLA a jednoho vlastníka, takže může kdykoliv přitvrdit".

## Stupnice licencí podle použitelnosti v produktu dodávaném zákazníkovi

| Licence | OSI open source? | Dodání zákazníkovi | Poznámka |
|---|---|---|---|
| MIT, Apache-2.0, BSD | Ano | Bez omezení | Apache-2.0 navíc řeší patenty |
| MPL-2.0, LGPL | Ano | Prakticky bez omezení | Copyleft na úrovni souboru/knihovny |
| GPL-3.0, AGPL-3.0 | Ano | **Pozor** | AGPL se vztahuje i na síťové použití |
| **BUSL** (Business Source License) | **Ne** | Self-hosting obvykle ano, konkurenční služba ne | Po ~4 letech typicky konvertuje na Apache-2.0 |
| **ELv2** (Elastic License 2.0) | **Ne** | Zákaz řízené služby, zákaz obcházení licenčních klíčů | |
| **SSPL** | **Ne** | Velmi restriktivní u poskytování služby | |
| Vlastní „enterprise" licence | Ne | Podle smlouvy | Typicky adresář `enterprise/` v jinak MIT repu |
| **Diagrid BSL** (BUSL 1.1 s prahy FTE a obratu) | **Ne** | **Otázka na právníka** – zákaz komerční redistribuce míří přímo na dodávku produktu | Change Date 2030-03-01 |

BUSL a ELv2 **nejsou fatální** pro produkt nasazovaný u zákazníka on-prem – bývají mířené
na konkurenční poskytovatele cloudu. Je ale nutné si to nechat potvrdit právníkem, ne architektem,
a počítat s tím, že to vyloučí model „provozujeme to jako SaaS pro víc zákazníků".

## Kontrolní otázky před volbou frameworku

1. **Co přesně potřebuju v produkci navíc oproti prototypu?** Trvalý stav, HITL přes restart,
   plánované běhy, více replik, tracing backend. Pro každou položku: v jaké licenci to je?
2. **Vyžaduje projekt CLA?** Pokud ano, jeden subjekt může licenci kdykoliv změnit.
3. **Je pod nadací?** Jaký stupeň zralosti (u CNCF: Sandbox → Incubating → Graduated)?
4. **Je v repu adresář `enterprise/`, `ee/` nebo `pro/`?** Skoro jistě jiná licence.
5. **Volá komponenta domů?** Telemetrie, kontrola licenčního klíče, hostovaný tracing –
   diskvalifikuje to air-gapped nasazení bez ohledu na licenci.
6. **Co se stane, když vendor zítra relicencuje?** Kolik práce je odejít a co zůstane funkční?
7. **Deklarují publikované balíčky licenci strojově čitelně?** Pole `license`,
   **`license_expression`** (SPDX, PEP 639) a classifier `License :: OSI Approved`.
   Chybějící hodnota = „unknown" v SBOM i u jinak čistě Apache-2.0 projektu.
8. **Vlastní kdokoliv jiný balíčky, které dokumentace doporučuje instalovat?**
   Ověř owner **každého** balíčku ve finálním lock filu, ne jen hlavního repa.
9. **Má komponenta produkční backend, který si smíme provozovat sami?** MIT knihovna,
   která umí mluvit jen s jednou hostovanou službou, není přenositelná bez ohledu na licenci.

## Obranný vzor: vytlačit komerční vrstvu ven

Když je monetizovanou částí durable runtime, je obranou **nenechat durable runtime vlastnit
agentní framework**. Trvalost stavu ať drží samostatná vrstva (viz [durable-execution.md](durable-execution.md))
s vlastní, ověřenou licencí. Framework se pak stává vyměnitelnou komponentou
a licenční past přestává být existenční.

Totéž platí pro přístup k modelům – viz model gateway v [overview.md](overview.md).

## Changelog
- 2026-09-27: první verze; doložen vzorec na `langgraph-api` (ELv2).
- 2026-09-29: čtvrtý vzorec zpřesněn po přečtení kódu – past je v dokumentované cestě
  a v jazykovém SDK, ne ve frameworku.
- 2026-09-29: přidán čtvrtý vzorec (OSS SDK, uzavřený backend – Azure DTS); doplněna
  skrytá CLA do tabulky governance a gradace hygieny licenčních metadat.
- 2026-09-28: přidán druhý vzorec (balíček bez licenčních metadat, kagent) a třetí
  (dokumentace jako vektor, Diagrid BSL); doplněn řádek DCO do tabulky governance.
