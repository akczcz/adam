---
tema: Licenční vzorce a pasti v open-source AI frameworcích
naposledy_overeno: 2026-09-27
zralost: n/a (metodika)
primarni_zdroje:
  - https://pypi.org/project/langgraph-api/
  - https://github.com/temporalio/temporal/blob/main/LICENSE
  - https://www.cncf.io/projects/dapr/
  - https://docs.litellm.ai/docs/enterprise
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

## Skutečný prediktor rizika: kdo vlastní copyright

Aktuální soubor `LICENSE` říká, co platí dnes. Neříká nic o tom, co bude platit za rok.
Rozhodující je, **kdo smí licenci změnit**.

| Struktura | Může relicencovat? | Riziko | Precedenty |
|---|---|---|---|
| Jeden vendor + CLA / copyright assignment | Ano, jednostranně a bez varování | **Vysoké** | HashiCorp → BUSL, Elastic → SSPL, Redis → RSAL, Sentry → BUSL |
| Projekt pod nadací (CNCF, ASF, LF AI & Data) | Prakticky ne – copyright je rozptýlený mezi přispěvatele | **Nízké** | Kubernetes, Dapr, OpenTelemetry |

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

## Obranný vzor: vytlačit komerční vrstvu ven

Když je monetizovanou částí durable runtime, je obranou **nenechat durable runtime vlastnit
agentní framework**. Trvalost stavu ať drží samostatná vrstva (viz [durable-execution.md](durable-execution.md))
s vlastní, ověřenou licencí. Framework se pak stává vyměnitelnou komponentou
a licenční past přestává být existenční.

Totéž platí pro přístup k modelům – viz model gateway v [overview.md](overview.md).

## Changelog
- 2026-09-27: první verze; doložen vzorec na `langgraph-api` (ELv2).
