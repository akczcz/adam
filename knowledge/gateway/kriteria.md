---
tema: Hodnoticí kritéria pro výběr model gateway
naposledy_overeno: 2026-10-22
zralost: n/a (metodika)
primarni_zdroje:
  - https://code.claude.com/docs/en/llm-gateway-protocol
  - https://platform.claude.com/docs/en/build-with-claude/claude-in-microsoft-foundry
  - https://platform.openai.com/docs/api-reference/chat
---

# Kritéria výběru model gateway

Rubrika pro vrstvu **model gateway** v přenositelné multiagentní platformě
(viz [`../platforma/overview.md`](../platforma/overview.md)). Gateway je **jediný šev
mezi agenty a poskytovateli modelů** – oddělí Azure OpenAI / AI Foundry od Bedrocku, Vertexu
a lokálního vLLM a zároveň je místem, kde se vynucují rozpočty, limity a audit.

## A. Vyřazovací kritéria

Platí společná A1–A5 z [`../frameworks/kriteria.md`](../frameworks/kriteria.md#a-vyřazovací-kritéria-splň-nebo-vypadni),
pro tuhle vrstvu konkrétně:

| # | Kritérium | Co to znamená pro gateway |
|---|---|---|
| A1 | OSI licence produkčního runtimu | Licenci má **proxy/server**, ne jen klientské SDK. Pozor na `enterprise/` a na funkce, které se v OSS buildu odemykají licenčním klíčem |
| A2 | Kontejnery na Kubernetes | Helm chart nebo alespoň image bez vazby na řízenou službu |
| A3 | Air-gapped provoz | Žádná kontrola licenčního klíče přes síť, žádná telemetrie bez opt-out, model ceníky a seznamy modelů lze načíst ze souboru |
| A4 | Bez řízené služby jednoho cloudu | Hostované gateway (Cloudflare AI Gateway, Azure APIM GenAI, OpenRouter, Portkey cloud) padají **jako jádro platformy**; smí být *backendem* za naší gateway |
| A5 | Stav mimo framework | Klíče, rozpočty, útrata a audit log leží v **naší** databázi (Postgres / Redis), v dokumentovaném schématu |

## B. Bodovaná kritéria

### G1. Protokolová věrnost (váha: nejvyšší)

Agentní smyčka platformy je **Claude Agent SDK** (rozhodnutí 2026-10-21, viz
[`../frameworks/overview.md`](../frameworks/overview.md)). Gateway, která umí jen OpenAI-kompatibilní
`chat/completions`, proto nestačí.

Referenční kontrakt publikuje Anthropic: [LLM gateway protocol](https://code.claude.com/docs/en/llm-gateway-protocol)
(ověřeno 2026-10-22). Gateway, která ho nesplní, rozbije Agent SDK tiše – ztrátou cache nebo nových beta funkcí.

| Co | Jak se to zjistí |
|---|---|
| **Nativní průchod Anthropic Messages API** (`/v1/messages`), ne překlad přes OpenAI formát | Dokumentace proxy, endpoint `/anthropic/*` nebo ekvivalent; test s `ANTHROPIC_BASE_URL` |
| **`anthropic-beta` a `anthropic-version` forwardovány jako otevřený seznam**, ne allowlist | Docs gateway; harness s neznámou beta hlavičkou. Bifrost ji by default blokuje |
| `system` pole nepřeskládané, `ping` eventy nebufferované, chybová těla upstreamu neobalená | Kontrakt výše; harness |
| Atribuční hlavičky `x-claude-code-session-id` / `-agent-id` / `-parent-agent-id` dostupné jako dimenze útraty | Docs gateway: lze z hlaviček dělat labely metrik a klíče rozpočtů? |
| Zachová **prompt caching** (`cache_control`, `cache_read_input_tokens` v usage) | Bez toho platforma platí násobně víc za každý turn agenta |
| Zachová **tool use** beze ztráty – `tool_use`/`tool_result` bloky, paralelní volání, `input_schema` | Překlad OpenAI ↔ Anthropic tool formátů je nejčastější místo tiché ztráty |
| Streaming (SSE) beze změny semantiky eventů | Agent SDK streamuje vždy |
| Extended thinking, structured outputs, PDF/obrázky, batches | Co z toho gateway *ořeže* |
| OpenAI-kompatibilní API pro ostatní smyčky a nástroje | Druhá nejčastější hranice |
| Backend pro **Azure OpenAI / AI Foundry** (deployment names, API versions, Entra ID auth), Bedrock, Vertex, vLLM/Ollama | Azure je výchozí cílové prostředí |
| Překlad Anthropic → jiný poskytovatel (fallback Claude na model jiného vendora) a jeho omezení | Marketing říká „any model"; ověřit, co se při překladu ztrácí |

### G2. FinOps

| Co |
|---|
| Rozpočty a limity per **klíč, tým, agent, use-case, koncový uživatel** – a jejich kombinace (tenant → tým → agent) |
| Kde se útrata počítá a ukládá; lze ceník modelů (Azure ceny) dodat vlastní |
| Reakce na vyčerpaný rozpočet: hard stop vs. alert vs. degradace na levnější model |
| Export útraty (API, Prometheus metriky, CSV) s vlastními dimenzemi (tagy z requestu) |
| Rate limiting (RPM/TPM) per klíč a per backend deployment |
| Cost-aware routing (levnější model pro jednoduché úlohy) – je, a je deterministický? |

### G3. Odolnost a routing

| Co |
|---|
| Retry, timeout, fallback mezi deploymenty a poskytovateli – konfigurovatelné per model |
| Load balancing mezi Azure deploymenty / regiony (TPM-aware) |
| Cache odpovědí (exact / semantic) – vypnutelná, uložená v našem Redisu |
| Chování při výpadku vlastní DB (fail-open vs. fail-closed) |

### G4. Observabilita

| Co |
|---|
| OpenTelemetry nativně, **propagace `traceparent`** z agenta přes gateway k backendu |
| Metriky tokenů a latence s vlastními dimenzemi (kdo, který agent, který use-case) |
| Logování promptů a odpovědí: **ve výchozím stavu vypnuté**, zapnutelné per klíč, do našeho úložiště |
| Funguje s libovolným OTEL backendem, nebo tlačí vendorovou observabilitu (Langfuse, Helicone, Portkey cloud) |

### G5. Bezpečnost a governance

| Co |
|---|
| Virtuální klíče, rotace, scope (které modely smí klíč volat) |
| **Propagace identity koncového uživatele** (`user`/`metadata`) k poskytovateli a do logů |
| Allowlist modelů per tým; **přišpendlení verze modelu** (žádné tiché `latest`) |
| Guardrails hooky (PII masking, injection detekce) – vlastní, nebo jen placené integrace |
| Multi-tenancy: izolace klíčů, rozpočtů a logů mezi tenanty |
| Kde leží SSO / RBAC admin UI – často první věc za placenou hranicí |

### G6. Rozsah vrstvy

| Co |
|---|
| Umí gateway i **MCP** (registry serverů, autorizace nástrojů) a **A2A** routing? Pokud ano, je to plus, nebo rozmazání vrstvy? |
| Je to L7 proxy (Envoy-based) nebo aplikační server (Python/Go)? Dopad na latenci a škálování |
| Režie gateway P50/P95 vs. přímé volání – **změřit harnessem**, ne věřit |

### G7. Provozní zralost

| Co |
|---|
| Stateless proxy, horizontální škálování, DB jen pro klíče a útratu |
| Config as code (YAML v Gitu), ne jen klikání v admin UI |
| Helm chart, verze, LTS, kadence breaking changes |
| Velikost image, počet runtime závislostí, SBOM |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| Počet podporovaných poskytovatelů („100+ LLMs") | Potřebujeme 4–5 správně, ne 100 povrchně |
| Hostovaná verze má hezčí dashboard | Nesmí být jádrem platformy (A4) |
| Semantic cache jako hlavní argument | U agentních běhů s nástroji je hit rate nízký |

## Changelog
- 2026-10-22: první verze; odvozeno z `frameworks/kriteria.md`, specializováno na Anthropic Messages passthrough,
  FinOps a propagaci identity.
- 2026-10-22: G1 doplněno o kontrakt z code.claude.com (beta hlavičky, system, ping, chybová těla, atribuční hlavičky).
