---
tema: EU AI Act, ISO/IEC 42001 a NIST AI RMF – co z nich plyne pro identitu, audit a lidský dohled platformy
naposledy_overeno: 2026-10-22
zralost: preview (harmonogram ověřen ze shody sekundárních zdrojů a výňatků primárních; text OJ nečten)
primarni_zdroje:
  - https://eur-lex.europa.eu/eli/reg/2024/1689/oj
  - https://digital-strategy.ec.europa.eu/en/news/ai-omnibus-enters-force
  - https://ai-act-service-desk.ec.europa.eu/en/ai-act/faq/how-are-ai-agents-addressed-within-ai-act-0
  - https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-26
  - https://digital-strategy.ec.europa.eu/en/library/draft-commission-guidelines-classification-high-risk-ai-systems
  - https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai
  - https://www.cencenelec.eu/news-events/news/2026/en-in-the-spotlight/2026-10-15-en-18286-2026-published-in-ojeu/
  - https://www.oecd.org/en/publications/agentic-ai-in-organisations_1257a26f-en.html
  - https://www.aisi.gov.uk/research
---

# Regulace a governance: co platforma musí umět

**Metodická poznámka (2026-10-22):** EUR-Lex, digital-strategy.ec.europa.eu, nist.gov, iso.org a oecd.org
nebyly z rešeršního prostředí dostupné. Fakta stojí na **výňatcích primárních stránek** přes vyhledávač
(označeno *prim.*) a na **shodě ≥ 4 právnických komentářů** (Bird & Bird, Freshfields, Orrick, Sidley, Cooley –
označeno *sek.*). Vlastní výklad je označen *výklad*. Před použitím v dokumentaci pro zákazníka
**ověřit text v OJ** – priority v sekci „Co ověřit dál“.

## Závěr: harmonogram k 2026-10-22

AI Act (2024/1689) byl novelizován nařízením **(EU) 2026/1744** („Digital Omnibus on AI“, OJ 24.7.2026,
účinné 27.7.2026 – *prim. výňatek + sek.*). Dopad na platformu:

| Povinnost | Termín | Stav | Co z toho plyne pro platformu |
|---|---|---|---|
| Zakázané praktiky (čl. 5), AI literacy (čl. 4) | 2.2.2025 | platí; čl. 4 Omnibusem změkčen (*sek.*) | Policy engine umí zablokovat **use case**, ne jen prompt |
| GPAI modely (kap. V) | 2.8.2025 | platí; týká se Anthropic, ne nás; Komise vymáhá od 2.8.2026 | Gateway eviduje **model + verzi** per request |
| Transparentnost čl. 50(1) – interakce s člověkem | 2.8.2026 | **platí, bez odkladu** (*prim.*) | Každý kanál k lidem oznamuje „jsem AI, jednám za X“ |
| Transparentnost čl. 50(2) – značení generovaného obsahu | 2.8.2026; systémy na trhu před tím → 2.12.2026 | platí / grace (*sek.*, shoda 4) | Značit výstupy pro lidi; API a mezikroky ne (final guidelines 20.7.2026) |
| Nové zákazy čl. 5 (NCII, CSAM) | 2.12.2026 | přijato, zatím neplatí (*sek.*) | Content policy ve výstupní vrstvě |
| **Vysoce rizikové – příloha III** | ~~2.8.2026~~ → **2.12.2027** | **odloženo** 2026/1744 (*prim.*/*sek.*) | Pokud zákazník nasadí agenty v příloze III, čl. 12/13/14 „by design“ |
| Vysoce rizikové – příloha I | ~~2.8.2027~~ → 2.8.2028 | odloženo | mimo náš scénář |
| Harmonizovaná norma QMS **EN 18286:2026** (čl. 17) | OJ 14.10.2026, prov. rozh. (EU) 2026/2274 | presumpce shody (*sek.* 4 zdroje + CEN-CENELEC) | První norma, podle které zákazník audituje náš QMS |
| Ostatní normy JTC 21 (risk mgmt, logging, oversight) | mandát do 28.2.2027 | ve vývoji | Zatím ISO 42001 + čl. 12/14 doslova |
| Guidelines ke klasifikaci high-risk (čl. 6(5)) | zákonný termín 2.2.2026 nedodržen | **jen návrh** 19.5.2026 (*prim.*) | Multiagentní systém = **jeden AI systém**, pokud kombinovaný výstup ovlivňuje high-risk rozhodnutí |

## Co dopadá na platformu (ne na organizaci zákazníka)

### Klasifikace rizika (*výklad* nad ověřeným textem přílohy III)

- Vývoj a provoz software v příloze III **není**. Platforma pro ADLC je sama o sobě ne-vysoce-riziková.
- **Příloha III bod 4 (zaměstnanost)** pokrývá i **přidělování úkolů** a **hodnocení výkonu osob**; návrh
  guidelines 19.5.2026 výslovně „task allocation“, „performance management“. → Jakmile agent přiděluje práci
  **lidem** nebo hodnotí lidské reviewery, use case zákazníka spadá do bodu 4. Alokace mezi agenty ne.
- **Příloha III bod 2 (kritická infrastruktura)**: safety komponenty v provozu kritické digitální infrastruktury;
  návrh guidelines váže na entity podle směrnice CER. → Agent SRE u takového zákazníka **může** být safety component.
- Platformu **nelze rozdělit** na malé ne-rizikové agenty – návrh guidelines: více interagujících komponent
  s kombinovaným výstupem = jeden systém.

### Provider vs. deployer (čl. 25, *výklad*)

My = **provider** platformy. Zákazník = **deployer**; providerem se stane, když platformu označí vlastní značkou,
provede substantial modification, nebo změní intended purpose do high-risk. → Smlouva a technická dokumentace
**vymezí intended purpose** tak, aby body 2 a 4 přílohy III byly explicitně pokryty, nebo explicitně vyloučeny.

### Čl. 12 záznamy, čl. 19/26 retence (*prim. výňatky*)

- 12(1): systém **technicky umožní automatické zaznamenávání událostí** po celou dobu života.
- 12(2): logy umožní identifikaci rizikových situací a substantial modification, post-market monitoring (čl. 72),
  monitoring deployerem (čl. 26(5)).
- 12(3): minimální obsah definován jen pro biometrii (čas začátku/konce, referenční DB, vstup vedoucí ke shodě,
  identita ověřujících osob). *Výklad:* pro ostatní je obsah odvozen z 12(2) – rekonstruovatelné „co, kdy,
  s jakým vstupem, jaký výstup, kdo potvrdil“.
- Retence **≥ 6 měsíců** provider (čl. 19) i deployer (čl. 26(6)), delší podle sektorového práva.

### Čl. 14 lidský dohled (*prim.*)

Osoby musí moci: (a) chápat limity a **monitorovat**; (b) uvědomovat si **automation bias**; (c) interpretovat
výstup; (d) **nepoužít / přepsat / zvrátit** výstup; (e) **zasáhnout nebo zastavit** do bezpečného stavu.
Provider navrhuje, deployer přiděluje osoby (čl. 26(2)).

### Čl. 13 informace deployerovi (*prim.*, částečně)

Instrukce obsahují opatření lidského dohledu vč. technických prostředků pro interpretaci výstupů (13(3)(d))
a **mechanismy, jak deployer sbírá, uchovává a interpretuje logy** (13(3)(f)).

### Čl. 50 transparentnost (final guidelines 20.7.2026, *prim. výňatky via sek.*)

- 50(1): agenti interagující s lidmi (korespondence, vyjednávání, smlouvy) musí být **architektonicky** navrženi
  tak, aby oznámili AI povahu **a za koho jednají** – i osobě, která agenta instruuje, v klíčových krocích.
- 50(2): mezikroky a **strojové výstupy (API) se neznačí**. Zda generovaný **zdrojový kód** předaný člověku
  je „text“ ve smyslu 50(2) – **neověřeno**.

### GPAI – kdy bychom se stali providerem modelu (guidelines 2025, *sek.* shoda 5)

Downstream modifier je providerem, pokud compute modifikace > **1/3** tréninkového compute původního modelu.
*Výklad:* prompting, RAG, tool-use, orchestrace ani fine-tuning přes API tento práh nedosáhnou. Jsme provider
**AI systému**, ne GPAI modelu.

## Code of Practice a guidelines Komise

| Dokument | Datum | Stav |
|---|---|---|
| GPAI Code of Practice | 10.7.2025; signatáři od 1.8.2025 (**Anthropic** mezi nimi, oznámeno 21.7.2025 – *prim.*) | platný, dobrovolný; aktuálnost seznamu k 10/2026 neověřena |
| Guidelines – zakázané praktiky | 4.2.2025, formálně C(2025) 5052 | platné, nezávazné |
| Guidelines – definice AI systému | 6.2.2025, formálně C(2025) 5053 | platné, nezávazné |
| Guidelines – GPAI providers | 18.7.2025 (C(2025) 5045) | platné |
| Guidelines – čl. 50 transparentnost | návrh 8.5.2026, **finál 20.7.2026** | platné, nezávazné |
| Code of Practice – značení AI obsahu (čl. 50(2),(4)) | finál 10.6.2026; signatáři 31.7.2026 (~190, Anthropic v sekci poskytovatelů – *prim.*) | platný |
| Guidelines – klasifikace high-risk (čl. 6(5)) | **návrh 19.5.2026** | **nefinální** |

## ISO/IEC 42001 a NIST AI RMF – technické požadavky

- **ISO/IEC 42001:2023** (beze změny; 42005:2025 impact assessment, 42006:2025 certifikační orgány). Z přílohy A
  přímo pro platformu: **A.6.2.8 event logs** (tamper-evident, per fáze lifecycle), A.6.2.6 monitoring,
  A.6.2.7 dokumentace, A.3 role, A.5 impact assessment, A.8 reporting incidentů, A.9 intended use,
  A.10 dodavatelé (Anthropic, Azure). Lidský dohled není samostatná kontrola.
- **NIST AI RMF 1.0 + Generative AI Profile (AI 600-1, 26.7.2024)**: MAP 3.5 procesy lidského dohledu
  dokumentovány; 12 rizik GenAI (confabulation, prompt injection, …). Žádné konkrétní logging požadavky.

## Specifika autonomních agentů – co je oficiální

- **AI Office** (Service Desk FAQ, *prim.*): úvahy o agentech jsou „preliminary“; **žádný samostatný guidance
  dokument k agentům k 2026-10-22 neexistuje**. Tvrdé body: čl. 50 final guidelines (agenti jednající za lidi)
  a návrh guidelines high-risk (multi-komponentní systém = jeden systém). GPAI CoP Measure 5.1 bod 7 (agentní
  použití v risk managementu).
- **OECD** „Agentic AI in organisations“ (9/2026, *prim. výňatek*): posun k **dynamickému, distribuovanému
  dohledu**; least privilege, sandbox, kontinuální monitoring, **registr schválených agentů**.
- **NIST/CAISI**: AI Agent Standards Initiative (17.2.2026); SP 800-53 overlays pro agenty (COSAiS)
  k 8/2026 nepublikovány; NCCoE doporučuje OAuth 2.0 / OIDC / **SPIFFE/SPIRE** pro identitu agentů (*sek.*).
- **UK AISI** (*prim. výňatky*): „Loss of Oversight“ (21.5.2026); „Multi-Agent AI Control“ – **per-instance
  monitory nestačí**, útok lze rozložit mezi agenty; nesankcionované akce agentů v evaluacích (8/2026),
  mj. pokus o supply-chain kompromitaci zastavený **lidským code review**.

## Technické požadavky na platformu (odvozeno, *výklad*)

| # | Požadavek | Kotva |
|---|---|---|
| T1 | Každý request nese **principal (člověk) + role agenta + delegační řetězec**, propagováno přes `trace_id` do policy decision logu i MCP volání | čl. 12(2), 26(2), 50(1); ISO A.3 |
| T2 | Logging je **vlastnost platformy** (automatický), per fáze lifecycle, **append-only + podepsaný**, exportovatelný deployerovi | čl. 12(1), 13(3)(f); A.6.2.8 |
| T3 | Minimální schéma záznamu: session start/end, vstup, kontext/RAG zdroje, výstup, nástroj + parametry, **model + verze + provider**, verze policy, rozhodnutí HITL + identita schvalovatele, náklad | čl. 12(2)–(3), 14(4)(d), 72 |
| T4 | Retence ≥ 6 měsíců default, per tenant konfigurovatelná výš; retence je **tenant policy** | čl. 19, 26(6) |
| T5 | **Stop/interrupt** na úrovni durable workflow (Dapr), ne promptu; zastavení vede do bezpečného stavu | čl. 14(4)(e) |
| T6 | HITL rozhraní ukazuje limity výstupu, vyžaduje důvod schválení (proti automation bias), umožňuje override | čl. 14(4)(a)–(d) |
| T7 | Disclosure „jsem AI, jednám za X“ **architektonicky** u každého kanálu k lidem (chat, e-mail, PR komentář, ticket) | čl. 50(1) + guidelines 20.7.2026 |
| T8 | Značení generovaného obsahu pro lidi; API a mezikroky ne; **kód otevřená otázka** | čl. 50(2) |
| T9 | **Klasifikační brána use casu** při onboardingu zákazníka (HR / alokace práce lidem → III/4; provoz u CER entit → III/2) → „high-risk profil“ s T2–T6 povinně a zdůvodněním čl. 6(3) | čl. 6, příloha III |
| T10 | **Change management**: verze modelu / promptu / nástrojů / policy jako evidovaná změna s posouzením substantial modification | čl. 12(2)(a), 25; A.6.2.5 |
| T11 | Risk register per zákazník / use case (NIST GenAI rizika, ISO 42005) | A.5; AI 600-1 |
| T12 | **Registr agentů** (role, oprávnění, vlastník) + least privilege; **cross-agent monitoring**, ne jen per-instance | OECD 9/2026; AISI |
| T13 | Produkční oprávnění agenta SRE **jen po lidském schválení**, časově omezené (token exchange), auditované | čl. 14, 26(2); AISI 8/2026 |
| T14 | Doložitelné nepřekročení 1/3 prahu GPAI (žádný trénink v platformě) | GPAI guidelines 2025 |
| T15 | QMS dokumentace podle **EN 18286:2026** | prov. rozh. (EU) 2026/2274 |

**Pozn. Adam:** T1, T2, T3, T5, T12 a T13 jsou přímé požadavky na vrstvu identity a na Dapr workflow;
T7 a T8 na AG-UI; T9–T11 a T15 na organizační vrstvu. Harmonogram příloha III (2.12.2027) dává čas,
ale čl. 50 **platí už teď** – disclosure v kanálech k lidem je první věc k implementaci.

## Co ověřit dál

- [ ] **Text OJ** nařízení 2026/1744 a konsolidovaného 2024/1689 (EUR-Lex): znění čl. 4, 111; zda Omnibus měnil čl. 12/14/19.
- [ ] Prov. rozhodnutí (EU) 2026/2274 – text v OJ.
- [ ] Final guidelines čl. 50: zda generovaný **kód** předaný člověku podléhá značení.
- [ ] Finální guidelines ke klasifikaci high-risk – stav přijetí.
- [ ] Aktuální seznam signatářů GPAI CoP (snapshot ~8/2025).
- [ ] NIST COSAiS overlays – stav po 8/2026.
- [ ] Český dozorový orgán a implementační zákon.

## Changelog
- 2026-10-22: první verze z rešerše; harmonogram po Omnibusu 2026/1744, požadavky T1–T15.
