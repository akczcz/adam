---
tema: Licenční vzorce a pasti v open-source AI frameworcích
naposledy_overeno: 2026-10-23
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
  - https://github.com/mastra-ai/mastra/blob/main/packages/connect/LICENSE-ELv2.txt
  - https://raw.githubusercontent.com/restatedev/restate/main/LICENSE
  - https://raw.githubusercontent.com/inngest/inngest/main/LICENSE.md
  - https://raw.githubusercontent.com/dapr/dapr-agents/main/pyproject.toml
  - https://raw.githubusercontent.com/microsoft/autogen/main/README.md
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

**Doložený případ (ověřeno 2026-09-27, re-ověřeno 2026-10-20):**

| Balíček | Licence | Co obsahuje |
|---|---|---|
| `langgraph` 1.2.16 | MIT | graf, uzly, hrany – vývojová smyčka |
| `langchain-core` 1.6.12 | MIT | základní abstrakce |
| **`langgraph-api`** 0.16.2 | **Elastic License 2.0** (`license: Elastic-2.0`) | **HTTP, persistence, fronty úloh, streaming** |

`langgraph-api` se aktivuje příkazy `langgraph dev` i `langgraph build`. ELv2 není OSI open source –
zakazuje mimo jiné poskytovat produkt jako řízenou službu třetím stranám a obcházet licenční klíče.
Pro produkční self-hosted provoz serverové části je potřeba komerční klíč.

Stejný vzorec jinde: **Mastra** má `@mastra/core` 1.78.0 Apache-2.0, ale `packages/connect/`
nese `LICENSE-ELv2.txt` (repo jako celek GitHub hlásí `NOASSERTION`; ověřeno 2026-10-20).
**LiteLLM** 1.106.1 má SDK i proxy MIT (`license_expression: MIT`), ale `enterprise/LICENSE.md`
je *„BerriAI Enterprise license“* (ověřeno 2026-10-20).

## Druhý vzorec: publikovaný artefakt bez licenčních metadat

Repozitář je Apache-2.0, ale **publikovaný balíček nedeklaruje licenci vůbec**.
Pro SBOM, license gate v CI a compliance review zákazníka to není „Apache-2.0",
ale **„unknown"** – a to bývá v enterprise politikách horší než permisivní licence.

**Doložený případ (ověřeno 2026-09-28, trvá k 2026-10-20 v obou liniích, 0.10.3 i 1.0.0a16):**
balíčky kagentu na PyPI – `kagent-adk`, `kagent-core`, `kagent-langgraph`, `agentsts-core` –
mají `license: null`, `license_expression: null` a žádný license classifier. Repozitář přitom
Apache-2.0 je.

Mírnější varianta: licence deklarovaná legacy free-textem (`"Apache License 2.0"`),
ale chybějící `license_expression` podle PEP 639 v SPDX tvaru (`Apache-2.0`).
Přísný gate, který čte jen `license_expression`, uvidí prázdno. Tak to má `dapr-agents`.

Tři gradace téhož symptomu, od nejhorší:

| Projekt (stav 2026-10-20) | `license` | `license_expression` | OSI classifier |
|---|---|---|---|
| kagent (PyPI, obě linie) | `null` | `null` | ❌ chybí |
| `diagrid` (PyPI 0.5.3) | `null` | `null` | ❌ chybí – a licence je BUSL |
| Microsoft Agent Framework (PyPI 1.22) | `null` | `null` | ✅ přítomný |
| Google ADK (PyPI 2.12) | `null` | `null` | ✅ přítomný |
| Dapr Agents (PyPI 1.0.9) | free-text, ne SPDX | `null` | ✅ přítomný |
| `langgraph-api` (PyPI 0.16.2) | `Elastic-2.0` free-text | `null` | ❌ (správně – není OSI) |
| `langgraph` (PyPI 1.2.16) | prázdné | ✅ `MIT` | ❌ chybí – opačná mezera: gate čtoucí jen classifier uvidí prázdno |
| LiteLLM (PyPI 1.106) | prázdné | ✅ `MIT` | – |

**Hygiena se liší i mezi jazykovými SDK jednoho repozitáře:** MAF má na PyPI `license_expression: null`,
ale jeho .NET balíček deklaruje SPDX `MIT` v nuspecu správně. Kontrolovat každý registry zvlášť.

Není to licenční past, je to **hygiena**. Řeší se jedním PR – ale dokud se nevyřeší,
je to práce pro dodavatele produktu: doložit licenci ručně.

## Třetí vzorec: dokumentace projektu jako vektor pasti

Šev nemusí být v repu. Může být **vedle něj** – a odkazovat na něj oficiální dokumentace
nadačního projektu.

**Doložený případ (ověřeno 2026-09-28, trvá k 2026-10-20 – 9 instalačních příkazů na stránce):**
stránka `docs.dapr.io/developing-ai/agent-integrations/` na doméně CNCF projektu nabízí durable
execution pro agentní frameworky instalací `pip install diagrid[...]`. Ty balíčky pocházejí z `github.com/diagridio/python-ai` –
repozitáře firmy, ne dapr orgu – a jsou pod **Diagrid Business Source License 1.1**:

| Omezení | |
|---|---|
| Produkční použití zdarma | jen organizace pod **60 FTE a 15 M USD obratu** |
| Zákaz | SaaS, konkurenční infrastruktura (agent runtime, durable execution) |
| Zákaz | **komerční redistribuce a sublicencování za úplatu** |
| Change Date | 2030-03-01 → Apache-2.0, **nebo čtvrté výročí první distribuce dané verze, co nastane dřív**; platí per verze (ověřeno v LICENSE.md 2026-10-20) |

Třetí řádek míří přesně na model *dodáváme produkt do prostředí zákazníka*.
**Otázka na právníka.**

Zákeřné je, že PyPI balíček `diagrid` (0.5.3, 2026-10-02) **licenci v metadatech neuvádí vůbec**
a GitHub ji hlásí jako `NOASSERTION` (stav 2026-10-20 beze změny). License gate tedy uvidí *unknown*, ne *BUSL* – a pustí to dál.

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

- `durabletask-azuremanaged` je **povinná závislost**, bez extra markeru (trvá k 2026-10-20,
  balíček 1.0.0b260922 bez nového vydání)
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

**Zobecnění (2026-09-29):** tentýž rozpor mezi dokumentací a kódem se potvrdil u dvou
nezávislých projektů a v obou směrech:

| Projekt | Co říká dokumentace | Co říká kód |
|---|---|---|
| Microsoft Agent Framework | durable jen přes Azure DTS | backend nevynucuje, provider určuje volající |
| kagent v1.0 | Substrate je volitelný (`enabled: false`) | `Dial` je nepodmíněný a blokující, default endpointu neprázdný |
| kagent credential-injection | *„matches exact DNS hostnames"* | jen defaulty per provider, `BaseURL` je přepíše |

**Pozn. Adam – poučení:** u otázek přenositelnosti je dokumentace indicie, ne důkaz.
Rozhoduje **default hodnota konfigurace** a to, **jestli je kolem volání podmínka**.
Obojí je otázka na půl hodiny čtení kódu a obojí může obrátit závěr.

**Pozn. Adam – kontrolní otázka:** *„Má tahle OSS komponenta alespoň jeden produkční
backend, který si smíme provozovat sami?"* MIT knihovna, která umí mluvit jen s jednou
hostovanou službou, není přenositelná bez ohledu na licenci.

## Pátý vzorec: governance tranzitivní závislosti

**Nadace chrání projekt, ne jeho runtime závislosti.**

**Doložený případ (ověřeno 2026-09-29):** kagent je Apache-2.0, má **DCO** a trademark
darovaný CNCF – Solo.io ho tedy nemůže jednostranně relicencovat. Jeho agentní smyčku
ale dodává **Google ADK**: jeden vendor, **CLA** (explicitně v `CONTRIBUTING.md`),
žádná nadace, žádná versioning ani support politika.

Riziko relicencování se tím na kagent nepřenáší – Apache-2.0 verze ADK zůstává.
**Přenáší se riziko směru:** tempo breaking changes, kadenci a EOL staré větve určuje
Google, ne CNCF. Konkrétně ADK vydává breaking changes v minorech, takže kagentí pin
`<3` nechrání, a ADK 1.x, na kterém jede doporučená linie v0.10.x, nemá od 2026-08-27
release ani publikované EOL.

**Pozn. Adam – kontrolní otázka:** *„Pod jakou governance je komponenta, která v tom
projektu reálně vykonává práci?"* Nadační odznak na repozitáři neříká nic o tom, kdo
vlastní dependency tree.

## Šestý vzorec: mrtvá telemetrická závislost

Ani licence, ani phone-home – a přesto nález. **Runtime závislost na analytickém SDK, kterou
kód nikde neimportuje.** License gate ji pustí (bývá MIT), síťový audit nic nenajde (nic se
neodesílá), ale SBOM ji vykáže a každý air-gap review se na ni zeptá. Je to supply-chain plocha
navíc a zároveň signál o hygieně dependency managementu.

**Doložený případ (ověřeno 2026-10-20):** `dapr-agents` 1.0.9 má v `pyproject.toml`
`posthog<8.0.0` mezi runtime závislostmi od 2025-07-07 (PR #139). V `dapr_agents/` ani nikde
v repu není `import posthog`; od té doby ho jen dependabot bumpuje (naposledy 7.60.0, 2026-10-01).

**Pozn. Adam – kontrolní otázka:** *„Které runtime závislosti se reálně importují?“*
`requires_dist` proti `grep -r` v balíčku. Půl hodiny práce, a u telemetrických SDK
(posthog, segment, sentry, mixpanel) to patří do checklistu před dodávkou.

## Sedmý vzorec: konec života deklarovaný mimo metadata

Automatika čte GitHub flag `archived` a datum posledního releasu. **Upstream ale může být
prohlášen za mrtvý v README nebo v `SUPPORT.md`, zatímco repo zůstává „živé“** – a naopak
větev může být bez releasu měsíce, aniž by kdo řekl, že skončila.

**Doložené případy (ověřeno 2026-10-20):**

| Projekt | Co říkají metadata | Co říká text |
|---|---|---|
| Microsoft AutoGen | `archived: false`, push 2026-10-16 | README od 2026-10-16: *„archived and no longer maintained … not providing bug fixes, security fixes … advise against production use“* |
| Google ADK 1.x | větev `v1` existuje, otevřené PR | žádný release od 2026-08-27, žádné publikované EOL ani `SECURITY.md` |
| MAF Go SDK | aktivní repo, v0.2.0 | README: *„public preview … evolving outside the core upstream codebase“* |

**Pozn. Adam – kontrolní otázka:** *„Kde je napsáno, že tahle linie dostane bezpečnostní
opravy, a kdo to podepsal?“* Když to nikde napsáno není, odpověď je „nevíme“ a do dodávky
patří jako riziko, ne jako předpoklad.

## Vzorce doplněné z vrstev gateway a identity (2026-10-22)

| Vzorec | Doložený případ | Jak poznat |
|---|---|---|
| **Osmý: proprietární balíček jako povinná závislost OSS proxy** | LiteLLM: `litellm-enterprise` (`LicenseRef-Proprietary`) v závislostech `litellm[proxy]`; potvrzeno instalací (0.1.76.post1 vedle 1.106.2) | Projít `requires_dist` / lock file **proxy**, ne jen `LICENSE` v rootu |
| **Devátý: rozpor LICENSE vs. metadata** | Helicone `ai-gateway`: `LICENSE` GPL-3.0, `Cargo.toml` a README Apache-2.0 | Porovnat soubor `LICENSE` s registry metadaty a README; při rozporu otázka na právníka |
| **Desátý: OSS linie bez nových minorů při živém enterprise produktu** | Kong: CE končí 3.9.x, EE na 3.16 | Matice verzí v docs vendora vs. tagy v OSS repu |
| **Jedenáctý: funkce odemykané server-side flagy s online validací klíče** | Infisical: `getDefaultOnPremFeatures()` – SSO, RBAC, audit log `false` bez klíče; licence validována proti license serveru (IP allowlist) | Hledat v kódu výčet feature flagů per licence; v docs „allow outbound connections to…“ |
| **Dvanáctý: inbound Apache bez CLA = CLA jinými slovy** | Zitadel: AGPL-3.0 runtime, příspěvky **povinně Apache-2.0** – vendor drží právo relicencovat celek | `LICENSING.md` / CONTRIBUTING: licence příspěvků ≠ licence projektu |
| **Třináctý: telemetrie opt-out u policy/authz komponenty** | SpiceDB: hodinový remote write na `telemetry.authzed.com`; Ory: Segment `sqa`; OPA: version check na api.github.com | Hledat `telemetry`, `sqa`, `version check` v konfiguraci; v air-gapu musí být vypnutelné **bez** změny kódu |
| **Čtrnáctý: telemetrie, kterou EE licence zakazuje vypnout** | Langfuse: OSS `TELEMETRY_ENABLED=false`, s EE klíčem „cannot be disabled“; SigNoz statsreporter sbírá e-maily; ClickHouse `send_crash_reports` v dodávaném configu | Číst stránku telemetry **pro EE režim**, ne jen pro OSS; kontrolovat dodávaný default config |
| **Patnáctý: AI bot nebo jeden člověk jako hlavní committer** | Jaeger: 137/300 commitů bot jednoho maintainera; MLflow: Copilot 96/300; Phoenix a OpenInference: jeden autor ~45 % | Podíl commitů podle autora za 300 commitů vč. botů – bot jako top autor znamená, že lidská kapacita je jeden člověk |
| **Šestnáctý: vertikální vlastnictví úložiště i platformy** | ClickHouse Inc. vlastní ClickHouse (CLA) i Langfuse (CLA, od 2026-01-16) | Když jeden vendor s CLA drží dvě vrstvy stacku, relicence jedné zasáhne obě – držet data v otevřeném schématu (OTLP), ne ve formátu platformy |
| **Sedmnáctý: „self-hosted“ = enterprise smlouva** | Logfire, LangSmith, Traceloop: SDK MIT/Apache, backend jen privátní image za smlouvou | Hledat Helm chart: `pullSecret`, „contact sales“, `LICENSE_KEY` v values |

## Skutečný prediktor rizika: kdo vlastní copyright

Aktuální soubor `LICENSE` říká, co platí dnes. Neříká nic o tom, co bude platit za rok.
Rozhodující je, **kdo smí licenci změnit**.

| Struktura | Může relicencovat? | Riziko | Precedenty |
|---|---|---|---|
| Jeden vendor + CLA / copyright assignment | Ano, jednostranně a bez varování | **Vysoké** | HashiCorp → BUSL, Elastic → SSPL, Redis → RSAL, Sentry → BUSL; **Temporal** (MIT + povinná CLA, ověřeno 2026-10-20), Google ADK |
| Jeden vendor **bez CLA**, ale prakticky všichni přispěvatelé zaměstnanci | Formálně jen se souhlasem přispěvatelů; fakticky ano, když jsou všichni z jedné firmy | **Střední až vysoké** | DBOS (MIT, bez CLA, jeden autor ≈ 65 % commitů) |
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
| **BUSL** (Business Source License) | **Ne** | Self-hosting obvykle ano, konkurenční služba ne | Po ~4 letech typicky konvertuje na Apache-2.0. **Rozhoduje Additional Use Grant, ne název licence:** Restate 1.8 výslovně povoluje produkční nasazení s vlastními workflow i interní managed platformu, zakazuje jen veřejnou „Restate Platform Service“ (ověřeno 2026-10-20) |
| **ELv2** (Elastic License 2.0) | **Ne** | Zákaz řízené služby, zákaz obcházení licenčních klíčů | |
| **SSPL** | **Ne** | Velmi restriktivní u poskytování služby | Může být dočasná: Inngest přidává *Grant of Future License* – každá verze je **Apache-2.0 tři roky po zpřístupnění** (ověřeno 2026-10-20) |
| Vlastní „enterprise" licence | Ne | Podle smlouvy | Typicky adresář `enterprise/` v jinak MIT repu |
| **Diagrid BSL** (BUSL 1.1 s prahy FTE a obratu) | **Ne** | **Otázka na právníka** – zákaz komerční redistribuce míří přímo na dodávku produktu | Change Date 2030-03-01 nebo 4. výročí verze, co dřív |

BUSL a ELv2 **nejsou fatální** pro produkt nasazovaný u zákazníka on-prem – bývají mířené
na konkurenční poskytovatele cloudu. Je ale nutné si to nechat potvrdit právníkem, ne architektem,
a počítat s tím, že to vyloučí model „provozujeme to jako SaaS pro víc zákazníků".

**Pozn. Adam (2026-10-20):** „BUSL“ a „SSPL“ jsou rodiny, ne verdikty. Tři BUSL/SSPL projekty
v našem poli mají tři různé grant klauzule: Restate povoluje náš scénář výslovně, Diagrid ho
výslovně zakazuje, Inngest ho po třech letech uvolňuje. Právníkovi se posílá **doslovný text
Additional Use Grant, Change Date a Change License**, ne název licence.

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
10. **Pod jakou governance jsou runtime závislosti, které dělají tu podstatnou práci?**
    Nadace chrání repozitář, ne dependency tree finálního obrazu.
11. **Které runtime závislosti se reálně importují?** Telemetrické SDK deklarované, ale nepoužité
    (`posthog` v Dapr Agents) projdou license gate i síťovým auditem, a přesto jsou nález v SBOM.
12. **Kde je napsáno, že tahle linie dostane bezpečnostní opravy?** README a `SUPPORT.md`, ne GitHub
    flag `archived` (AutoGen) ani existence větve (ADK 1.x).
13. **U BUSL / SSPL / ELv2: co doslova říká Additional Use Grant, Change Date a Change License?**
    Tři projekty, tři různé odpovědi na tentýž scénář.

## Obranný vzor: vytlačit komerční vrstvu ven

Když je monetizovanou částí durable runtime, je obranou **nenechat durable runtime vlastnit
agentní framework**. Trvalost stavu ať drží samostatná vrstva (viz [durable-execution.md](durable-execution.md))
s vlastní, ověřenou licencí. Framework se pak stává vyměnitelnou komponentou
a licenční past přestává být existenční.

Totéž platí pro přístup k modelům – viz model gateway v [overview.md](overview.md).

## Changelog
- 2026-10-23: čtrnáctý až sedmnáctý vzorec z vrstvy observability (Langfuse EE telemetrie, AI bot committer, ClickHouse+Langfuse, self-hosted = smlouva).
- 2026-10-22: osmý až třináctý vzorec z vrstev gateway a identity (LiteLLM, Helicone, Kong, Infisical, Zitadel, SpiceDB).
- 2026-09-27: první verze; doložen vzorec na `langgraph-api` (ELv2).
- 2026-10-20: re-verifikace všech doložených případů (verze a metadata k 2026-10-20); Mastra a
  LiteLLM doloženy konkrétním souborem; hygienická tabulka rozšířena (diagrid, langgraph-api,
  langgraph, LiteLLM); Diagrid Change Date per verze; přidán šestý vzorec (mrtvá telemetrická
  závislost, Dapr Agents `posthog`) a sedmý (EOL mimo metadata – AutoGen, ADK 1.x, MAF Go);
  governance tabulka o řádek „vendor bez CLA“ (DBOS) a příklad Temporal; stupnice licencí
  o grant klauzule Restate a Inngest; kontrolní otázky 11–13.
- 2026-09-29: přidán pátý vzorec (governance tranzitivní závislosti, doloženo na
  kagent → Google ADK) a kontrolní otázka 10.
- 2026-09-29: doplněno zobecnění – rozpor dokumentace vs. kód potvrzen na dvou projektech
  a v obou směrech.
- 2026-09-29: čtvrtý vzorec zpřesněn po přečtení kódu – past je v dokumentované cestě
  a v jazykovém SDK, ne ve frameworku.
- 2026-09-29: přidán čtvrtý vzorec (OSS SDK, uzavřený backend – Azure DTS); doplněna
  skrytá CLA do tabulky governance a gradace hygieny licenčních metadat.
- 2026-09-28: přidán druhý vzorec (balíček bez licenčních metadat, kagent) a třetí
  (dokumentace jako vektor, Diagrid BSL); doplněn řádek DCO do tabulky governance.
