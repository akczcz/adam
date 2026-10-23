---
name: memory-research
description: Postup pro průzkum a prověrku vrstvy paměti a znalostí multiagentní platformy (mem0, Letta, Zep/Graphiti, Cognee, LangMem, Dapr state a Conversation API, Claude memory tool a CLAUDE.md, MCP memory servery, Qdrant, Weaviate, Milvus, pgvector, LanceDB, Chroma, Neo4j, Memgraph, FalkorDB, Kuzu, Apache AGE, Azure AI Search) a pro aktualizaci knowledge/memory/. Použij vždy, když Adam řeší, co si agenti pamatují mezi běhy, sdílenou firemní paměť, znalostní bázi nebo graf, RAG nad firemními daty, původ a stáří faktů, oprávnění k paměti a izolaci tenantů, memory poisoning, výmaz dat, kompakci kontextu nebo cenu tokenů paměti – i když slovo "paměť" výslovně nezazní.
---

# Průzkum paměti a znalostí

## 1. Vyjdi ze znalostní báze
- Přečti `knowledge/memory/overview.md` a `kriteria.md`; u dotčených kandidátů jejich soubor.
- Přečti rozhodnutí v `knowledge/platforma/cilova-architektura.md`: stav běhu drží **Dapr Workflows + DaprSessionStore**,
  epizodická data vznikají v **ClickHouse** (observabilita), oprávnění řeší **OPA** a identita **Keycloak/SPIRE**,
  nástroje jdou přes **MCP** a **agentgateway**. Paměť se do těchto švů musí vejít – ne vedle nich.
- Přečti `knowledge/README.md` – hlavička znalostních souborů tohoto repa (téma, naposledy ověřeno, zralost,
  primární zdroje) je **vzor modelu původu** pro firemní paměť.

## 2. Rozliš čtyři druhy a čtyři otázky
Pracovní · epizodická · sémantická · procedurální; M1 původ · M2 přístup · M3 rozhraní · M4 životní cyklus.
Framework, který tvrdí, že „řeší paměť“, obvykle řeší sémantickou paměť osobního asistenta bez tenantů a původu.

## 3. Licence a governance jako u frameworků
Postup `framework-research` sekce 2, vzorce v `knowledge/frameworks/licencni-vzorce.md`. Pro tuhle vrstvu navíc:
- **Graf DB jsou licenční minové pole**: Neo4j Community GPLv3 (Enterprise komerční, clustering a RBAC jen tam),
  Memgraph BSL, FalkorDB SSPL – zapiš doslovně; OSI alternativy Apache AGE, Kuzu (ověř stav), JanusGraph.
- Memory frameworky: SDK Apache + **hostovaná platforma** (mem0 Platform, Letta Cloud, Zep Cloud) – ověř, co funguje
  self-hosted bez klíče, kde se počítají embeddingy a zda SDK volá domů.
- Vektorové DB: `ee/` a cloud-only funkce (RBAC, multi-tenancy, backup) – zapiš doslovně.

## 4. Standardy a nativní schopnosti z primárních zdrojů
- Anthropic: memory tool (`memory_20250818`, stav beta?), Claude Code `memory` docs (CLAUDE.md, auto memory, `/memory`),
  context management / compaction, prompt caching jako „paměť“ v cache; Agent SDK session resume.
- Dapr 1.18: state management (komponenty, transakce, query API), **Conversation API** (historie, PII scrubbing),
  komponenty pro Azure AI Search / Cosmos DB / Postgres jako šev.
- MCP: resources vs. tools jako rozhraní paměti; existující memory MCP servery (reference `@modelcontextprotocol/server-memory`, mem0 MCP, Graphiti MCP).
- OTEL GenAI semconv: `create_memory`, `search_memory` spany (Development).
- GDPR čl. 17 a AI Act čl. 10 (data governance) – co z toho plyne pro výmaz a původ.

## 5. Posuzuj na firemním use casu, ne na osobním asistentovi
- Multi-tenant izolace v retrievalu (filtr per tenant **vynucený**, ne doporučený).
- Původ a datum ověření jako první třída v modelu; konflikt faktů; schválení zápisu do sdílené paměti.
- Memory poisoning: dokument s injection → trvalý „fakt“; karanténa a lidské schválení.
- Cena: tokeny paměti per turn, latence retrievalu, cena embeddingů přes gateway.

## 6. Analyzuj architektonicky
- Kde je paměť: MCP server (PEP uvnitř) + DB za Dapr komponentou; agentní kód bez SDK frameworku.
- Co je zadarmo (Dapr state, ClickHouse trace, CLAUDE.md) a co se musí postavit (destilace epizod, model původu, schvalovací zápis).
- Cena odchodu: export faktů s původem v JSONL; embeddingy přepočitatelné; graf jako hrany v Postgresu nebo otevřeném formátu.

## 7. Výstup
- Česky, závěr první, fakta se zdrojem a datem, doporučení jako doporučení.
- Návrh úprav `knowledge/memory/` jako diff; rozhodnutí do `knowledge/platforma/cilova-architektura.md`.
- Soubory měň až po Adamově souhlasu.

## 8. Čemu se vyhni
- Nevybírej podle skóre LoCoMo/LongMemEval – měří osobního asistenta.
- Nezaměňuj RAG nad dokumenty za paměť firmy.
- Netvrď stav memory toolu Anthropic ani licenci graf DB z paměti – ověř.
