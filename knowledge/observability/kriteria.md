---
tema: Hodnoticí kritéria pro vrstvu observability a evaluace agentů
naposledy_overeno: 2026-10-23
zralost: n/a (metodika)
primarni_zdroje:
  - https://opentelemetry.io/docs/specs/semconv/gen-ai/
  - https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai
  - https://eur-lex.europa.eu/eli/reg/2024/1689/oj
---

# Kritéria pro observabilitu a evaluaci

Rubrika pro **průřezovou vrstvu** platformy (viz [`../platforma/overview.md`](../platforma/overview.md)).
Observabilita odpovídá „co se stalo a proč“, evaluace „dělá to práci dobře“. Bez evaluace se nedá ladit paměť
ani měřit autonomie; bez observability nejde splnit audit (čl. 12 AI Act, viz [`../identity/regulace.md`](../identity/regulace.md)).

## Tři otázky, které vrstva musí zodpovědět

| # | Otázka | Co to znamená v autonomní firmě |
|---|---|---|
| O1 | **Co se stalo?** | Jeden `trace_id` od AG-UI přes orchestrátor, agenta, gateway, model i MCP nástroj; spany s tokeny, cenou, identitou (sub, agent), rozhodnutím PDP |
| O2 | **Dělá to práci dobře?** | Evaluace agentů na úrovni *trajektorie* (správné nástroje, správné pořadí, výsledek), ne jen odpovědi; regrese v CI při změně modelu, promptu, nástrojů nebo politiky |
| O3 | **Kdy zasáhnout?** | Metriky a alerty: náklady, chybovost nástrojů, smyčky, délka běhů, zásahy člověka (HITL), odchylky od evalů v provozu |

## A. Vyřazovací kritéria

Společná A1–A5 z [`../frameworks/kriteria.md`](../frameworks/kriteria.md), pro tuhle vrstvu konkrétně:

| # | Kritérium | Co to znamená tady |
|---|---|---|
| A1 | OSI licence produkčního runtimu | **Pozor na Elastic License (Arize Phoenix), BUSL a `ee/` u LLM observability platforem** (Langfuse, SigNoz) – SSO, RBAC, retence a alerty bývají za hranicí |
| A2 | Kontejnery na Kubernetes | Backend trace/metrik/logů běží u zákazníka; žádná SaaS-only platforma (LangSmith, Braintrust, Logfire cloud) jako jádro |
| A3 | Air-gapped | Žádné odesílání spanů ani evalů ven; LLM-as-judge musí jít přes **naši gateway** na model v prostředí zákazníka |
| A4 | Bez řízené služby jednoho cloudu | Azure Monitor / Application Insights smí být **backend**, ne formát – data tečou přes OTLP |
| A5 | Stav mimo framework | Traces, metriky, eval datasety a výsledky v našem úložišti (ClickHouse / Postgres / objektové) v dokumentovaném schématu |

## B. Bodovaná kritéria

### B1. Standard na drátě (O1)

| Co | Jak se to zjistí |
|---|---|
| **OpenTelemetry nativně** – OTLP export, W3C `traceparent` propagace celým řetězem | Co emituje Claude Agent SDK / Claude Code, Dapr, agentgateway, MCP SDK; kde se trace přeruší (viz harness G1: agentgateway propaguje, LiteLLM ne) |
| **GenAI semantic conventions** – stav (experimental / stable), pokrytí agentů (`gen_ai.agent.*`, `gen_ai.tool.*`), MCP spany | Semconv repo, verze; kdo je implementuje (OpenLLMetry, OpenInference, agentgateway `gen_ai`) |
| Konkurenční konvence (OpenInference) a převod | Lze převést v OTEL Collectoru, nebo nutný vendor backend |
| Atributy identity a nákladů ve spanech: `sub`, agent id, session, model+verze, tokeny vč. cache, cena, PDP rozhodnutí | Co jde z gateway (`config.tracing.fields.add`), co z hooků Agent SDK |
| Obsah promptů ve spanech **opt-in**, s maskováním PII | Default off; kde se maskuje (collector processor vs. SDK) |

### B2. Backend a úložiště (O1, O3)

| Co |
|---|
| Traces + metriky + logy v jednom stacku, nebo tři (Tempo/Mimir/Loki, Jaeger + Prometheus, ClickHouse-based) |
| Kardinalita: spany per token-call × agent × session – retence a náklady na úložiště |
| Vyhledávání v trace podle `sub`, agenta, nástroje, ceny; replay běhu z trace |
| Retence ≥ 6 měsíců konfigurovatelná per tenant (čl. 19/26 AI Act); export pro deployera (čl. 13(3)(f)) |
| Multi-tenancy (izolace traces per zákazník) v OSS, nebo za licencí |

### B3. Evaluace (O2)

| Co | Jak se to zjistí |
|---|---|
| **Trajektorie, ne jen odpověď:** správný nástroj, pořadí, argumenty, počet kroků, cena, dokončení úkolu | Podporuje framework eval nad trace/trajektorií (agent evals), nebo jen input→output |
| **Datasety z provozu:** trace → eval případ jedním krokem; anotace lidí (HITL rozhodnutí jako label) | Integrace tracing ↔ eval v jednom nástroji vs. dva nástroje |
| **LLM-as-judge** přes naši gateway, s pinnutým modelem a verzí; kalibrace proti lidským labelům | Lze nastavit `base_url`; jak se měří shoda judge ↔ člověk |
| **Judge vidí celý trace / trajektorii**, ne jednu observaci | Langfuse judge nevidí sourozence ani děti observace (2026-10-23) – pak nejde hodnotit trajektorii |
| **Bezpečnostní (red-team) generátory běží offline** | promptfoo má 26 agentních pluginů `REMOTE_ONLY` (cloud) – v air-gapu nepoužitelné |
| **Regrese v CI:** změna modelu / promptu / nástroje / politiky → eval suite jako quality gate (ADLC) | CLI, exit code, prahy, porovnání běhů |
| Reprodukovatelnost: seed, pinned model, deterministické nástroje (mock) | Lze běh přehrát z trace |
| Bezpečnostní evaly: prompt injection, nesankcionované akce (AISI 8/2026), únik tajemství | Jsou k dispozici sady, nebo vlastní |
| Metriky pro čl. 15 AI Act (přesnost, robustnost) jako evidovatelný výstup | Export výsledků s verzí systému |

### B4. Provozní metriky a alerty (O3)

| Co |
|---|
| Metriky per agent / use case / tenant: tokeny, cena, latence, chybovost nástrojů, počet kroků, HITL zásahy, odmítnutí PDP |
| Detekce smyček a runaway běhů (kroky, cena) s automatickým stopem → durable vrstva |
| Drift: odchylka provozních metrik od eval baseline |
| SLO per role agenta (dokončení úkolu, čas do schválení) |

### B5. Governance projektu a provoz

| Co |
|---|
| Licence, nadace, CLA/DCO, bus factor – jako B1 u frameworků; **telemetrie samotného nástroje** (phone-home) |
| Helm chart, HA, upgrade; SDK Python a TypeScript |
| Cena odchodu: data v OTLP/standardním schématu = přenositelná; eval datasety v otevřeném formátu (JSONL) |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| Hezký dashboard hostované verze | A4; dashboard je poslední vrstva, data první |
| Počet „integrací“ s frameworky | OTEL je jedna integrace; vendor SDK vytváří lock-in na úrovni instrumentace |
| Veřejné agentní benchmarky jako evaluace platformy | Měří model, ne naši firmu; potřebujeme evaly nad **našimi** rolemi a procesy |
| „Automatické evaly“ bez lidských labelů | Judge bez kalibrace je jen další model s názorem |

## Changelog
- 2026-10-23: B3 doplněno o „judge vidí celý trace“ a „red-team offline“ (ze síta evaluace).
- 2026-10-23: první verze; tři otázky O1–O3, kritéria B1–B5.
