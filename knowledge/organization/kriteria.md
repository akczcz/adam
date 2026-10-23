---
tema: Návrhová kritéria organizační vrstvy – role, procesy, hranice autonomie a schvalovací body virtuální IT firmy
naposledy_overeno: 2026-10-23
zralost: n/a (metodika návrhu)
primarni_zdroje:
  - knowledge/platforma/cilova-architektura.md (rozhodnuté vrstvy 1–7, hypotéza organizační vrstvy)
  - knowledge/identity/regulace.md (AI Act požadavky T1–T15, čl. 14 lidský dohled, čl. 50 transparentnost)
  - knowledge/observability/evaluace.md (vrstvy evaluace L0–L5, approval policy)
  - knowledge/memory/model-pameti.md (co role potřebují z paměti)
---

# Kritéria pro organizační vrstvu

Poslední vrstva platformy (viz [`../platforma/overview.md`](../platforma/overview.md)). Je **návrhová, ne rešeršní**:
nehledá se komponenta, skládá se **firma** z rozhodnutých vrstev. Výstupem není síto, ale návrh, který jde
změřit evaly rolí (L0–L5) a provozními metrikami. Vstupem je sedm rozhodnutí v
[`../platforma/cilova-architektura.md`](../platforma/cilova-architektura.md) a požadavky AI Act (T1–T15).

## Zásada

**Firma je sada procesů; role jsou odvozené.** Nejdřív se popíše, co firma dodává a jak zakázka teče
(vstupy, výstupy, předání, schvalovací body), teprve pak se procesům přiřadí role. Role = svazek
**oprávnění** (identita, OPA), **rozpočtu** (gateway), **scope paměti** (tenant/firma), **sandboxu** (obraz, egress)
a **metrik** (evaly, SLO). Agent je instance role v konkrétním procesu, ne osobnost.

## Čtyři otázky, které vrstva musí zodpovědět

| # | Otázka | Co to znamená v autonomní firmě |
|---|---|---|
| O1 | **Co firma dodává a jak zakázka teče?** | Katalog procesů od poptávky po provoz: stavy, vstupy/výstupy, kdo předává komu, kde je nevratný krok; každý proces = Dapr Workflow s HITL body |
| O2 | **Jaké role a s jakými hranicemi?** | Matice rolí: co smí (nástroje, repa, prostředí), za kolik (rozpočet per role a zakázku), co si pamatuje (scope), kde pracuje (sandbox profil), kdo ji eskaluje |
| O3 | **Kde končí autonomie?** | Schvalovací body v procesu, ne v promptu: nevratné akce (push do main, deploy, platba, smazání, komunikace ven), klasifikace rizika use casu zákazníka (AI Act), výjimky |
| O4 | **Jak se pozná, že firma dělá práci dobře a kdo za to odpovídá?** | Metriky per role a proces (evaly L2–L5, pass^k, SLO, cena per úkol), odpovědný člověk per proces, registr agentů (T12), risk register (T11), post-mortem procesu |

## A. Zásady návrhu (vyřazovací – návrh, který je poruší, se vrací)

| # | Zásada | Proč |
|---|---|---|
| A1 | **Hranice autonomie v procesu** (Dapr Workflow aktivita „approve“), ne v instrukci modelu | prompt injection je výchozí stav; HITL musí přežít restart (dny) |
| A2 | **Každá akce má identitu, rozpočet a stopu** – role bez SVID, rozpočtu v gateway a trace do ClickHouse neexistuje | AI Act čl. 12 logování, FinOps, incident response |
| A3 | **Paměť je firemní** – role čte scope podle tenanta a citlivosti, nikdy „svou“ paměť | rozhodnuto ve vrstvě paměti |
| A4 | **Agent se představí** (čl. 50 od 2.8.2026) – každý kanál k lidem architektonicky | regulace T7 |
| A5 | **Jeden člověk odpovídá za každý proces** – „autonomní“ neznamená bez vlastníka | čl. 14 lidský dohled, odpovědnost vůči zákazníkovi |
| A6 | **Role je přenositelná** – definice role = YAML (oprávnění, rozpočet, scope, sandbox profil, evaly), ne kód agenta | vyměnitelnost modelu i frameworku |

## B. Bodovaná kritéria návrhu

### B1. Procesy (O1)

| Co | Jak se to pozná |
|---|---|
| Každý proces má stavový diagram, vstup/výstup, SLA a vlastníka | Mermaid v `overview.md`, tabulka procesů |
| Nevratné kroky označené a kryté schvalovacím bodem nebo reverzibilní alternativou | seznam nevratných akcí per proces |
| Předání mezi rolemi = A2A úkol s artefaktem (PR, ADR, runbook), ne volný chat | kontrakt předání |
| Proces jde spustit v harnessu (mock role) a změřit end-to-end | harness O-1 |

### B2. Role (O2)

| Co |
|---|
| Minimální oprávnění per role: nástroje (MCP), repa, prostředí, data; napsáno jako Rego/OPA |
| Rozpočet per role a zakázku (gateway API klíč per role/tým – rozhodnuto v gateway), limit a eskalace při překročení |
| Scope paměti (tenant, firma, platforma) a co role smí zapisovat (`proposed`) vs. schvalovat |
| Sandbox profil (obraz role, egress allow-list, approval na nevratné akce) |
| Evaly role (L0–L5) s gate a pass^k; co se stane při propadu (role se stáhne z procesu) |

### B3. Hranice autonomie (O3)

| Co |
|---|
| Katalog nevratných akcí a kdo je schvaluje (člověk, reviewer-agent + člověk, jen agent) |
| Klasifikační brána zákazníkova use casu (příloha III → jiný proces s vyšším dohledem) |
| Eskalační cesty: agent → reviewer → vlastník procesu → člověk zákazníka; timeouty HITL |
| Stop tlačítko per proces a per tenant (T6) – a co se stane s rozpracovanou prací |

### B4. Výkon a odpovědnost (O4)

| Co |
|---|
| Metriky per proces: doba cyklu, podíl HITL odmítnutí, cena per zakázka (gateway), incidenty |
| Registr agentů (T12) a risk register (T11) jako data v paměti platformy, ne dokument |
| Post-mortem procesu s poučením do procedurální paměti (git) |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| „Agent jako osobnost“ (jméno, charakter, vlastní paměť) | role je svazek oprávnění; osobnost nemá audit |
| Org chart lidské firmy 1:1 | lidská firma má role kvůli lidem; tady se role odvozují z procesů a nevratných kroků |
| Autonomie jako cíl | autonomie je důsledek změřené spolehlivosti role v procesu, ne nastavení |
| Multiagentní „debaty“ bez artefaktu | předání bez artefaktu se nedá auditovat ani evaluovat |

## Changelog
- 2026-10-23: první verze; zásada „procesy první“, otázky O1–O4, zásady A1–A6, kritéria B1–B4.
