---
tema: Hodnoticí kritéria pro výběr agentního frameworku
naposledy_overeno: 2026-09-29
zralost: n/a (metodika)
primarni_zdroje:
  - https://www.cncf.io/project-metrics/
---

# Kritéria výběru agentního frameworku

Rubrika pro případ **přenositelné multiagentní platformy dodávané do prostředí zákazníka**
(public cloud i on-premises), provozované v regulovaném odvětví.

Pořadí není náhodné – od vyřazovacích kritérií k bodovaným.

## A. Vyřazovací kritéria (splň, nebo vypadni)

Tyhle se nebodují. Kdo neprojde, nepostupuje do hloubkového kola.

| # | Kritérium | Proč vyřazuje |
|---|---|---|
| A1 | Produkční runtime je v OSI-schválené licenci | Jinak je produkt rukojmím vendora přesně ve chvíli, kdy začne škálovat |
| A2 | Běží jako obyčejné kontejnery na Kubernetes | Jediný reálný společný jmenovatel Azure / AWS / GCP / on-prem |
| A3 | Funguje bez odchozího spojení (air-gapped) | Telemetrie, kontrola licenčního klíče a hostovaný tracing diskvalifikují |
| A4 | Nevyžaduje řízenou službu jednoho cloudu | Jinak to není přenositelné, jen přenosně vypadající |
| A5 | Stav běhu lze uložit mimo framework | Podmínka vyměnitelnosti frameworku |

## B. Bodovaná kritéria

### B1. Licence a governance (váha: nejvyšší)

| Co | Jak se to zjistí |
|---|---|
| Licence produkčního runtimu, ne jen knihovny | Viz [licencni-vzorce.md](licencni-vzorce.md) |
| Vyžaduje projekt CLA? | `CONTRIBUTING.md`, bot u PR |
| Vlastní projekt nadace? Jaký stupeň zralosti? | CNCF Sandbox / Incubating / Graduated |
| Existuje adresář `enterprise/`, `ee/`, `pro/`? | Strom repozitáře |
| Bus factor – kolik přispěvatelů mimo hlavního vendora? | Statistiky přispěvatelů; **ověř i podíl commitů, nejen počet maintainerů** |
| **Vztahuje se stupeň zralosti nadace na *tuhle* komponentu?** | Porovnej datum graduace s `created_at` repozitáře sub-projektu |
| **Má komponenta vlastní support a versioning policy?** | `SUPPORT.md`, `docs/versioning` – politika runtimu na sub-projekt platit nemusí |
| **Byly po GA breaking changes v patch releasech?** | Release notes od tagu `v1.0.0` dál |
| **Deklaruje publikovaný balíček licenci strojově čitelně?** | Registry JSON API – `license`, `license_expression` (SPDX), OSI classifier |
| **Vlastní kdokoliv jiný balíčky, které dokumentace doporučuje instalovat?** | Owner **každého** balíčku ve finálním lock filu |
| **Pod jakou governance je runtime závislost, která vykonává práci?** | Dependency tree finálního obrazu, ne jen hlavní repo – nadace chrání repozitář, ne `pip install` |

### B2. Trvalost stavu a odolnost

| Co | Proč to je nahoře |
|---|---|
| Přežije rozpracovaný běh restart procesu i celého clusteru? | Bez toho nelze provozovat dlouhoběžící agenty |
| Kde je uložený stav a jde ho vzít jinam? | Určuje cenu odchodu |
| Umí pozastavit běh na lidské rozhodnutí na dny až týdny? | Schvalovací body v regulovaném procesu nemají hodinový horizont |
| Je trvalost součástí OSS části, nebo komerční? | Nejčastější místo licenční pasti |
| **Je durable komponenta sama stavová a lze ji škálovat?** | Stavový singleton v control plane je skrytá provozní past |
| **Má durable vrstva alespoň jeden produkční backend, který si smíme provozovat sami?** | MIT knihovna mluvící jen s hostovanou službou není přenositelná bez ohledu na licenci |
| **Je obnovení běhu exactly-once, nebo at-least-once?** | At-least-once resume za schvalovacím bodem znamená riziko dvojího provedení neidempotentní akce |

### B3. Přenositelnost a hranice

| Co |
|---|
| Sedí čistě za protokolovou hranicí (A2A / MCP / AG-UI), nebo vnucuje vlastní API? |
| Kolik kódu agenta je na framework vázaného? |
| Je přístup k modelům abstrahovaný, nebo natvrdo na jednoho poskytovatele? |
| Cena odchodu: co zůstane funkční, když se framework vymění? |

### B4. Izolace a bezpečnost

| Co |
|---|
| Izolace selhání – položí pád jednoho agenta ostatní? |
| Sandbox pro spouštění nástrojů; může nástroj eskalovat oprávnění agenta? |
| Propagace identity koncového uživatele celým během |
| Vynutitelná pravidla, kdo koho smí volat |
| Omezení hloubky delegací (obrana proti kaskádě) |

### B5. Determinismus a auditovatelnost

| Co |
|---|
| Lze oddělit deterministický úsek od úseku řízeného modelem? |
| Dá se běh přehrát a dostat identický výsledek? |
| Vzniká auditní stopa automaticky, nebo se dopisuje? |
| Lze přišpendlit verzi modelu a vynutit ji? |

### B6. Observabilita

| Co |
|---|
| OpenTelemetry bez vlastní instrumentace? |
| Jeden `trace_id` přes celý běh napříč službami |
| Metriky tokenů s vlastními dimenzemi (kdo, který agent, který use-case) |
| Funguje s libovolným OTEL backendem, nebo jen s vendorovým? |

### B7. Provozní zralost

| Co |
|---|
| Horizontální škálování per agent |
| Upgrade a výpadek per agent, ne per platforma |
| Plánované a dávkové běhy |
| Kvalita Helm chartu / operátoru |
| Politika verzování a LTS |

### B8. Ekosystém a jazyky

| Co |
|---|
| Podporované runtimy (Python, TypeScript, Java, .NET, Go) |
| Nativní podpora MCP jako klient i server |
| Nativní podpora A2A |
| Živost projektu – release kadence, otevřené issues, reálná nasazení |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| Počet hvězd na GitHubu | Měří marketing, ne provozní zralost |
| Skóre na veřejných agentních benchmarcích | Měří model, ne framework – viz níže |
| Počet integrací a konektorů | U protokolové hranice je nahrazuje MCP |
| „Používá to firma X" | Bez znalosti jejich požadavků to nevypovídá o ničem |

### Proč veřejné benchmarky neměří framework

SWE-bench, GAIA, τ-bench a podobné měří schopnost **modelu**. Když se na nich porovnají
frameworky, naměří se hlavně to, jaký model byl pod ně dosazený.

Pro rozhodnutí o platformě je potřeba **platformní benchmark**: stejný model, stejná úloha,
mění se jen framework. Měří se:

| Veličina | Co prozradí |
|---|---|
| Režie frameworku vs. holé volání modelu (P50/P95) | Kolik latence stojí samotná orchestrace |
| Přežití běhu přes restart | Zda trvalost stavu skutečně funguje |
| Pozastavení a obnovení po dnech | Použitelnost schvalovacích bodů |
| Determinismus opakovaného běhu | Zda jde přehrát |
| Propustnost při desítkách souběžných agentů | Kde je strop |
| Izolace selhání | Zda pád jednoho agenta položí ostatní |
| Věrnost OTEL spanů bez vlastní instrumentace | Kolik observability je zadarmo |
| Cold start | Náklad na škálování na nulu |

Tenhle benchmark veřejně nikdo neprovozuje – je to práce na vlastní harness.

## Changelog
- 2026-09-27: první verze.
- 2026-09-29: do B1 přidána governance runtime závislostí, do B2 sémantika obnovení běhu.
- 2026-09-29: do B2 přidána otázka na vlastní provozovatelný backend durable vrstvy.
- 2026-09-28: do B1 přidána zralost sub-projektu, support policy, breaking changes,
  deklarace licence v registry a vlastnictví doporučovaných balíčků; do B2 škálovatelnost
  durable komponenty.
