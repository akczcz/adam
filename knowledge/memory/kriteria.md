---
tema: Hodnoticí kritéria pro vrstvu paměti a znalostí agentů
naposledy_overeno: 2026-10-23
zralost: n/a (metodika)
primarni_zdroje:
  - https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md
  - https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
  - https://code.claude.com/docs/en/memory
  - https://docs.dapr.io/developing-applications/building-blocks/state-management/
---

# Kritéria pro paměť a znalosti

Rubrika pro vrstvu **paměť a znalosti** platformy (viz [`../platforma/overview.md`](../platforma/overview.md)).
Zásada z hypotézy organizační vrstvy: **paměť je firemní, ne agentní.** Co se agent naučí o zákazníkovi, kódu nebo
procesu, patří firmě a řídí se oprávněním (I3), ne instancí agenta. Vrstva závisí na identitě (kdo smí číst co),
observabilitě (epizodická paměť vzniká z trace) a durable vrstvě (stav běhu už drží Dapr).

## Čtyři druhy paměti a kde už jsou

| Druh | Co to je | Kde už je / kde chybí |
|---|---|---|
| **Pracovní (stav běhu)** | kontext jednoho běhu, transcript, checkpointy | **Dapr Workflows + `DaprSessionStore`** (rozhodnuto) – tahle vrstva ji **neřeší** |
| **Epizodická** | co se stalo: běhy, rozhodnutí, HITL verdikty, výsledky | vzniká z trace v **ClickHouse** (rozhodnuto); chybí: destilace do „poučení“ a jejich vyhledání |
| **Sémantická** | fakta o zákazníkovi, systémech, kódu, lidech; s původem a datem ověření | **chybí** – kandidáti níže |
| **Procedurální** | jak se co dělá: runbooky, ADR, skilly, kód | repozitář + CLAUDE.md/skills (vzor tohoto repa); chybí: vyhledání a verzování v platformě |

## Čtyři otázky, které vrstva musí zodpovědět

| # | Otázka | Co to znamená v autonomní firmě |
|---|---|---|
| M1 | **Co si firma pamatuje a odkud to ví?** | Každý záznam má původ (trace_id / dokument / člověk), datum ověření, tenanta a vlastníka; „fakt“ bez původu je domněnka |
| M2 | **Kdo smí co číst a psát?** | Oprávnění per tenant, roli agenta a citlivost; zápis do sdílené paměti je akce s auditem, ne vedlejší efekt promptu |
| M3 | **Jak se paměť dostane do kontextu?** | Rozhraní pro agenty (MCP resources/tools, Agent SDK memory, context engineering), retrieval (vektor, graf, full-text, hybrid), kompakce |
| M4 | **Jak paměť stárne a mizí?** | Retence, zapomínání, oprava chyb, právo na výmaz (GDPR), konflikt starého a nového faktu |

## A. Vyřazovací kritéria

Společná A1–A5 z [`../frameworks/kriteria.md`](../frameworks/kriteria.md), pro tuhle vrstvu konkrétně:

| # | Kritérium | Co to znamená tady |
|---|---|---|
| A1 | OSI licence produkčního runtimu | **Pozor na graf DB** (Neo4j Community GPLv3 + Enterprise komerční; Memgraph BSL; FalkorDB SSPL) a na vektorové DB s `ee/`; memory frameworky bývají Apache SDK + hostovaná platforma |
| A2 | Kontejnery na Kubernetes | DB i memory služba u zákazníka |
| A3 | Air-gapped | Embeddingy přes **naši gateway** nebo lokální model, ne přes API frameworku |
| A4 | Bez řízené služby jednoho cloudu | Azure AI Search / Cosmos DB smí být **backend za abstrakcí** (Dapr state/komponenta), ne formát paměti |
| A5 | Stav mimo framework | Paměť v naší DB v dokumentovaném schématu, exportovatelná; framework je vyměnitelný |

## B. Bodovaná kritéria

### B1. Model a původ (M1)

| Co | Jak se to zjistí |
|---|---|
| Záznam nese **původ** (zdroj, trace_id, autor), **datum ověření**, **tenanta**, **confidence**; podporuje verzování a opravu | Schéma frameworku / DB; vzor hlavičky `knowledge/README.md` tohoto repa |
| Rozlišení fakt / názor / spekulace a „kdo to ověřil“ (člověk vs. agent) | Je to v modelu, nebo jen volný text |
| Entita + vztah (graf) vs. chunk + embedding (vektor) vs. obojí; temporalita (platí od–do) | Graphiti/Zep temporal graph, mem0 graph memory, Cognee |
| Deduplikace, konflikt starého a nového faktu (update vs. append) | Jak framework řeší „A se změnilo na B“ |

### B2. Přístup a izolace (M2)

| Co |
|---|
| Oprávnění per tenant, uživatel, role agenta, citlivost; vynucení v DB nebo v MCP serveru paměti (PEP), ne v promptu |
| Zápis jako auditovaná akce (kdo, kdy, z jakého běhu, schváleno?) – napojení na OPA a audit log |
| Oddělení paměti platformy, firmy (sdílená) a zákazníka (tenant); žádné prosakování mezi tenanty v retrievalu |
| Obrana proti **memory poisoning** (injection z dokumentu → trvalý „fakt“): karanténa, lidské schválení pro sdílenou paměť, původ |

### B3. Rozhraní a retrieval (M3)

| Co | Jak se to zjistí |
|---|---|
| Agent přistupuje přes **MCP** (resources pro čtení, tools pro zápis) – paměť je MCP server, ne SDK v agentovi | Existuje MCP server kandidáta; jaká je kvalita |
| Co dává **Claude Agent SDK / Claude** nativně: memory tool, CLAUDE.md a auto-memory, kompakce, context management, prompt cache | Docs Anthropic; hranice mezi „model si pamatuje“ a „firma si pamatuje“ |
| Retrieval: hybrid (BM25 + vektor), graf traversal, reranking, filtry per tenant; embeddingy přes gateway (A3) | Podpora filtrů v dotazu; kde se embedding počítá |
| Context engineering: kolik tokenů paměť stojí per turn; jak se vybírá, co do kontextu | Měřitelné harnessem |
| Dapr: state store, **Conversation API** (historie, PII scrubbing?), komponenty jako šev k Azure AI Search / Cosmos | Docs Dapr 1.18 |

### B4. Životní cyklus (M4)

| Co |
|---|
| Retence per tenant a per druh paměti; TTL; archivace |
| Výmaz na žádost (GDPR čl. 17) včetně embeddingů a odvozených faktů; doložitelnost výmazu |
| Zapomínání a decay (stará epizodická paměť → shrnutí); re-verifikace faktů (stáří > N dní = neověřeno) |
| Migrace schématu a změna embedding modelu (re-embedding) bez ztráty původu |

### B5. Kvalita a evaluace

| Co |
|---|
| Benchmarky paměti (LoCoMo, LongMemEval, …) – jen orientačně; **vlastní eval** nad rolemi: najde agent správný fakt o zákazníkovi, nepoužije zastaralý, nevyzradí cizí tenant |
| Měřitelné: precision/recall retrievalu, cena tokenů paměti per úkol, podíl odpovědí s původem |
| Observabilita: spany `create_memory` / `search_memory` (OTEL GenAI semconv, Development) |

### B6. Governance projektu a provoz

| Co |
|---|
| Licence, nadace, CLA/DCO, bus factor, telemetrie frameworku (phone-home) – jako B1 u frameworků |
| Helm, HA, zálohy; SDK Python/TypeScript; cena odchodu (export v otevřeném formátu) |

## C. Čím se záměrně neřídit

| Anti-kritérium | Proč |
|---|---|
| „Agent se učí sám“ bez původu a schválení | Memory poisoning a neauditovatelná domněnka jako fakt |
| Skóre na LoCoMo/LongMemEval jako volba | Měří jiný use case (osobní asistent), ne firemní paměť s tenanty |
| Počet podporovaných vektorových DB | Jedna správně přes Dapr komponentu stačí |
| „RAG = paměť“ | RAG je retrieval nad dokumenty; paměť firmy je i epizodická a procedurální s původem a životním cyklem |

## Changelog
- 2026-10-23: první verze; čtyři druhy paměti, otázky M1–M4, kritéria B1–B6.
